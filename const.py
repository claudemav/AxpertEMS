"""Constantes AxpertEMS."""

DOMAIN = "axpertems"

CONF_PORT = "port"
CONF_BAUDRATE = "baudrate"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_BAUDRATE = 2400
DEFAULT_SCAN_INTERVAL = 30  # secondes — cadence validée avec l'utilisateur

# --- Options (modifiables sans redémarrage, via Configurer) ---------------

CONF_LOADS = "loads"
CONF_SOC_THRESHOLD = "battery_soc_threshold"
CONF_BATTERY_CRITICAL_THRESHOLD = "battery_critical_threshold"
CONF_DEFICIT_DELAY_ON = "deficit_delay_on_minutes"
CONF_DEFICIT_DELAY_OFF = "deficit_delay_off_minutes"
CONF_NIGHT_START = "night_start"

DEFAULT_LOADS_OPTION: list[dict] = [
    {"entity_id": "switch.frigo", "name": "Frigo", "tier": 1, "restore_delay": 180},
    {"entity_id": "switch.tele", "name": "Télé", "tier": 2, "restore_delay": 5},
]

DEFAULT_OPTIONS: dict = {
    CONF_SOC_THRESHOLD: 35,
    CONF_BATTERY_CRITICAL_THRESHOLD: 20,
    CONF_DEFICIT_DELAY_ON: 10,
    CONF_DEFICIT_DELAY_OFF: 5,
    CONF_NIGHT_START: "23:00",
    CONF_LOADS: DEFAULT_LOADS_OPTION,
}
