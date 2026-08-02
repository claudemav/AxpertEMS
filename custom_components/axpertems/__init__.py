"""AxpertEMS — intégration Home Assistant native pour onduleurs Axpert/Voltronic."""

from __future__ import annotations

import logging
import re

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, device_registry as dr

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
ATTR_DEVICE_ID = "device_id"

MAX_COMMAND_LENGTH = 32
# Commandes PI30 : ASCII imprimable uniquement (lettres, chiffres, quelques
# symboles utilisés par le protocole). Pas de CR/LF/contrôle — ceux-ci sont
# ajoutés par build_command(), jamais fournis par l'appelant.
_COMMAND_PATTERN = re.compile(r"^[A-Za-z0-9]+$")

SEND_RAW_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_COMMAND): cv.string,
        vol.Optional(ATTR_DEVICE_ID): cv.string,
    }
)


def _normalize_command(raw: str) -> str:
    """Nettoie et valide une commande brute avant envoi série.

    Rejette tout ce qui n'est pas un mot ASCII alphanumérique simple —
    en particulier tout CR/LF injecté manuellement (qui terminerait la
    trame prématurément ou l'invaliderait), tout caractère de contrôle,
    et toute tentative de faire passer plusieurs commandes en une seule
    chaîne."""
    command = raw.strip().upper()
    if not command:
        raise HomeAssistantError("Empty command.")
    if len(command) > MAX_COMMAND_LENGTH:
        raise HomeAssistantError(
            f"Command too long (max {MAX_COMMAND_LENGTH} characters)."
        )
    if not _COMMAND_PATTERN.match(command):
        raise HomeAssistantError(
            "Invalid command: only ASCII letters and digits are allowed "
            "(no CR/LF, spaces, or control characters)."
        )
    return command


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = AxpertCoordinator(
        hass,
        entry,
        port=entry.data[CONF_PORT],
        baudrate=entry.data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE),
        scan_interval=entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Découverte des paliers de courant : lancée après les plateformes
    # pour ne pas retarder l'installation initiale (jusqu'à ~12s dans le
    # pire cas). Rattachée au cycle de vie de l'entrée via
    # entry.async_create_background_task : Home Assistant l'annule
    # proprement si l'entrée est déchargée pendant l'exécution, évitant
    # tout usage du client série après fermeture du port.
    entry.async_create_background_task(
        hass,
        coordinator.async_fetch_supported_currents(),
        name=f"{DOMAIN}_fetch_supported_currents_{entry.entry_id}",
    )

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    if not hass.services.has_service(DOMAIN, SERVICE_SEND_RAW_COMMAND):

        async def _handle_send_raw_command(call: ServiceCall) -> ServiceResponse:
            command = _normalize_command(call.data[ATTR_COMMAND])
            target_coordinator = _resolve_coordinator(hass, call.data.get(ATTR_DEVICE_ID))
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


def _resolve_coordinator(hass: HomeAssistant, device_id: str | None) -> AxpertCoordinator:
    """Résout le coordinator ciblé par le service.

    Si device_id est fourni, retrouve l'entrée de config correspondante
    via le registre d'appareils. Sinon, s'il n'y a qu'un seul onduleur
    configuré, l'utilise par défaut. Avec plusieurs onduleurs et aucun
    device_id fourni, lève une erreur explicite plutôt que de cibler
    arbitrairement le premier trouvé.
    """
    entries = hass.data.get(DOMAIN, {})

    if device_id:
        device_registry = dr.async_get(hass)
        device = device_registry.async_get(device_id)
        if device is None:
            raise HomeAssistantError(f"Device not found: {device_id}")
        for entry_id in device.config_entries:
            if entry_id in entries:
                return entries[entry_id]["coordinator"]
        raise HomeAssistantError(
            f"Device {device_id} does not correspond to any configured AxpertEMS inverter"
        )

    if len(entries) == 1:
        return next(iter(entries.values()))["coordinator"]

    if len(entries) == 0:
        raise HomeAssistantError("No AxpertEMS inverter configured")

    raise HomeAssistantError(
        "Multiple AxpertEMS inverters configured: specify device_id to choose which one to target"
    )


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        stored = hass.data[DOMAIN].pop(entry.entry_id)
        await stored["coordinator"].async_shutdown()
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_SEND_RAW_COMMAND)
    return unload_ok