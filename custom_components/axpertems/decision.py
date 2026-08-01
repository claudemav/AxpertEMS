"""
Logique de décision pure du moteur EMS — remplace la logique de
axpert_energy_brain.yaml.

AUCUNE dépendance à Home Assistant dans ce fichier : uniquement des
fonctions pures (mêmes entrées -> mêmes sorties) et une petite classe de
debounce. C'est ce qui permet de le tester exhaustivement sans instance HA
(voir test_decision.py) — contrairement au reste de l'intégration.

IMPORTANT : ce module ne contient plus d'horaire codé en dur pour le
délestage/mode "soir" (l'ancien "evening_start" a disparu, remplacé par le
déficit solaire mesuré). Il reste UN SEUL horaire, `night_start` — un
filet de sécurité configurable (23h par défaut) qui s'ajoute à la vraie
détection astronomique de la nuit (sun.sun), pas un horaire de planning.

La couche qui relie ça aux vraies entités HA (services, coordinator,
horloge réelle) est dans engine.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time as dt_time, timedelta
from typing import Literal, Optional

Mode = Literal["NORMAL", "VACANCES"]
OutputOption = Literal["E2C", "SOLAIRE", "BATTERIE"]


def parse_hhmm(value: str) -> dt_time:
    """Parse 'HH:MM' -> time. Utilisé pour lire night_start configuré par l'utilisateur."""
    hour, minute = value.split(":")
    return dt_time(int(hour), int(minute))


def is_night(clock_time: dt_time, night_start: dt_time, sun_below_horizon: bool) -> bool:
    """Nuit = le soleil est réellement couché (sun.sun), OU on a dépassé
    l'horaire de secours `night_start` (23h par défaut, configurable).

    Le second critère est un filet de sécurité (capteur sun.sun
    indisponible, ou coucher de soleil tardif à certaines latitudes) —
    dans la grande majorité des cas, c'est sun_below_horizon qui déclenche
    en premier, bien avant night_start.

    Utilisé pour la PRÉFÉRENCE DE MODE (basculer sur BATTERIE dès la
    tombée du jour, cf decide_output_mode) — PAS pour la restauration
    forcée des charges, qui doit rester tardive (voir night_restore_ok)."""
    return sun_below_horizon or clock_time >= night_start


def night_restore_ok(clock_time: dt_time, night_start: dt_time, sun_below_horizon: bool) -> bool:
    """Fenêtre de restauration forcée des charges (si SOC confortable) :
    après night_start (23h par défaut) le soir, OU tôt le matin (avant
    midi) tant qu'il fait encore nuit.

    Volontairement plus tardif que is_night : on ne force pas la
    restauration juste après le coucher du soleil (dès 18h30 ici) — on
    laisse le délestage conserver la batterie pendant la soirée, et on ne
    la restaure de force qu'à partir de night_start, ou tôt le matin avant
    le lever du jour."""
    if clock_time >= night_start:
        return True
    if sun_below_horizon and clock_time < dt_time(12, 0):
        return True
    return False

# ---------------------------------------------------------------------------
# Debounce (réplique delay_on / delay_off d'un binary_sensor HA)
# ---------------------------------------------------------------------------

@dataclass
class Debounced:
    """État booléen qui ne bascule qu'après `delay_on`/`delay_off` de
    stabilité de la valeur brute — évite les oscillations rapides
    (ex: déficit solaire qui clignote sur un nuage passager).

    `now` est passé explicitement à chaque update() : pas d'horloge cachée,
    donc entièrement testable de façon déterministe.
    """

    delay_on: timedelta
    delay_off: timedelta
    stable_state: bool = False
    _pending_state: Optional[bool] = field(default=None, repr=False)
    _pending_since: Optional[datetime] = field(default=None, repr=False)

    def update(self, raw_state: bool, now: datetime) -> bool:
        if raw_state == self.stable_state:
            self._pending_state = None
            self._pending_since = None
            return self.stable_state

        if self._pending_state != raw_state:
            self._pending_state = raw_state
            self._pending_since = now

        delay = self.delay_on if raw_state else self.delay_off
        assert self._pending_since is not None
        if now - self._pending_since >= delay:
            self.stable_state = raw_state
            self._pending_state = None
            self._pending_since = None

        return self.stable_state


# ---------------------------------------------------------------------------
# Délestage / restauration — basé uniquement sur la couverture réelle
# ---------------------------------------------------------------------------

def shed_needed(*, grid_down: bool, deficit: bool) -> bool:
    """Le réseau est absent ET le PV ne couvre pas la charge (déficit
    confirmé, avec debounce) -> il faut délester.

    Avant : NORMAL délestait sur grid_down seul (sans vérifier le déficit),
    VACANCES exigeait un déficit confirmé. Cette asymétrie n'avait de sens
    que parce qu'on n'avait pas de mesure fiable du déficit disponible pour
    NORMAL à l'époque — maintenant qu'on l'a (debounce 10/5 min), les deux
    modes s'appuient dessus : c'est strictement plus sûr (on ne coupe plus
    une charge alors que le PV suffit encore, juste parce que le réseau est
    tombé)."""
    return grid_down and deficit


def tier1_shed_allowed(*, shed_needed: bool, night_restore_override: bool) -> bool:
    """Le palier 1 (essentiel, ex: frigo) ne doit PAS être délesté si on est
    dans la fenêtre de restauration nocturne acceptée (night_restore_ok) —
    sinon on entre dans une boucle : la restauration force le rallumage,
    puis le cycle d'évaluation suivant le déleste à nouveau immédiatement,
    et ainsi de suite indéfiniment. Une fois qu'on a décidé (nuit + SOC
    correct) d'accepter de puiser sur la batterie pour l'essentiel, le
    délestage ne doit plus revenir sur cette décision tant que le SOC reste
    correct — c'est night_restore_ok lui-même (recalculé à chaque cycle,
    via le seuil SOC) qui reprend la main si la batterie devient trop
    basse."""
    return shed_needed and not night_restore_override


def restore_needed(*, grid_up: bool, deficit: bool, battery_ok: bool) -> bool:
    return grid_up or (not deficit and battery_ok)


@dataclass(frozen=True)
class Load:
    entity_id: str
    name: str
    tier: int             # 1 = délestée en premier / restaurée en premier
    restore_delay: int     # secondes avant réenclenchement (protection matériel)


DEFAULT_LOADS: tuple[Load, ...] = (
    Load(entity_id="switch.frigo", name="Frigo", tier=1, restore_delay=180),
    Load(entity_id="switch.tele", name="Télé", tier=2, restore_delay=5),
)


# ---------------------------------------------------------------------------
# Choix du mode de sortie onduleur — basé uniquement sur couverture + nuit réelle
# ---------------------------------------------------------------------------

def decide_output_mode(
    *,
    current_mode: Optional[OutputOption],
    night_restore_window: bool,
    battery_soc_ok: bool,
    vacances: bool,
    tele_power_low: bool,
    deficit: bool,
    grid_up: bool,
    max_battery_mode: bool = False,
    battery_capacity: float = 100.0,
    battery_critical_threshold: float = 20.0,
    evening_decline: bool = False,
) -> Optional[OutputOption]:
    """Le premier cas qui matche gagne. Retourne None si rien à changer
    (évite un appel de service inutile).

    `night_restore_window` vient de night_restore_ok() (23h par défaut,
    configurable, PAS le coucher du soleil) — c'est le seul repère qui
    peut reprendre la main sur un E2C en cours (cf priorité 2 ci-dessous).
    Avant ce cap, une fois basculé en E2C, on y reste (sticky) même si le
    PV couvre à nouveau momentanément ou que le soleil est déjà couché —
    MAIS seulement si `evening_decline` est vrai (cf ci-dessous).

    `max_battery_mode` : si activé, la règle 2 (sticky E2C sur déficit)
    est suspendue tant que la batterie reste au-dessus de
    `battery_critical_threshold` — on laisse tourner sur batterie/PV même
    en déficit, jusqu'à un seuil bas explicite plutôt que de céder au
    réseau dès qu'un déficit est confirmé.

    `evening_decline` : vrai à partir du dernier déficit solaire de
    l'après-midi (en pratique : une heuristique horaire tardive, la vraie
    détection du "dernier" déficit n'étant possible qu'après coup), faux
    le reste du temps. Tant que faux (journée), un passage en E2C reste
    réversible — un nuage qui se dissipe permet un retour immédiat vers
    BATTERIE. Une fois vrai (déclin du soir confirmé), E2C devient sticky
    jusqu'à la fenêtre de nuit tardive, comme avant."""

    # 1. Fenêtre de nuit tardive (23h, configurable) + SOC ok -> BATTERIE.
    #    Seul cas qui peut annuler un E2C sticky en cours.
    if (
        night_restore_window
        and battery_soc_ok
        and current_mode != "BATTERIE"
        and (not vacances or tele_power_low)
    ):
        return "BATTERIE"

    # 2. Déficit solaire + réseau dispo -> E2C — MAIS seulement AVANT la
    #    fenêtre de nuit tardive (cf règle 1, sinon boucle infinie vécue
    #    en conditions réelles). En mode Max Batterie, suspendue tant que
    #    la batterie reste au-dessus du seuil critique.
    max_battery_blocks_e2c = max_battery_mode and battery_capacity > battery_critical_threshold
    if (
        not night_restore_window
        and not max_battery_blocks_e2c
        and deficit
        and grid_up
        and current_mode != "E2C"
    ):
        return "E2C"

    # 3. PV couvre la charge -> autoconsommation. Sticky uniquement pendant
    #    le déclin du soir (evening_decline) : le jour, un E2C engagé sur
    #    un déficit passager (nuage) redescend vers BATTERIE dès que le
    #    déficit se résorbe, comme n'importe quel autre mode.
    if not deficit and (
        current_mode not in ("BATTERIE", "E2C")
        or (current_mode == "E2C" and not evening_decline)
    ):
        return "BATTERIE"

    return None
