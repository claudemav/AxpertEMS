"""
Moteur EMS — orchestre decision.py avec les vraies entités Home Assistant.

Remplace axpert_energy_brain.yaml. Toute la logique de décision vit dans
decision.py (pur, testé) ; ce module ne fait que : lire l'état réel,
appeler les fonctions pures, et traduire le résultat en appels de service.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from . import decision
from .const import (
    CONF_DEFICIT_DELAY_OFF,
    CONF_DEFICIT_DELAY_ON,
    CONF_LOADS,
    CONF_NIGHT_START,
    CONF_SOC_THRESHOLD,
    DEFAULT_OPTIONS,
)
from .coordinator import AxpertCoordinator

_LOGGER = logging.getLogger(__name__)

_PRIORITY_TO_OPTION = {
    "Utility first": "E2C",
    "Solar first": "SOLAIRE",
    "SBU first": "BATTERIE",
}

MAX_HISTORY = 30


class AxpertEnergyManager:
    """Un par entrée de config. Écoute le coordinator + une horloge de secours."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: AxpertCoordinator,
        options: dict | None = None,
    ) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self.mode: decision.Mode = "NORMAL"

        self._restore_tasks: dict[str, asyncio.Task] = {}
        self._remove_listener = None
        self._remove_interval = None
        self._enabled = False

        self.history: deque[dict[str, Any]] = deque(maxlen=MAX_HISTORY)
        self._on_decision_callbacks: list = []

        # Valeurs par défaut avant tout appel à async_update_options().
        self._soc_threshold: float = DEFAULT_OPTIONS[CONF_SOC_THRESHOLD]
        self._deficit_debounce = decision.Debounced(
            delay_on=timedelta(minutes=DEFAULT_OPTIONS[CONF_DEFICIT_DELAY_ON]),
            delay_off=timedelta(minutes=DEFAULT_OPTIONS[CONF_DEFICIT_DELAY_OFF]),
        )
        self._night_start = decision.parse_hhmm(DEFAULT_OPTIONS[CONF_NIGHT_START])
        self._loads: tuple[decision.Load, ...] = decision.DEFAULT_LOADS

        self.async_update_options(options or DEFAULT_OPTIONS)

    def async_update_options(self, options: dict) -> None:
        """Applique de nouvelles options à chaud — appelé au démarrage ET à
        chaque sauvegarde de l'Options Flow, SANS redémarrage de HA."""
        self._soc_threshold = options.get(CONF_SOC_THRESHOLD, DEFAULT_OPTIONS[CONF_SOC_THRESHOLD])

        # On garde l'état stable du debounce actuel (ne pas perdre un déficit
        # déjà en cours de confirmation juste parce que l'utilisateur a
        # changé un seuil ailleurs).
        self._deficit_debounce.delay_on = timedelta(
            minutes=options.get(CONF_DEFICIT_DELAY_ON, DEFAULT_OPTIONS[CONF_DEFICIT_DELAY_ON])
        )
        self._deficit_debounce.delay_off = timedelta(
            minutes=options.get(CONF_DEFICIT_DELAY_OFF, DEFAULT_OPTIONS[CONF_DEFICIT_DELAY_OFF])
        )

        self._night_start = decision.parse_hhmm(
            options.get(CONF_NIGHT_START, DEFAULT_OPTIONS[CONF_NIGHT_START])
        )

        raw_loads = options.get(CONF_LOADS, DEFAULT_OPTIONS[CONF_LOADS])
        self._loads = tuple(
            decision.Load(
                entity_id=item["entity_id"],
                name=item["name"],
                tier=int(item["tier"]),
                restore_delay=int(item["restore_delay"]),
            )
            for item in raw_loads
        )
        _LOGGER.debug("EMS : options appliquées (%d charges configurées)", len(self._loads))

    def async_add_decision_listener(self, callback_fn) -> None:
        """Permet à AxpertLastDecisionSensor de se rafraîchir sans polling."""
        self._on_decision_callbacks.append(callback_fn)

    def _log_decision(self, message: str) -> None:
        entry = {"time": dt_util.now().isoformat(timespec="seconds"), "message": message}
        self.history.append(entry)
        _LOGGER.info("EMS : %s", message)
        for cb in self._on_decision_callbacks:
            cb()

    def async_setup(self) -> None:
        self._enabled = True
        self._remove_listener = self.coordinator.async_add_listener(self._handle_coordinator_update)
        # Filet de sécurité : réévalue toutes les minutes même sans nouvelle
        # donnée — reproduit les triggers `time_pattern` de l'ancien
        # automation YAML (utile notamment pour le filet night_start).
        self._remove_interval = async_track_time_interval(
            self.hass, self._handle_interval, timedelta(minutes=1)
        )

    def async_unload(self) -> None:
        if self._remove_listener:
            self._remove_listener()
        if self._remove_interval:
            self._remove_interval()
        for task in self._restore_tasks.values():
            task.cancel()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.hass.async_create_task(self._async_evaluate())

    @callback
    def _handle_interval(self, _now: datetime) -> None:
        self.hass.async_create_task(self._async_evaluate())

    async def async_set_mode(self, mode: decision.Mode) -> None:
        self.mode = mode
        if self._enabled:
            await self._async_evaluate()

    # -- évaluation principale -------------------------------------------

    async def _async_evaluate(self) -> None:
        data = self.coordinator.data
        if not data:
            return  # onduleur en erreur -> on ne prend aucune décision hasardeuse

        now = dt_util.now()
        qpigs: dict[str, Any] = data.get("qpigs", {})
        qpiri: dict[str, Any] = data.get("qpiri", {})

        grid_v = qpigs.get("ac_input_voltage") or 0
        grid_down = grid_v < 1
        grid_up = grid_v > 150

        pv_power = qpigs.get("pv_input_power") or 0
        output_power = qpigs.get("ac_output_active_power") or 0
        raw_deficit = pv_power < output_power
        deficit = self._deficit_debounce.update(raw_deficit, now)

        battery_capacity = qpigs.get("battery_capacity") or 0
        battery_charging = qpigs.get("battery_charging_current") or 0
        battery_discharging = qpigs.get("battery_discharge_current") or 0
        # "En charge" ou "Repos" -> ok ; "En décharge" -> pas ok (parité ancien template)
        battery_ok = battery_charging > 1 or not (battery_discharging > 1)

        night_restore = decision.night_restore_ok(
            now.time(), self._night_start, self._is_sun_below_horizon()
        )
        night_restore_active = night_restore and battery_capacity > self._soc_threshold

        shed = decision.shed_needed(grid_down=grid_down, deficit=deficit)
        restore = decision.restore_needed(grid_up=grid_up, deficit=deficit, battery_ok=battery_ok)

        await self._async_apply_load_shedding(
            shed=shed, restore=restore, deficit=deficit, night_restore_override=night_restore_active
        )
        await self._async_apply_night_restore(is_night=night_restore, battery_capacity=battery_capacity)
        await self._async_apply_output_mode(
            qpiri=qpiri,
            night_restore_window=night_restore,
            battery_capacity=battery_capacity,
            grid_up=grid_up,
            deficit=deficit,
        )

    # -- délestage ---------------------------------------------------------

    async def _async_apply_load_shedding(
        self, *, shed: bool, restore: bool, deficit: bool, night_restore_override: bool
    ) -> None:
        loads = self._loads
        tier1 = [load for load in loads if load.tier == 1]
        tier2 = [load for load in loads if load.tier == 2]

        if shed:
            if decision.tier1_shed_allowed(
                shed_needed=shed, night_restore_override=night_restore_override
            ):
                for load in tier1:
                    await self._async_turn_off_if_needed(load)

            tier1_currently_off = any(self._is_off(load.entity_id) for load in tier1)
            if deficit and tier1_currently_off:
                for load in tier2:
                    await self._async_turn_off_if_needed(load)

        elif restore:
            for load in loads:
                if self._is_off(load.entity_id):
                    self._schedule_restore(load)

    async def _async_apply_night_restore(self, *, is_night: bool, battery_capacity: float) -> None:
        if not is_night or battery_capacity <= self._soc_threshold:
            return
        # Uniquement le palier 1 (frigo) : la nuit, pas de raison de forcer
        # la télé à se rallumer toute seule, seule la conservation de la
        # nourriture justifie de puiser sur la batterie sans attendre le
        # réseau/PV.
        tier1 = [load for load in self._loads if load.tier == 1]
        for load in tier1:
            if self._is_off(load.entity_id) and load.entity_id not in self._restore_tasks:
                self._schedule_restore(load, delay_override=60)

    def _is_off(self, entity_id: str) -> bool:
        state = self.hass.states.get(entity_id)
        return state is not None and state.state == "off"

    async def _async_turn_off_if_needed(self, load: decision.Load) -> None:
        state = self.hass.states.get(load.entity_id)
        if state is not None and state.state == "on":
            await self.hass.services.async_call(
                "switch", "turn_off", {"entity_id": load.entity_id}
            )
            self._log_decision(f"Délestage de {load.name}")

    def _schedule_restore(self, load: decision.Load, delay_override: int | None = None) -> None:
        if load.entity_id in self._restore_tasks:
            return  # déjà planifié

        async def _restore() -> None:
            try:
                await asyncio.sleep(delay_override or load.restore_delay)
                if self._is_off(load.entity_id):
                    await self.hass.services.async_call(
                        "switch", "turn_on", {"entity_id": load.entity_id}
                    )
                    self._log_decision(f"Restauration de {load.name}")
            finally:
                self._restore_tasks.pop(load.entity_id, None)

        self._restore_tasks[load.entity_id] = self.hass.async_create_task(_restore())

    # -- mode de sortie ------------------------------------------------------

    async def _async_apply_output_mode(
        self,
        *,
        qpiri: dict[str, Any],
        night_restore_window: bool,
        battery_capacity: float,
        grid_up: bool,
        deficit: bool,
    ) -> None:
        current_priority = qpiri.get("output_source_priority")
        current_mode = _PRIORITY_TO_OPTION.get(current_priority)

        tele_power_low = True
        tele_state = self.hass.states.get("sensor.tele_puissance")
        if tele_state is not None:
            try:
                tele_power_low = float(tele_state.state) < 10
            except ValueError:
                tele_power_low = True

        new_mode = decision.decide_output_mode(
            current_mode=current_mode,
            night_restore_window=night_restore_window,
            battery_soc_ok=battery_capacity > self._soc_threshold,
            vacances=(self.mode == "VACANCES"),
            tele_power_low=tele_power_low,
            deficit=deficit,
            grid_up=grid_up,
        )

        if new_mode is not None:
            self._log_decision(f"Changement de mode -> {new_mode}")
            await self.coordinator.async_set_output_mode(new_mode)

    # -- horloge solaire ----------------------------------------------------

    def _is_sun_below_horizon(self) -> bool:
        sun_state = self.hass.states.get("sun.sun")
        if sun_state is None:
            return False  # pas d'info -> on ne force pas la nuit (night_start reste le filet)
        return sun_state.state == "below_horizon"
