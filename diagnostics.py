"""Diagnostics — Paramètres > Appareils et services > AxpertEMS > ⋮ > Télécharger les diagnostics.

Rien de sensible à rédiger ici (pas de token, pas de mot de passe : juste
un port série et des mesures électriques), donc pas de logique de
redaction particulière.
"""

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
    engine = stored["engine"]

    return {
        "entry_data": {
            "port": entry.data.get("port"),
            "baudrate": entry.data.get("baudrate"),
            "scan_interval": entry.data.get("scan_interval"),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "data": coordinator.data,
        },
        "engine": {
            "mode": engine.mode,
            "history": list(engine.history),
        },
    }
