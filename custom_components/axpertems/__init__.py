"""AxpertEMS — intégration Home Assistant native pour onduleurs Axpert/Voltronic."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_BAUDRATE,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    DEFAULT_BAUDRATE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import AxpertCoordinator
from .exceptions import AxpertError

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor", "binary_sensor", "select"]

SERVICE_SEND_RAW_COMMAND = "send_raw_command"
ATTR_COMMAND = "command"

SEND_RAW_COMMAND_SCHEMA = vol.Schema({vol.Required(ATTR_COMMAND): cv.string})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = AxpertCoordinator(
        hass,
        port=entry.data[CONF_PORT],
        baudrate=entry.data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE),
        scan_interval=entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )

    await coordinator.async_config_entry_first_refresh()
    await coordinator.async_fetch_supported_currents()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Service de diagnostic : envoyer une commande PI30 brute et voir la
    # réponse exacte (ACK/NAK/payload) — utile pour identifier un format
    # de commande divergent sur un clone (ex: MCHGC40 vs MCHGC040).
    # Enregistré une seule fois même si plusieurs entrées de config
    # existent ; cible la première trouvée dans hass.data[DOMAIN].
    if not hass.services.has_service(DOMAIN, SERVICE_SEND_RAW_COMMAND):

        async def _handle_send_raw_command(call: ServiceCall) -> ServiceResponse:
            command = call.data[ATTR_COMMAND]
            target_coordinator: AxpertCoordinator = next(
                iter(hass.data[DOMAIN].values())
            )["coordinator"]
            try:
                response = await target_coordinator.async_send_raw(command)
            except AxpertError as err:
                raise HomeAssistantError(str(err)) from err
            return {"command": command, "response": response}

        hass.services.async_register(
            DOMAIN,
            SERVICE_SEND_RAW_COMMAND,
            _handle_send_raw_command,
            schema=SEND_RAW_COMMAND_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        stored = hass.data[DOMAIN].pop(entry.entry_id)
        await stored["coordinator"].async_shutdown()
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_SEND_RAW_COMMAND)
    return unload_ok
