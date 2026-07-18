"""Coordinator : unique propriétaire du port série, alimente toutes les entités."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .axpert import AxpertClient
from .const import DOMAIN
from .exceptions import AxpertCommandRejectedError, AxpertError

_LOGGER = logging.getLogger(__name__)


class AxpertCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll unique du port série ; toutes les entités lisent coordinator.data.

    Le port est ouvert une seule fois et gardé ouvert entre les cycles
    (contrairement à cli_test.py qui ouvre/ferme à chaque appel) — c'est
    ce qui évite la contention qu'on a diagnostiquée à l'étape 1 : tant que
    ce coordinator est le SEUL à parler au port, il n'y a plus de conflit.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        port: str,
        baudrate: int,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self._client = AxpertClient(port, baudrate=baudrate)
        self._port_open = False

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.hass.async_add_executor_job(self._poll)
        except AxpertError as err:
            # Le port se referme tout seul en cas d'erreur, pour forcer une
            # réouverture propre au prochain cycle plutôt que de rester
            # dans un état incertain.
            self._port_open = False
            raise UpdateFailed(str(err)) from err

    def _poll(self) -> dict[str, Any]:
        if not self._port_open:
            self._client.open()
            self._port_open = True
        return self._client.get_all()

    async def async_set_output_mode(self, mode: str) -> None:
        """Change le mode de sortie (E2C/SOLAIRE/BATTERIE) puis rafraîchit l'état."""
        try:
            await self.hass.async_add_executor_job(
                self._client.set_output_source_priority, mode
            )
        except AxpertError as err:
            raise UpdateFailed(str(err)) from err
        await self.async_request_refresh()

    async def async_set_charger_priority(self, priority: str) -> None:
        """Change la priorité de CHARGE (E2C/SOLAIRE/MIXTE/SOLAIRE_SEUL)."""
        try:
            await self.hass.async_add_executor_job(
                self._client.set_charger_source_priority, priority
            )
        except AxpertCommandRejectedError:
            # NAK propre (valeur non supportée par ce modèle) : pas une
            # panne de communication, on ne fait pas planter le coordinator.
            raise
        except AxpertError as err:
            raise UpdateFailed(str(err)) from err
        await self.async_request_refresh()

    async def async_set_max_charging_current(self, amps: int) -> None:
        """MCHGC — courant de charge max, toutes sources."""
        try:
            await self.hass.async_add_executor_job(
                self._client.set_max_charging_current, amps
            )
        except AxpertCommandRejectedError:
            raise
        except AxpertError as err:
            raise UpdateFailed(str(err)) from err
        await self.async_request_refresh()

    async def async_set_max_utility_charging_current(self, amps: int) -> None:
        """MUCHGC — courant de charge max sur réseau uniquement."""
        try:
            await self.hass.async_add_executor_job(
                self._client.set_max_utility_charging_current, amps
            )
        except AxpertCommandRejectedError:
            raise
        except AxpertError as err:
            raise UpdateFailed(str(err)) from err
        await self.async_request_refresh()

    async def async_shutdown(self) -> None:
        await self.hass.async_add_executor_job(self._safe_close)
        await super().async_shutdown()

    def _safe_close(self) -> None:
        self._client.close()
        self._port_open = False
