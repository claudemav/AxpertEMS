"""Config flow : formulaire UI, aucune ligne de YAML nécessaire.

Contient aussi l'OptionsFlow : seuils et liste de charges modifiables
depuis Paramètres > AxpertEMS > Configurer, appliqués À CHAUD par
engine.async_update_options() — aucun redémarrage de HA requis.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .axpert import AxpertClient
from .const import (
    CONF_BATTERY_CRITICAL_THRESHOLD,
    CONF_BAUDRATE,
    CONF_DEFICIT_DELAY_OFF,
    CONF_DEFICIT_DELAY_ON,
    CONF_LOADS,
    CONF_NIGHT_START,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_SOC_THRESHOLD,
    DEFAULT_BAUDRATE,
    DEFAULT_OPTIONS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .exceptions import AxpertError

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PORT, default="/dev/ttyUSB0"): str,
        vol.Optional(CONF_BAUDRATE, default=DEFAULT_BAUDRATE): int,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): int,
    }
)


def _test_connection(port: str, baudrate: int) -> None:
    """Ouvre le port et fait un aller-retour QMOD pour valider la config.

    Exécuté dans l'executor HA (bloquant), jamais dans la boucle async.
    """
    with AxpertClient(port, baudrate=baudrate) as client:
        client.get_qmod()


class AxpertEMSConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Un seul écran : port série + options avancées repliables."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_PORT])
            self._abort_if_unique_id_configured()

            try:
                await self.hass.async_add_executor_job(
                    _test_connection, user_input[CONF_PORT], user_input[CONF_BAUDRATE]
                )
            except AxpertError as err:
                _LOGGER.debug("Échec de connexion pendant le config_flow : %s", err)
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"Axpert ({user_input[CONF_PORT]})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "AxpertEMSOptionsFlow":
        return AxpertEMSOptionsFlow()


class AxpertEMSOptionsFlow(config_entries.OptionsFlow):
    """Menu : seuils, ou gestion des charges (ajouter/retirer).

    NOTE : écrit pour la convention récente où `self.config_entry` est
    injecté automatiquement par le framework (pas de __init__ ici). Si tu
    es sur une version de HA antérieure à ~2024.12, il faudra peut-être
    réintroduire un __init__(self, config_entry) qui fait
    self.config_entry = config_entry — dis-le-moi si le flow ne s'ouvre pas.
    """

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["thresholds", "loads_menu"],
        )

    # -- Seuils ------------------------------------------------------------

    async def async_step_thresholds(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        current = {**DEFAULT_OPTIONS, **self.config_entry.options}

        if user_input is not None:
            new_options = {**self.config_entry.options, **user_input}
            return self.async_create_entry(title="", data=new_options)

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SOC_THRESHOLD, default=current[CONF_SOC_THRESHOLD]
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_BATTERY_CRITICAL_THRESHOLD, default=current[CONF_BATTERY_CRITICAL_THRESHOLD]
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_DEFICIT_DELAY_ON, default=current[CONF_DEFICIT_DELAY_ON]
                ): vol.Coerce(int),
                vol.Optional(
                    CONF_DEFICIT_DELAY_OFF, default=current[CONF_DEFICIT_DELAY_OFF]
                ): vol.Coerce(int),
                vol.Optional(
                    CONF_NIGHT_START, default=current[CONF_NIGHT_START]
                ): str,
            }
        )
        return self.async_show_form(step_id="thresholds", data_schema=schema)

    # -- Charges -------------------------------------------------------------

    async def async_step_loads_menu(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return self.async_show_menu(
            step_id="loads_menu",
            menu_options=["add_load", "remove_load", "init"],
        )

    async def async_step_add_load(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        loads = list(self.config_entry.options.get(CONF_LOADS, DEFAULT_OPTIONS[CONF_LOADS]))

        if user_input is not None:
            if any(load["entity_id"] == user_input["entity_id"] for load in loads):
                errors["base"] = "already_exists"
            else:
                loads.append(
                    {
                        "entity_id": user_input["entity_id"],
                        "name": user_input["name"],
                        "tier": user_input["tier"],
                        "restore_delay": user_input["restore_delay"],
                    }
                )
                new_options = {**self.config_entry.options, CONF_LOADS: loads}
                return self.async_create_entry(title="", data=new_options)

        schema = vol.Schema(
            {
                vol.Required("entity_id"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="switch")
                ),
                vol.Required("name"): str,
                vol.Required("tier", default=2): vol.In([1, 2]),
                vol.Required("restore_delay", default=10): vol.Coerce(int),
            }
        )
        return self.async_show_form(step_id="add_load", data_schema=schema, errors=errors)

    async def async_step_remove_load(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        loads = list(self.config_entry.options.get(CONF_LOADS, DEFAULT_OPTIONS[CONF_LOADS]))

        if not loads:
            return self.async_abort(reason="no_loads")

        if user_input is not None:
            loads = [load for load in loads if load["entity_id"] != user_input["entity_id"]]
            new_options = {**self.config_entry.options, CONF_LOADS: loads}
            return self.async_create_entry(title="", data=new_options)

        options_map = {
            load["entity_id"]: f"{load['name']} ({load['entity_id']}, tier {load['tier']})"
            for load in loads
        }
        schema = vol.Schema({vol.Required("entity_id"): vol.In(options_map)})
        return self.async_show_form(step_id="remove_load", data_schema=schema)
