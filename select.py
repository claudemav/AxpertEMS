"""Sélecteur du mode de sortie — remplace input_select.axpert_output_mode.

Contrairement à l'ancienne architecture (input_select + automation qui
traduit le choix en shell_command SSH), ce select pilote directement
l'onduleur via le coordinator, et reflète l'état RÉEL lu sur l'onduleur
(QPIRI) plutôt qu'un état supposé.
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .coordinator import AxpertCoordinator
from .engine import AxpertEnergyManager
from .entity import AxpertEntity
from .protocol import CHARGER_PRIORITY_COMMANDS, OUTPUT_MODE_COMMANDS

OPTIONS = list(OUTPUT_MODE_COMMANDS)  # ["E2C", "SOLAIRE", "BATTERIE"]
CHARGER_OPTIONS = list(CHARGER_PRIORITY_COMMANDS)  # ["E2C", "SOLAIRE", "MIXTE", "SOLAIRE_SEUL"]

# Traduit le libellé lu sur l'onduleur (QPIRI) vers nos options internes.
_PRIORITY_TO_OPTION = {
    "Utility first": "E2C",
    "Solar first": "SOLAIRE",
    "SBU first": "BATTERIE",
}

_CHARGER_PRIORITY_TO_OPTION = {
    "Utility first": "E2C",
    "Solar first": "SOLAIRE",
    "Solar and utility": "MIXTE",
    "Solar only": "SOLAIRE_SEUL",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: AxpertCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    engine: AxpertEnergyManager = hass.data[DOMAIN][entry.entry_id]["engine"]
    async_add_entities(
        [
            AxpertOutputModeSelect(coordinator),
            AxpertEmsModeSelect(coordinator, engine),
            AxpertChargerPrioritySelect(coordinator),
        ]
    )


class AxpertOutputModeSelect(AxpertEntity, SelectEntity):
    _attr_options = OPTIONS
    _attr_icon = "mdi:transmission-tower"

    def __init__(self, coordinator: AxpertCoordinator) -> None:
        super().__init__(coordinator, "output_mode")
        self._attr_name = "Axpert Output Mode"

    @property
    def current_option(self) -> str | None:
        if self.coordinator.data is None:
            return None
        priority = self.coordinator.data["qpiri"].get("output_source_priority")
        return _PRIORITY_TO_OPTION.get(priority)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_output_mode(option)


class AxpertChargerPrioritySelect(AxpertEntity, SelectEntity):
    """Priorité de CHARGE (PCP) — distincte de la priorité de SORTIE (POP).

    Contrôle d'où vient le courant qui charge la batterie, pas d'où vient
    l'alimentation de la maison. Risque faible : réversible, n'affecte pas
    les tensions/seuils de sécurité de la batterie elle-même."""

    _attr_options = CHARGER_OPTIONS
    _attr_icon = "mdi:battery-charging-100"

    def __init__(self, coordinator: AxpertCoordinator) -> None:
        super().__init__(coordinator, "charger_priority")
        self._attr_name = "Axpert Charger Priority"

    @property
    def current_option(self) -> str | None:
        if self.coordinator.data is None:
            return None
        priority = self.coordinator.data["qpiri"].get("charger_source_priority")
        return _CHARGER_PRIORITY_TO_OPTION.get(priority)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_charger_priority(option)


class AxpertEmsModeSelect(AxpertEntity, SelectEntity, RestoreEntity):
    """NORMAL / VACANCES — remplace input_select.ems_mode.

    C'est une préférence utilisateur pure (pas une lecture onduleur), donc
    RestoreEntity la restaure telle quelle après un redémarrage de HA,
    comme le faisait l'ancien input_select.
    """

    _attr_options = ["NORMAL", "VACANCES"]
    _attr_icon = "mdi:brain"

    def __init__(self, coordinator: AxpertCoordinator, engine: AxpertEnergyManager) -> None:
        super().__init__(coordinator, "ems_mode")
        self._attr_name = "Axpert EMS Mode"
        self._engine = engine
        self._current = "NORMAL"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in self._attr_options:
            self._current = last_state.state
        self._engine.mode = self._current

    @property
    def current_option(self) -> str:
        return self._current

    async def async_select_option(self, option: str) -> None:
        self._current = option
        self.async_write_ha_state()
        await self._engine.async_set_mode(option)
