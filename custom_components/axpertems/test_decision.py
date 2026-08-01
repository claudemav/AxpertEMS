"""
Tests de decision.py — AUCUNE dépendance HA, s'exécutent avec un simple
`python3 test_decision.py`. C'est la partie du moteur EMS la plus critique
à avoir juste, donc la plus testée.
"""

from datetime import datetime, time as dt_time, timedelta

import decision


# --- is_night (astronomie + filet de sécurité configurable) ------------

def test_is_night_soleil_couche():
    assert decision.is_night(dt_time(18, 30), dt_time(23, 0), True) is True


def test_is_night_avant_night_start_soleil_leve():
    assert decision.is_night(dt_time(20, 0), dt_time(23, 0), False) is False


def test_is_night_apres_night_start_meme_si_capteur_sun_ko():
    assert decision.is_night(dt_time(23, 15), dt_time(23, 0), False) is True


def test_is_night_start_configurable():
    assert decision.is_night(dt_time(21, 30), dt_time(21, 0), False) is True


def test_parse_hhmm():
    assert decision.parse_hhmm("23:00") == dt_time(23, 0)
    assert decision.parse_hhmm("21:30") == dt_time(21, 30)


# --- night_restore_ok (distinct de is_night, volontairement plus tardif) ---

def test_night_restore_pas_juste_apres_coucher_du_soleil():
    """Le cas exact du bug rapporté : 18h35, soleil couché, SOC ok -> ne
    doit PAS forcer la restauration (sinon ça annule le délestage en cours)."""
    assert decision.night_restore_ok(dt_time(18, 35), dt_time(23, 0), True) is False


def test_night_restore_apres_night_start():
    assert decision.night_restore_ok(dt_time(23, 5), dt_time(23, 0), True) is True


def test_night_restore_tot_le_matin_avant_midi_soleil_couche():
    assert decision.night_restore_ok(dt_time(2, 0), dt_time(23, 0), True) is True


def test_night_restore_apres_midi_soleil_couche_ne_compte_pas():
    # Cas hypothétique/capteur farfelu : ne doit pas se déclencher l'après-midi
    assert decision.night_restore_ok(dt_time(14, 0), dt_time(23, 0), True) is False


def test_night_restore_is_night_restent_bien_distincts():
    """À 18h35 soleil couché : is_night=True (préférence BATTERIE) mais
    night_restore_ok=False (pas de restauration forcée). C'est exactement
    la distinction qui corrige le bug."""
    assert decision.is_night(dt_time(18, 35), dt_time(23, 0), True) is True
    assert decision.night_restore_ok(dt_time(18, 35), dt_time(23, 0), True) is False


# --- Debounce ----------------------------------------------------------

def test_debounce_ne_bascule_pas_avant_le_delai():
    deb = decision.Debounced(delay_on=timedelta(minutes=10), delay_off=timedelta(minutes=5))
    t0 = datetime(2026, 7, 11, 12, 0)
    assert deb.update(True, t0) is False  # pas encore stable
    assert deb.update(True, t0 + timedelta(minutes=5)) is False  # toujours pas


def test_debounce_bascule_apres_le_delai():
    deb = decision.Debounced(delay_on=timedelta(minutes=10), delay_off=timedelta(minutes=5))
    t0 = datetime(2026, 7, 11, 12, 0)
    deb.update(True, t0)
    assert deb.update(True, t0 + timedelta(minutes=11)) is True


def test_debounce_annule_si_ca_revient_avant_le_delai():
    deb = decision.Debounced(delay_on=timedelta(minutes=10), delay_off=timedelta(minutes=5))
    t0 = datetime(2026, 7, 11, 12, 0)
    deb.update(True, t0)
    deb.update(False, t0 + timedelta(minutes=3))  # annule avant les 10 min
    assert deb.update(True, t0 + timedelta(minutes=11)) is False  # le compteur a été remis à zéro


def test_debounce_delay_off_plus_court():
    deb = decision.Debounced(delay_on=timedelta(minutes=10), delay_off=timedelta(minutes=5))
    deb.stable_state = True
    t0 = datetime(2026, 7, 11, 12, 0)
    assert deb.update(False, t0 + timedelta(minutes=4)) is True    # pending démarre ici
    assert deb.update(False, t0 + timedelta(minutes=8)) is True    # +4min de pending, pas encore
    assert deb.update(False, t0 + timedelta(minutes=10)) is False  # +6min de pending, basculé


# --- shed_needed / restore_needed (basé uniquement sur la couverture réelle) ---

def test_shed_exige_grid_down_et_deficit():
    assert decision.shed_needed(grid_down=True, deficit=True) is True
    assert decision.shed_needed(grid_down=True, deficit=False) is False  # PV couvre -> pas de souci
    assert decision.shed_needed(grid_down=False, deficit=True) is False  # réseau dispo -> pas de souci
    assert decision.shed_needed(grid_down=False, deficit=False) is False


def test_tier1_shed_bloque_pendant_night_restore():
    """Le cas exact rapporté : 23h30, 55% batterie, pas de réseau -> le
    délestage ne doit PAS reprendre la main sur le frigo une fois que la
    restauration nocturne a décidé de le laisser tourner."""
    assert decision.tier1_shed_allowed(shed_needed=True, night_restore_override=True) is False


def test_tier1_shed_normal_hors_night_restore():
    assert decision.tier1_shed_allowed(shed_needed=True, night_restore_override=False) is True


def test_tier1_shed_rien_a_faire_sans_deficit():
    assert decision.tier1_shed_allowed(shed_needed=False, night_restore_override=False) is False


def test_restore_si_reseau_revient():
    assert decision.restore_needed(grid_up=True, deficit=True, battery_ok=False) is True


def test_restore_si_plus_de_deficit_et_batterie_ok():
    assert decision.restore_needed(grid_up=False, deficit=False, battery_ok=True) is True
    assert decision.restore_needed(grid_up=False, deficit=True, battery_ok=True) is False


def test_restore_rien_ne_va():
    assert decision.restore_needed(grid_up=False, deficit=True, battery_ok=False) is False


# --- decide_output_mode (night_restore_window = 23h, PAS le coucher du soleil) ---

def test_mode_23h_soc_ok_normal():
    result = decision.decide_output_mode(
        current_mode="E2C", night_restore_window=True, battery_soc_ok=True,
        vacances=False, tele_power_low=False, deficit=True, grid_up=False,
    )
    assert result == "BATTERIE"


def test_mode_23h_vacances_attend_tele_eteinte():
    result = decision.decide_output_mode(
        current_mode="E2C", night_restore_window=True, battery_soc_ok=True,
        vacances=True, tele_power_low=False, deficit=True, grid_up=False,
    )
    assert result is None  # télé encore allumée -> on ne bascule pas


def test_mode_23h_vacances_tele_eteinte():
    result = decision.decide_output_mode(
        current_mode="E2C", night_restore_window=True, battery_soc_ok=True,
        vacances=True, tele_power_low=True, deficit=True, grid_up=False,
    )
    assert result == "BATTERIE"


def test_mode_solaire_promu_en_battery_si_pv_couvre():
    """PV couvre alors qu'on est en SOLAIRE (pas E2C) -> promotion normale vers BATTERIE."""
    result = decision.decide_output_mode(
        current_mode="SOLAIRE", night_restore_window=False, battery_soc_ok=False,
        vacances=False, tele_power_low=True, deficit=False, grid_up=True,
    )
    assert result == "BATTERIE"


def test_mode_e2c_reste_sticky_pendant_le_declin_du_soir():
    """evening_decline=True (après le dernier déficit de l'après-midi) :
    une fois basculé en E2C, on n'y retourne pas juste parce que le PV
    couvre de nouveau brièvement — on reste en E2C jusqu'à 23h."""
    result = decision.decide_output_mode(
        current_mode="E2C", night_restore_window=False, battery_soc_ok=True,
        vacances=False, tele_power_low=True, deficit=False, grid_up=True,
        evening_decline=True,
    )
    assert result is None


def test_mode_e2c_repart_en_battery_hors_declin_du_soir():
    """Le cas corrigé : en pleine journée (evening_decline=False, ex: un
    nuage passager a fait basculer en E2C), dès que le déficit se résorbe,
    retour possible vers BATTERIE — pas de sticky avant le vrai déclin
    du soir."""
    result = decision.decide_output_mode(
        current_mode="E2C", night_restore_window=False, battery_soc_ok=True,
        vacances=False, tele_power_low=True, deficit=False, grid_up=True,
        evening_decline=False,
    )
    assert result == "BATTERIE"


def test_mode_e2c_reste_sticky_meme_apres_le_coucher_du_soleil():
    """Le cas exact rapporté : 18h45, soleil déjà couché, choix manuel E2C
    -> ne doit PAS repartir sur BATTERIE juste parce que le soleil est
    couché. Seule la fenêtre 23h (pas le coucher du soleil) peut reprendre
    la main."""
    result = decision.decide_output_mode(
        current_mode="E2C", night_restore_window=False, battery_soc_ok=True,
        vacances=False, tele_power_low=True, deficit=True, grid_up=True,
    )
    assert result is None


def test_mode_e2c_sticky_mais_23h_reste_prioritaire():
    """À 23h, le retour vers BATTERIE reprend la main sur le E2C sticky."""
    result = decision.decide_output_mode(
        current_mode="E2C", night_restore_window=True, battery_soc_ok=True,
        vacances=False, tele_power_low=True, deficit=False, grid_up=True,
    )
    assert result == "BATTERIE"


def test_mode_deficit_et_reseau_dispo_bascule_e2c_meme_tard():
    result = decision.decide_output_mode(
        current_mode="BATTERIE", night_restore_window=False, battery_soc_ok=False,
        vacances=False, tele_power_low=True, deficit=True, grid_up=True,
    )
    assert result == "E2C"


def test_mode_deja_bon_ne_redeclenche_pas():
    result = decision.decide_output_mode(
        current_mode="BATTERIE", night_restore_window=True, battery_soc_ok=True,
        vacances=False, tele_power_low=True, deficit=True, grid_up=False,
    )
    assert result is None  # déjà en BATTERIE -> pas de réappel inutile


def test_mode_deficit_sans_reseau_rien_ne_matche():
    result = decision.decide_output_mode(
        current_mode="SOLAIRE", night_restore_window=False, battery_soc_ok=False,
        vacances=False, tele_power_low=True, deficit=True, grid_up=False,
    )
    assert result is None  # déficit mais pas de réseau -> rien à faire (on reste sur batterie/PV)


def test_mode_23h_deficit_et_reseau_ne_repart_pas_en_e2c():
    """RÉGRESSION — bug d'oscillation infinie vécu en conditions réelles :
    la nuit (23h+), le déficit est quasi toujours vrai (PV à 0) et le
    réseau souvent dispo. Sans le 'not night_restore_window', decide_output_mode
    bascule en BATTERIE (règle 1) puis immédiatement en E2C (règle 2) puis
    BATTERIE puis E2C... en boucle. Ce test verrouille : une fois en
    BATTERIE après 23h, deficit+grid_up ne doivent PLUS faire revenir en E2C."""
    result = decision.decide_output_mode(
        current_mode="BATTERIE", night_restore_window=True, battery_soc_ok=True,
        vacances=True, tele_power_low=True, deficit=True, grid_up=True,
    )
    assert result is None


def test_mode_23h_force_battery_meme_avec_deficit_et_reseau():
    """Le complément du test ci-dessus : si on est encore en E2C au moment
    où on franchit 23h, la règle 1 doit gagner malgré deficit+grid_up."""
    result = decision.decide_output_mode(
        current_mode="E2C", night_restore_window=True, battery_soc_ok=True,
        vacances=True, tele_power_low=True, deficit=True, grid_up=True,
    )
    assert result == "BATTERIE"


def test_mode_max_battery_bloque_e2c_si_soc_au_dessus_du_seuil_critique():
    """Le cas demandé : déficit au réveil (PV faible), réseau dispo, mode
    Max Batterie actif, SOC largement au-dessus du seuil critique -> reste
    sur batterie malgré le déficit."""
    result = decision.decide_output_mode(
        current_mode="BATTERIE", night_restore_window=False, battery_soc_ok=False,
        vacances=False, tele_power_low=True, deficit=True, grid_up=True,
        max_battery_mode=True, battery_capacity=60.0, battery_critical_threshold=20.0,
    )
    assert result is None


def test_mode_max_battery_cede_sous_le_seuil_critique():
    """Même situation, mais SOC sous le seuil critique -> le mode Max
    Batterie cède quand même à E2C (filet de sécurité)."""
    result = decision.decide_output_mode(
        current_mode="BATTERIE", night_restore_window=False, battery_soc_ok=False,
        vacances=False, tele_power_low=True, deficit=True, grid_up=True,
        max_battery_mode=True, battery_capacity=15.0, battery_critical_threshold=20.0,
    )
    assert result == "E2C"


if __name__ == "__main__":
    import sys

    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"OK   {test.__name__}")
        except Exception as err:  # noqa: BLE001
            failed += 1
            print(f"FAIL {test.__name__}: {err}")
    print(f"\n{len(tests) - failed}/{len(tests)} tests passés")
    sys.exit(1 if failed else 0)
