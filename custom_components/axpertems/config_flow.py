"""Config flow : formulaire UI, aucune ligne de YAML nécessaire."""

from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .axpert import AxpertClient, detect_baudrate, list_available_ports
from .const import (
    CONF_BATTERY_CRITICAL_THRESHOLD,
    CONF_BAUDRATE,
    CONF_DEFICIT_DELAY_OFF,
    CONF_DEFICIT_DELAY_ON,
    CONF_NAME,
    CONF_NIGHT_START,
    CONF_PORT,
    CONF_RESTORE_DELAY_TIER1,
    CONF_RESTORE_DELAY_TIER2,
    CONF_RESTORE_DELAY_TIER3,
    CONF_SCAN_INTERVAL,
    CONF_SOC_THRESHOLD,
    CONF_SOC_THRESHOLD_SHEDDING,
    DEFAULT_BAUDRATE,
    DEFAULT_NAME,
    DEFAULT_OPTIONS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .exceptions import AxpertError

_LOGGER = logging.getLogger(__name__)

SUPPORTED_BAUDRATES = [2400, 4800, 9600, 19200]
AUTO_DETECT_BAUDRATE = "auto"

_HHMM_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _test_connection(port: str, baudrate: int) -> None:
    with AxpertClient(port, baudrate=baudrate) as client:
        client.get_qmod()


def _build_user_schema(detected_ports: list[str]) -> vol.Schema:
    port_selector = (
        selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=detected_ports,
                custom_value=True,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )
        if detected_ports
        else str
    )

    baudrate_options = [AUTO_DETECT_BAUDRATE] + [str(b) for b in SUPPORTED_BAUDRATES]

    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
            vol.Required(CONF_PORT): port_selector,
            vol.Optional(CONF_BAUDRATE, default=AUTO_DETECT_BAUDRATE): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=baudrate_options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                vol.Coerce(int), vol.Range(min=5, max=300)
            ),
        }
    )


class AxpertEMSConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        detected_ports = await self.hass.async_add_executor_job(list_available_ports)

        if user_input is not None:
            port = user_input[CONF_PORT]
            baudrate_input = user_input[CONF_BAUDRATE]

            if baudrate_input == AUTO_DETECT_BAUDRATE:
                detected_baudrate = await self.hass.async_add_executor_job(
                    detect_baudrate, port, SUPPORTED_BAUDRATES
                )
                if detected_baudrate is None:
                    errors["base"] = "cannot_detect_baudrate"
                else:
                    baudrate = detected_baudrate
            else:
                baudrate = int(baudrate_input)

            if not errors:
                await self.async_set_unique_id(port)
                self._abort_if_unique_id_configured()

                try:
                    await self.hass.async_add_executor_job(
                        _test_connection, port, baudrate
                    )
                except AxpertError as err:
                    _LOGGER.debug("Connection failed during config_flow: %s", err)
                    errors["base"] = "cannot_connect"
                else:
                    final_data = {
                        **user_input,
                        CONF_PORT: port,
                        CONF_BAUDRATE: baudrate,
                    }
                    return self.async_create_entry(
                        title=user_input[CONF_NAME],
                        data=final_data,
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=_build_user_schema(detected_ports),
            errors=errors,
            description_placeholders={
                "ports_found": str(len(detected_ports))
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> "AxpertEMSOptionsFlow":
        return AxpertEMSOptionsFlow()


class AxpertEMSOptionsFlow(config_entries.OptionsFlow):
    """Un seul écran : seuils du moteur de décision."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        current = {**DEFAULT_OPTIONS, **self.config_entry.options}
        errors: dict[str, str] = {}

        if user_input is not None:
            night_start = user_input.get(CONF_NIGHT_START, current[CONF_NIGHT_START])
            if not _HHMM_PATTERN.match(night_start):
                errors[CONF_NIGHT_START] = "format_hhmm"
            else:
                new_options = {**self.config_entry.options, **user_input}
                return self.async_create_entry(title="", data=new_options)

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SOC_THRESHOLD, default=current[CONF_SOC_THRESHOLD]
                ): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
                vol.Optional(
                    CONF_BATTERY_CRITICAL_THRESHOLD, default=current[CONF_BATTERY_CRITICAL_THRESHOLD]
                ): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
                vol.Optional(
                    CONF_DEFICIT_DELAY_ON, default=current[CONF_DEFICIT_DELAY_ON]
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=120)),
                vol.Optional(
                    CONF_DEFICIT_DELAY_OFF, default=current[CONF_DEFICIT_DELAY_OFF]
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=120)),
                vol.Optional(
                    CONF_NIGHT_START, default=current[CONF_NIGHT_START]
                ): str,
                vol.Optional(
                    CONF_SOC_THRESHOLD_SHEDDING, default=current[CONF_SOC_THRESHOLD_SHEDDING]
                ): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
                vol.Optional(
                    CONF_RESTORE_DELAY_TIER1, default=current[CONF_RESTORE_DELAY_TIER1]
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=3600)),
                vol.Optional(
                    CONF_RESTORE_DELAY_TIER2, default=current[CONF_RESTORE_DELAY_TIER2]
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=3600)),
                vol.Optional(
                    CONF_RESTORE_DELAY_TIER3, default=current[CONF_RESTORE_DELAY_TIER3]
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=3600)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
