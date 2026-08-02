"""Capteurs binaires : bits de statut QPIGS + santé de la liaison série."""

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
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AxpertCoordinator
from .entity import AxpertDiagnosticEntity, AxpertEntity


@dataclass(frozen=True, kw_only=True)
class AxpertBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], bool | None]


BINARY_SENSOR_DESCRIPTIONS: tuple[AxpertBinarySensorDescription, ...] = (
    AxpertBinarySensorDescription(
        key="ac_charging", translation_key="ac_charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda data: data["qpigs"].get("is_ac_charging_on"),
    ),
    AxpertBinarySensorDescription(
        key="scc_charging", translation_key="scc_charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda data: data["qpigs"].get("is_scc_charging_on"),
    ),
    AxpertBinarySensorDescription(
        key="load_on", translation_key="load_on",
        device_class=BinarySensorDeviceClass.POWER,
        value_fn=lambda data: data["qpigs"].get("is_load_on"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: AxpertCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = [
        AxpertBinarySensor(coordinator, entry, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    ]
    entities.append(AxpertCommunicationBinarySensor(coordinator, entry))
    entities.append(AxpertDataStaleBinarySensor(coordinator, entry))
    entities.append(AxpertQmodStaleBinarySensor(coordinator, entry))
    entities.append(AxpertQpiriStaleBinarySensor(coordinator, entry))
    async_add_entities(entities)


class AxpertBinarySensor(AxpertEntity, BinarySensorEntity):
    entity_description: AxpertBinarySensorDescription

    def __init__(
        self,
        coordinator: AxpertCoordinator,
        entry: ConfigEntry,
        description: AxpertBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class AxpertCommunicationBinarySensor(AxpertDiagnosticEntity, BinarySensorEntity):
    _attr_translation_key = "communication"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: AxpertCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "communication")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.last_update_success and not self.coordinator.data_stale


class AxpertDataStaleBinarySensor(AxpertDiagnosticEntity, BinarySensorEntity):
    _attr_translation_key = "data_stale"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: AxpertCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "data_stale")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data_stale


class AxpertQmodStaleBinarySensor(AxpertDiagnosticEntity, BinarySensorEntity):
    _attr_translation_key = "qmod_stale"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: AxpertCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "qmod_stale")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.qmod_stale


class AxpertQpiriStaleBinarySensor(AxpertDiagnosticEntity, BinarySensorEntity):
    _attr_translation_key = "qpiri_stale"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: AxpertCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "qpiri_stale")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.qpiri_stale