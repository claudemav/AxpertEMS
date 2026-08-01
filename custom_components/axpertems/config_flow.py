"""Config flow : formulaire UI, aucune ligne de YAML nécessaire."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .axpert import AxpertClient
from .const import (
    CONF_BATTERY_CRITICAL_THRESHOLD,
    CONF_BAUDRATE,
    CONF_DEFICIT_DELAY_OFF,
    CONF_DEFICIT_DELAY_ON,
    CONF_NIGHT_START,
    CONF_PORT,
    CONF_RESTORE_DELAY_TIER1,
    CONF_RESTORE_DELAY_TIER2,
    CONF_RESTORE_DELAY_TIER3,
    CONF_SCAN_INTERVAL,
    CONF_SOC_THRESHOLD,
    CONF_SOC_THRESHOLD_SHEDDING,
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
    with AxpertClient(port, baudrate=baudrate) as client:
        client.get_qmod()


class AxpertEMSConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
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

        return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> "AxpertEMSOptionsFlow":
        return AxpertEMSOptionsFlow()


class AxpertEMSOptionsFlow(config_entries.OptionsFlow):
    """Un seul écran : seuils du moteur de décision."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        current = {**DEFAULT_OPTIONS, **self.config_entry.options}

        if user_input is not None:
            new_options = {**self.config_entry.options, **user_input}
            return self.async_create_entry(title="", data=new_options)

        schema = vol.Schema(
            {
                vol.Optional(CONF_SOC_THRESHOLD, default=current[CONF_SOC_THRESHOLD]): vol.Coerce(float),
                vol.Optional(
                    CONF_BATTERY_CRITICAL_THRESHOLD, default=current[CONF_BATTERY_CRITICAL_THRESHOLD]
                ): vol.Coerce(float),
                vol.Optional(CONF_DEFICIT_DELAY_ON, default=current[CONF_DEFICIT_DELAY_ON]): vol.Coerce(int),
                vol.Optional(CONF_DEFICIT_DELAY_OFF, default=current[CONF_DEFICIT_DELAY_OFF]): vol.Coerce(int),
                vol.Optional(CONF_NIGHT_START, default=current[CONF_NIGHT_START]): str,
                vol.Optional(
                    CONF_SOC_THRESHOLD_SHEDDING, default=current[CONF_SOC_THRESHOLD_SHEDDING]
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_RESTORE_DELAY_TIER1, default=current[CONF_RESTORE_DELAY_TIER1]
                ): vol.Coerce(int),
                vol.Optional(
                    CONF_RESTORE_DELAY_TIER2, default=current[CONF_RESTORE_DELAY_TIER2]
                ): vol.Coerce(int),
                vol.Optional(
                    CONF_RESTORE_DELAY_TIER3, default=current[CONF_RESTORE_DELAY_TIER3]
                ): vol.Coerce(int),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)