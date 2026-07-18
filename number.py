"""Courants de charge max — MCHGC (toutes sources) et MUCHGC (réseau).

L'onduleur n'accepte que certains paliers spécifiques à son modèle (pas
n'importe quelle valeur entière) — une valeur hors palier est rejetée
proprement (NAK -> AxpertCommandRejectedError), sans rien casser côté HA.
Les bornes min/max ci-dessous sont volontairement larges (0-100A) ; c'est
l'onduleur qui a le dernier mot sur ce qu'il accepte réellement.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfElectricCurrent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AxpertCoordinator
from .entity import AxpertEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: AxpertCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        [
            AxpertMaxChargingCurrentNumber(coordinator),
            AxpertMaxUtilityChargingCurrentNumber(coordinator),
        ]
    )


class AxpertMaxChargingCurrentNumber(AxpertEntity, NumberEntity):
    """MCHGC — courant de charge max, toutes sources confondues."""

    _attr_icon = "mdi:current-dc"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

    def __init__(self, coordinator: AxpertCoordinator) -> None:
        super().__init__(coordinator, "max_charging_current")
        self._attr_name = "Axpert Max Charging Current"

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data["qpiri"].get("max_charging_current")

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_max_charging_current(int(value))


class AxpertMaxUtilityChargingCurrentNumber(AxpertEntity, NumberEntity):
    """MUCHGC — courant de charge max sur réseau uniquement."""

    _attr_icon = "mdi:current-ac"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

    def __init__(self, coordinator: AxpertCoordinator) -> None:
        super().__init__(coordinator, "max_utility_charging_current")
        self._attr_name = "Axpert Max Utility Charging Current"

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data["qpiri"].get("max_ac_charging_current")

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_max_utility_charging_current(int(value))
