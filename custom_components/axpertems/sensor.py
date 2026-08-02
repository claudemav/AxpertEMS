"""Capteurs numériques exposés par l'onduleur, capteurs de configuration
et capteurs de diagnostic de la liaison série."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_BATTERY_CRITICAL_THRESHOLD,
    CONF_DEFICIT_DELAY_OFF,
    CONF_DEFICIT_DELAY_ON,
    CONF_NIGHT_START,
    CONF_RESTORE_DELAY_TIER1,
    CONF_RESTORE_DELAY_TIER2,
    CONF_RESTORE_DELAY_TIER3,
    CONF_SOC_THRESHOLD,
    CONF_SOC_THRESHOLD_SHEDDING,
    DEFAULT_OPTIONS,
    DOMAIN,
)
from .coordinator import AxpertCoordinator
from .entity import AxpertDiagnosticEntity, AxpertEntity


@dataclass(frozen=True, kw_only=True)
class AxpertSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]


SENSOR_DESCRIPTIONS: tuple[AxpertSensorDescription, ...] = (
    AxpertSensorDescription(
        key="grid_voltage", translation_key="grid_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE, state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["qpigs"].get("ac_input_voltage"),
    ),
    AxpertSensorDescription(
        key="output_voltage", translation_key="output_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE, state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["qpigs"].get("ac_output_voltage"),
    ),
    AxpertSensorDescription(
        key="output_power", translation_key="output_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["qpigs"].get("ac_output_active_power"),
    ),
    AxpertSensorDescription(
        key="output_load", translation_key="output_load",
        native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["qpigs"].get("ac_output_load"),
    ),
    AxpertSensorDescription(
        key="battery_voltage", translation_key="battery_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE, state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["qpigs"].get("battery_voltage"),
    ),
    AxpertSensorDescription(
        key="battery_capacity", translation_key="battery_capacity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY, state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["qpigs"].get("battery_capacity"),
    ),
    AxpertSensorDescription(
        key="battery_charging_current", translation_key="battery_charging_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT, state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["qpigs"].get("battery_charging_current"),
    ),
    AxpertSensorDescription(
        key="battery_discharge_current", translation_key="battery_discharge_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT, state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["qpigs"].get("battery_discharge_current"),
    ),
    AxpertSensorDescription(
        key="pv_voltage", translation_key="pv_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE, state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["qpigs"].get("pv_input_voltage"),
    ),
    AxpertSensorDescription(
        key="pv_current", translation_key="pv_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT, state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["qpigs"].get("pv_input_current_for_battery"),
    ),
    AxpertSensorDescription(
        key="pv_power", translation_key="pv_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["qpigs"].get("pv_input_power"),
    ),
    AxpertSensorDescription(
        key="inverter_temperature", translation_key="inverter_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE, state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["qpigs"].get("inverter_heat_sink_temperature"),
    ),
    AxpertSensorDescription(
        key="device_mode", translation_key="device_mode", icon="mdi:state-machine",
        value_fn=lambda data: data["qmod"].get("device_mode"),
    ),
)


@dataclass(frozen=True, kw_only=True)
class AxpertConfigSensorDescription(SensorEntityDescription):
    option_key: str
    default: Any


CONFIG_SENSOR_DESCRIPTIONS: tuple[AxpertConfigSensorDescription, ...] = (
    AxpertConfigSensorDescription(
        key="config_soc_threshold", translation_key="config_soc_threshold",
        icon="mdi:battery-heart-variant", native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        option_key=CONF_SOC_THRESHOLD, default=DEFAULT_OPTIONS[CONF_SOC_THRESHOLD],
    ),
    AxpertConfigSensorDescription(
        key="config_battery_critical_threshold", translation_key="config_battery_critical_threshold",
        icon="mdi:battery-alert", native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        option_key=CONF_BATTERY_CRITICAL_THRESHOLD, default=DEFAULT_OPTIONS[CONF_BATTERY_CRITICAL_THRESHOLD],
    ),
    AxpertConfigSensorDescription(
        key="config_night_start", translation_key="config_night_start",
        icon="mdi:clock-time-eleven", entity_category=EntityCategory.DIAGNOSTIC,
        option_key=CONF_NIGHT_START, default=DEFAULT_OPTIONS[CONF_NIGHT_START],
    ),
    AxpertConfigSensorDescription(
        key="config_deficit_delay_on", translation_key="config_deficit_delay_on",
        icon="mdi:timer-sand", native_unit_of_measurement=UnitOfTime.MINUTES,
        entity_category=EntityCategory.DIAGNOSTIC,
        option_key=CONF_DEFICIT_DELAY_ON, default=DEFAULT_OPTIONS[CONF_DEFICIT_DELAY_ON],
    ),
    AxpertConfigSensorDescription(
        key="config_deficit_delay_off", translation_key="config_deficit_delay_off",
        icon="mdi:timer-sand", native_unit_of_measurement=UnitOfTime.MINUTES,
        entity_category=EntityCategory.DIAGNOSTIC,
        option_key=CONF_DEFICIT_DELAY_OFF, default=DEFAULT_OPTIONS[CONF_DEFICIT_DELAY_OFF],
    ),
    AxpertConfigSensorDescription(
        key="config_soc_threshold_shedding", translation_key="config_soc_threshold_shedding",
        icon="mdi:battery-arrow-down", native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        option_key=CONF_SOC_THRESHOLD_SHEDDING, default=DEFAULT_OPTIONS[CONF_SOC_THRESHOLD_SHEDDING],
    ),
    AxpertConfigSensorDescription(
        key="config_restore_delay_tier1", translation_key="config_restore_delay_tier1",
        icon="mdi:timer-sand", native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_category=EntityCategory.DIAGNOSTIC,
        option_key=CONF_RESTORE_DELAY_TIER1, default=DEFAULT_OPTIONS[CONF_RESTORE_DELAY_TIER1],
    ),
    AxpertConfigSensorDescription(
        key="config_restore_delay_tier2", translation_key="config_restore_delay_tier2",
        icon="mdi:timer-sand", native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_category=EntityCategory.DIAGNOSTIC,
        option_key=CONF_RESTORE_DELAY_TIER2, default=DEFAULT_OPTIONS[CONF_RESTORE_DELAY_TIER2],
    ),
    AxpertConfigSensorDescription(
        key="config_restore_delay_tier3", translation_key="config_restore_delay_tier3",
        icon="mdi:timer-sand", native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_category=EntityCategory.DIAGNOSTIC,
        option_key=CONF_RESTORE_DELAY_TIER3, default=DEFAULT_OPTIONS[CONF_RESTORE_DELAY_TIER3],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: AxpertCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = [
        AxpertSensor(coordinator, entry, description) for description in SENSOR_DESCRIPTIONS
    ]
    entities.extend(
        AxpertConfigSensor(coordinator, entry, description)
        for description in CONFIG_SENSOR_DESCRIPTIONS
    )
    entities.append(AxpertConsecutiveFailuresSensor(coordinator, entry))
    entities.append(AxpertLastSuccessSensor(coordinator, entry))
    entities.append(AxpertLastErrorSensor(coordinator, entry))
    entities.append(AxpertPartialErrorSensor(coordinator, entry))
    async_add_entities(entities)


class AxpertSensor(AxpertEntity, SensorEntity):
    entity_description: AxpertSensorDescription

    def __init__(
        self, coordinator: AxpertCoordinator, entry: ConfigEntry, description: AxpertSensorDescription
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class AxpertConfigSensor(AxpertEntity, SensorEntity):
    entity_description: AxpertConfigSensorDescription

    def __init__(
        self,
        coordinator: AxpertCoordinator,
        entry: ConfigEntry,
        description: AxpertConfigSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description
        self._entry = entry

    @property
    def native_value(self) -> Any:
        return self._entry.options.get(
            self.entity_description.option_key, self.entity_description.default
        )


class AxpertConsecutiveFailuresSensor(AxpertDiagnosticEntity, SensorEntity):
    _attr_translation_key = "consecutive_failures"
    _attr_icon = "mdi:counter"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: AxpertCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "consecutive_failures")

    @property
    def native_value(self) -> Any:
        return self.coordinator.consecutive_failures


class AxpertLastSuccessSensor(AxpertDiagnosticEntity, SensorEntity):
    _attr_translation_key = "last_success"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:check-circle-outline"

    def __init__(self, coordinator: AxpertCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "last_success")

    @property
    def native_value(self) -> Any:
        return self.coordinator.last_success


class AxpertLastErrorSensor(AxpertDiagnosticEntity, SensorEntity):
    _attr_translation_key = "last_error"
    _attr_icon = "mdi:alert-circle-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: AxpertCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "last_error")

    @property
    def native_value(self) -> Any:
        # None plutôt qu'une chaîne "Aucune" : convention HA pour un
        # capteur diagnostic, évite de polluer l'historique d'une valeur
        # traduite répétée. L'UI affiche déjà "—" pour un état vide.
        return self.coordinator.last_error


class AxpertPartialErrorSensor(AxpertDiagnosticEntity, SensorEntity):
    _attr_translation_key = "partial_error"
    _attr_icon = "mdi:alert-circle-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: AxpertCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "partial_error")

    @property
    def native_value(self) -> Any:
        return self.coordinator.partial_error