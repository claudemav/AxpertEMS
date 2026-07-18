"""AxpertEMS — intégration Home Assistant native pour onduleurs Axpert/Voltronic."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_BAUDRATE,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    DEFAULT_BAUDRATE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import AxpertCoordinator
from .engine import AxpertEnergyManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor", "binary_sensor", "select", "number"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = AxpertCoordinator(
        hass,
        port=entry.data[CONF_PORT],
        baudrate=entry.data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE),
        scan_interval=entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )

    # Premier poll synchrone : si l'onduleur ne répond pas, l'entrée de
    # config passe en état "retry" au lieu de charger des entités mortes.
    await coordinator.async_config_entry_first_refresh()

    engine = AxpertEnergyManager(hass, coordinator, options=entry.options)
    # DÉSACTIVÉ EN RÉSERVE : le "cerveau" est maintenant porté par des
    # automations YAML (voir packages/axpert_brain_*.yaml) pour plus de
    # flexibilité d'ajustement. engine.async_setup() n'est PAS appelé :
    # l'objet existe encore (le select EMS Mode et le capteur Last Decision
    # en dépendent toujours pour exister), mais il n'écoute plus le
    # coordinator et ne prend plus aucune décision. Pour réactiver un jour :
    # décommenter la ligne suivante et redémarrer.
    # engine.async_setup()

    # Options Flow -> ici, à chaud, sans redémarrage de HA.
    remove_options_listener = entry.add_update_listener(_async_options_updated)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "engine": engine,
        "remove_options_listener": remove_options_listener,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    stored = hass.data[DOMAIN][entry.entry_id]
    stored["engine"].async_update_options(entry.options)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        stored = hass.data[DOMAIN].pop(entry.entry_id)
        stored["remove_options_listener"]()
        stored["engine"].async_unload()
        await stored["coordinator"].async_shutdown()
    return unload_ok
