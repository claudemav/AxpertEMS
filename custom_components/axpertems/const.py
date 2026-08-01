"""Constantes AxpertEMS."""

DOMAIN = "axpertems"

CONF_PORT = "port"
CONF_BAUDRATE = "baudrate"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_BAUDRATE = 2400
DEFAULT_SCAN_INTERVAL = 30  # secondes

CONF_SOC_THRESHOLD = "battery_soc_threshold"
CONF_BATTERY_CRITICAL_THRESHOLD = "battery_critical_threshold"
CONF_DEFICIT_DELAY_ON = "deficit_delay_on_minutes"
CONF_DEFICIT_DELAY_OFF = "deficit_delay_off_minutes"
CONF_NIGHT_START = "night_start"

# Ajoutés pour le point #7 : le YAML de délestage les référence depuis
# plusieurs versions mais ils n'existaient nulle part côté intégration —
# le YAML retombait silencieusement sur ses valeurs de repli.
CONF_SOC_THRESHOLD_SHEDDING = "battery_soc_threshold_shedding"
CONF_RESTORE_DELAY_TIER1 = "restore_delay_tier1_seconds"
CONF_RESTORE_DELAY_TIER2 = "restore_delay_tier2_seconds"
CONF_RESTORE_DELAY_TIER3 = "restore_delay_tier3_seconds"

DEFAULT_OPTIONS: dict = {
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