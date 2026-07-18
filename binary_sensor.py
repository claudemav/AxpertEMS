"""Capteurs binaires dérivés des bits de statut de l'onduleur (QPIGS)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AxpertCoordinator
from .entity import AxpertEntity


@dataclass(frozen=True, kw_only=True)
class AxpertBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], bool | None]


BINARY_SENSOR_DESCRIPTIONS: tuple[AxpertBinarySensorDescription, ...] = (
    AxpertBinarySensorDescription(
        key="ac_charging",
        name="Axpert AC Charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda data: data["qpigs"].get("is_ac_charging_on"),
    ),
    AxpertBinarySensorDescription(
        key="scc_charging",
        name="Axpert SCC Charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda data: data["qpigs"].get("is_scc_charging_on"),
    ),
    AxpertBinarySensorDescription(
        key="load_on",
        name="Axpert Load On",
        device_class=BinarySensorDeviceClass.POWER,
        value_fn=lambda data: data["qpigs"].get("is_load_on"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: AxpertCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        AxpertBinarySensor(coordinator, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    )


class AxpertBinarySensor(AxpertEntity, BinarySensorEntity):
    entity_description: AxpertBinarySensorDescription

    def __init__(
        self, coordinator: AxpertCoordinator, description: AxpertBinarySensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
