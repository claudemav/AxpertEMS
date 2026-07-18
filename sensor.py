"""Capteurs numériques exposés par l'onduleur (remplace axpert_sensors.yaml)."""

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
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_BATTERY_CRITICAL_THRESHOLD,
    CONF_DEFICIT_DELAY_OFF,
    CONF_DEFICIT_DELAY_ON,
    CONF_NIGHT_START,
    CONF_SOC_THRESHOLD,
    DEFAULT_OPTIONS,
    DOMAIN,
)
from .coordinator import AxpertCoordinator
from .engine import AxpertEnergyManager
from .entity import AxpertEntity


@dataclass(frozen=True, kw_only=True)
class AxpertSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]


SENSOR_DESCRIPTIONS: tuple[AxpertSensorDescription, ...] = (
    AxpertSensorDescription(
        key="grid_voltage",
        name="Axpert Grid Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["qpigs"].get("ac_input_voltage"),
    ),
    AxpertSensorDescription(
        key="output_voltage",
        name="Axpert Output Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["qpigs"].get("ac_output_voltage"),
    ),
    AxpertSensorDescription(
        key="output_power",
        name="Axpert Output Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["qpigs"].get("ac_output_active_power"),
    ),
    AxpertSensorDescription(
        key="output_load",
        name="Axpert Output Load",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["qpigs"].get("ac_output_load"),
    ),
    AxpertSensorDescription(
        key="battery_voltage",
        name="Axpert Battery Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["qpigs"].get("battery_voltage"),
    ),
    AxpertSensorDescription(
        key="battery_capacity",
        name="Axpert Battery Capacity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["qpigs"].get("battery_capacity"),
    ),
    AxpertSensorDescription(
        key="battery_charging_current",
        name="Axpert Battery Charging Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["qpigs"].get("battery_charging_current"),
    ),
    AxpertSensorDescription(
        key="battery_discharge_current",
        name="Axpert Battery Discharge Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["qpigs"].get("battery_discharge_current"),
    ),
    AxpertSensorDescription(
        key="pv_voltage",
        name="Axpert PV Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["qpigs"].get("pv_input_voltage"),
    ),
    AxpertSensorDescription(
        key="pv_current",
        name="Axpert PV Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["qpigs"].get("pv_input_current_for_battery"),
    ),
    AxpertSensorDescription(
        key="pv_power",
        name="Axpert PV Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["qpigs"].get("pv_input_power"),
    ),
    AxpertSensorDescription(
        key="inverter_temperature",
        name="Axpert Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["qpigs"].get("inverter_heat_sink_temperature"),
    ),
    AxpertSensorDescription(
        key="device_mode",
        name="Axpert Mode",
        icon="mdi:state-machine",
        value_fn=lambda data: data["qmod"].get("device_mode"),
    ),
)


@dataclass(frozen=True, kw_only=True)
class AxpertConfigSensorDescription(SensorEntityDescription):
    option_key: str
    default: Any


CONFIG_SENSOR_DESCRIPTIONS: tuple[AxpertConfigSensorDescription, ...] = (
    AxpertConfigSensorDescription(
        key="config_soc_threshold",
        name="Axpert Config SOC Threshold",
        icon="mdi:battery-heart-variant",
        native_unit_of_measurement=PERCENTAGE,
        option_key=CONF_SOC_THRESHOLD,
        default=DEFAULT_OPTIONS[CONF_SOC_THRESHOLD],
    ),
    AxpertConfigSensorDescription(
        key="config_battery_critical_threshold",
        name="Axpert Config Battery Critical Threshold",
        icon="mdi:battery-alert",
        native_unit_of_measurement=PERCENTAGE,
        option_key=CONF_BATTERY_CRITICAL_THRESHOLD,
        default=DEFAULT_OPTIONS[CONF_BATTERY_CRITICAL_THRESHOLD],
    ),
    AxpertConfigSensorDescription(
        key="config_night_start",
        name="Axpert Config Night Start",
        icon="mdi:clock-time-eleven",
        option_key=CONF_NIGHT_START,
        default=DEFAULT_OPTIONS[CONF_NIGHT_START],
    ),
    AxpertConfigSensorDescription(
        key="config_deficit_delay_on",
        name="Axpert Config Deficit Delay On",
        icon="mdi:timer-sand",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        option_key=CONF_DEFICIT_DELAY_ON,
        default=DEFAULT_OPTIONS[CONF_DEFICIT_DELAY_ON],
    ),
    AxpertConfigSensorDescription(
        key="config_deficit_delay_off",
        name="Axpert Config Deficit Delay Off",
        icon="mdi:timer-sand",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        option_key=CONF_DEFICIT_DELAY_OFF,
        default=DEFAULT_OPTIONS[CONF_DEFICIT_DELAY_OFF],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: AxpertCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    engine: AxpertEnergyManager = hass.data[DOMAIN][entry.entry_id]["engine"]
    entities = [
        AxpertSensor(coordinator, description) for description in SENSOR_DESCRIPTIONS
    ]
    entities.append(AxpertLastDecisionSensor(coordinator, engine))
    entities.extend(
        AxpertConfigSensor(coordinator, entry, description)
        for description in CONFIG_SENSOR_DESCRIPTIONS
    )
    async_add_entities(entities)


class AxpertSensor(AxpertEntity, SensorEntity):
    entity_description: AxpertSensorDescription

    def __init__(
        self, coordinator: AxpertCoordinator, description: AxpertSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class AxpertLastDecisionSensor(AxpertEntity, SensorEntity):
    """Journal des N dernières décisions de l'EMS ('16:42 Délestage de Frigo'...).

    Ne lit pas coordinator.data (comme les autres capteurs) mais
    engine.history directement, et s'abonne à l'engine pour se rafraîchir
    dès qu'une décision est prise, sans attendre le prochain cycle de poll.
    """

    _attr_icon = "mdi:notebook-outline"

    def __init__(self, coordinator: AxpertCoordinator, engine: AxpertEnergyManager) -> None:
        super().__init__(coordinator, "last_decision")
        self._attr_name = "Axpert Last Decision"
        self._engine = engine

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._engine.async_add_decision_listener(self.async_write_ha_state)

    @property
    def native_value(self) -> Any:
        if not self._engine.history:
            return "Aucune décision récente"
        return self._engine.history[-1]["message"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"historique": list(self._engine.history)}


class AxpertConfigSensor(AxpertEntity, SensorEntity):
    """Expose une valeur de l'Options Flow comme capteur lisible par les
    automations (ex: sensor.axpert_config_soc_threshold).

    Se rafraîchit à chaque cycle du coordinator (comme les autres capteurs),
    ce qui suffit largement pour un réglage qu'on ne change qu'occasionnellement
    via Configurer — pas besoin d'un listener dédié aux options.
    """

    entity_description: AxpertConfigSensorDescription

    def __init__(
        self,
        coordinator: AxpertCoordinator,
        entry: ConfigEntry,
        description: AxpertConfigSensorDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._entry = entry

    @property
    def native_value(self) -> Any:
        return self._entry.options.get(
            self.entity_description.option_key, self.entity_description.default
        )
