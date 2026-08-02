"""Constantes AxpertEMS."""

from typing import Final

DOMAIN: Final = "axpertems"

CONF_PORT: Final = "port"
CONF_BAUDRATE: Final = "baudrate"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_NAME: Final = "name"

DEFAULT_NAME: Final = "Axpert"
DEFAULT_BAUDRATE: Final = 2400
DEFAULT_SCAN_INTERVAL: Final = 30  # secondes

CONF_SOC_THRESHOLD: Final = "battery_soc_threshold"
CONF_BATTERY_CRITICAL_THRESHOLD: Final = "battery_critical_threshold"
CONF_DEFICIT_DELAY_ON: Final = "deficit_delay_on_minutes"
CONF_DEFICIT_DELAY_OFF: Final = "deficit_delay_off_minutes"
CONF_NIGHT_START: Final = "night_start"
CONF_SOC_THRESHOLD_SHEDDING: Final = "battery_soc_threshold_shedding"
CONF_RESTORE_DELAY_TIER1: Final = "restore_delay_tier1_seconds"
CONF_RESTORE_DELAY_TIER2: Final = "restore_delay_tier2_seconds"
CONF_RESTORE_DELAY_TIER3: Final = "restore_delay_tier3_seconds"

DEFAULT_OPTIONS: Final[dict[str, int | float | str]] = {
    CONF_SOC_THRESHOLD: 35,
    CONF_BATTERY_CRITICAL_THRESHOLD: 20,
    CONF_DEFICIT_DELAY_ON: 10,
    CONF_DEFICIT_DELAY_OFF: 5,
    CONF_NIGHT_START: "23:00",
    CONF_SOC_THRESHOLD_SHEDDING: 35,
    CONF_RESTORE_DELAY_TIER1: 180,
    CONF_RESTORE_DELAY_TIER2: 5,
    CONF_RESTORE_DELAY_TIER3: 5,
}