"""Diagnostics — Paramètres > Appareils et services > AxpertEMS > ⋮ > Télécharger les diagnostics."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    stored = hass.data[DOMAIN][entry.entry_id]
    coordinator = stored["coordinator"]

    return {
        "entry_data": {
            "port": entry.data.get("port"),
            "baudrate": entry.data.get("baudrate"),
            "scan_interval": entry.data.get("scan_interval"),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "data": coordinator.data,
            "supported_max_charging_currents": coordinator.supported_max_charging_currents,
            "supported_max_utility_charging_currents": coordinator.supported_max_utility_charging_currents,
            "consecutive_failures": coordinator.consecutive_failures,
            "last_success": coordinator.last_success,
            "last_error": coordinator.last_error,
            "data_stale": coordinator.data_stale,
            "qmod_stale": coordinator.qmod_stale,
            "qmod_last_error": coordinator.qmod_last_error,
            "qpiri_stale": coordinator.qpiri_stale,
            "qpiri_last_error": coordinator.qpiri_last_error,
            "partial_error": coordinator.partial_error,
        },
    }
