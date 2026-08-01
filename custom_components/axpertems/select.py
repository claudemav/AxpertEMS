"""Sélecteurs pilotant l'onduleur directement via le coordinator."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AxpertCoordinator
from .entity import AxpertEntity
from .exceptions import AxpertCommandRejectedError
from .protocol import CHARGER_PRIORITY_COMMANDS, OUTPUT_MODE_COMMANDS

OPTIONS = list(OUTPUT_MODE_COMMANDS)
CHARGER_OPTIONS = list(CHARGER_PRIORITY_COMMANDS)

_PRIORITY_TO_OPTION = {
    "Utility first": "E2C", "Solar first": "SOLAIRE", "SBU first": "BATTERIE",
}
_CHARGER_PRIORITY_TO_OPTION = {
    "Utility first": "E2C", "Solar first": "SOLAIRE",
    "Solar and utility": "MIXTE", "Solar only": "SOLAIRE_SEUL",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: AxpertCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        [
            AxpertOutputModeSelect(coordinator),
            AxpertChargerPrioritySelect(coordinator),
            AxpertMaxChargingCurrentSelect(coordinator),
            AxpertMaxUtilityChargingCurrentSelect(coordinator),
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
        priority = self.coordinator.data.get("qpiri", {}).get("output_source_priority")
        return _PRIORITY_TO_OPTION.get(priority)

    async def async_select_option(self, option: str) -> None:
        try:
            await self.coordinator.async_set_output_mode(option)
        except AxpertCommandRejectedError as err:
            raise HomeAssistantError(
                f"L'onduleur a refusé le mode de sortie « {option} »."
            ) from err


class AxpertChargerPrioritySelect(AxpertEntity, SelectEntity):
    _attr_options = CHARGER_OPTIONS
    _attr_icon = "mdi:battery-charging-100"

    def __init__(self, coordinator: AxpertCoordinator) -> None:
        super().__init__(coordinator, "charger_priority")
        self._attr_name = "Axpert Charger Priority"

    @property
    def current_option(self) -> str | None:
        if self.coordinator.data is None:
            return None
        priority = self.coordinator.data.get("qpiri", {}).get("charger_source_priority")
        return _CHARGER_PRIORITY_TO_OPTION.get(priority)

    async def async_select_option(self, option: str) -> None:
        try:
            await self.coordinator.async_set_charger_priority(option)
        except AxpertCommandRejectedError as err:
            raise HomeAssistantError(
                f"L'onduleur a refusé la priorité de charge « {option} »."
            ) from err


class AxpertMaxChargingCurrentSelect(AxpertEntity, SelectEntity):
    _attr_icon = "mdi:current-dc"

    def __init__(self, coordinator: AxpertCoordinator) -> None:
        super().__init__(coordinator, "max_charging_current_select")
        self._attr_name = "Axpert Max Charging Current"

    @property
    def options(self) -> list[str]:
        discovered = self.coordinator.supported_max_charging_currents
        if discovered:
            return [str(v) for v in discovered]
        current = self.current_option
        return [current] if current is not None else []

    @property
    def current_option(self) -> str | None:
        if self.coordinator.data is None:
            return None
        value = self.coordinator.data.get("qpiri", {}).get("max_charging_current")
        return str(int(value)) if value is not None else None

    async def async_select_option(self, option: str) -> None:
        try:
            await self.coordinator.async_set_max_charging_current(int(option))
        except AxpertCommandRejectedError as err:
            # NAK réel de l'onduleur (palier non accepté) : erreur
            # attendue et informative pour l'utilisateur, pas une
            # exception inattendue à laisser remonter brute jusqu'à
            # l'UI (voir logs du 20/07, MCHGC010/020/030 rejetés).
            raise HomeAssistantError(
                f"L'onduleur a refusé le courant de charge max {option}A "
                f"(réponse NAK). Ce palier n'est peut-être pas supporté "
                f"par ce modèle malgré la découverte QMCHGCR."
            ) from err


class AxpertMaxUtilityChargingCurrentSelect(AxpertEntity, SelectEntity):
    _attr_icon = "mdi:current-ac"

    def __init__(self, coordinator: AxpertCoordinator) -> None:
        super().__init__(coordinator, "max_utility_charging_current_select")
        self._attr_name = "Axpert Max Utility Charging Current"

    @property
    def options(self) -> list[str]:
        discovered = self.coordinator.supported_max_utility_charging_currents
        if discovered:
            return [str(v) for v in discovered]
        current = self.current_option
        return [current] if current is not None else []

    @property
    def current_option(self) -> str | None:
        if self.coordinator.data is None:
            return None
        value = self.coordinator.data.get("qpiri", {}).get("max_ac_charging_current")
        return str(int(value)) if value is not None else None

    async def async_select_option(self, option: str) -> None:
        try:
            await self.coordinator.async_set_max_utility_charging_current(int(option))
        except AxpertCommandRejectedError as err:
            raise HomeAssistantError(
                f"L'onduleur a refusé le courant de charge réseau max {option}A "
                f"(réponse NAK). Ce palier n'est peut-être pas supporté "
                f"par ce modèle malgré la découverte QMCHGCR."
            ) from err
