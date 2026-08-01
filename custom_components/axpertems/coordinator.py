"""Coordinator : unique propriétaire du port série, alimente toutes les entités.

Gère une période de grâce pour les échecs transitoires COMPLETS (bruit
RS232, micro-coupure) : les entités ne disparaissent plus pour un seul
raté isolé — elles conservent la dernière valeur connue, marquée
"vieillissante" via data_stale, et ne basculent en vraiment indisponible
qu'après plusieurs échecs consécutifs ou si les données deviennent trop
vieilles.

Distinct de ça : un échec PARTIEL (QMOD ou QPIRI seuls, alors que QPIGS
a réussi) est absorbé dans _poll() pour ne pas perdre les mesures
critiques, mais est maintenant suivi séparément via qmod_stale/
qpiri_stale/partial_error — sans quoi last_error/data_stale étaient
remis à zéro par un cycle "globalement réussi" qui masquait pourtant un
vrai problème sur une sous-commande.
"""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .axpert import AxpertClient
from .const import DOMAIN
from .exceptions import AxpertCommandRejectedError, AxpertError

_LOGGER = logging.getLogger(__name__)

QPIRI_REFRESH_SECONDS = 600
QMOD_REFRESH_SECONDS = 60
MAX_CONSECUTIVE_FAILURES = 3
MAX_STALE_AGE_SECONDS = 120


class AxpertCoordinator(DataUpdateCoordinator[dict[str, Any]]):
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

        self._qpiri_cache: dict[str, Any] = {}
        self._last_qpiri_fetch: float = 0.0

        self._qmod_cache: dict[str, Any] = {}
        self._last_qmod_fetch: float = 0.0

        self.supported_max_charging_currents: list[int] = []
        self.supported_max_utility_charging_currents: list[int] = []

        # -- santé GLOBALE du cycle de poll (échec complet, période de grâce) --
        self.consecutive_failures: int = 0
        self.last_success: Any = None
        self.last_error: str | None = None
        self.data_stale: bool = False
        self._last_success_monotonic: float | None = None

        # -- santé PARTIELLE : QMOD/QPIRI en échec alors que le cycle
        # global a réussi (QPIGS ok). Persistent jusqu'à la prochaine
        # tentative réussie de la commande concernée — pas remis à zéro
        # juste parce que la commande n'était pas due ce cycle-ci.
        self.qmod_stale: bool = False
        self.qmod_last_error: str | None = None
        self.qpiri_stale: bool = False
        self.qpiri_last_error: str | None = None

    @property
    def partial_error(self) -> str | None:
        """Résumé lisible des sous-commandes en échec, ou None si tout est frais."""
        parts: list[str] = []
        if self.qmod_stale:
            parts.append(f"QMOD ancien ({self.qmod_last_error or 'raison inconnue'})")
        if self.qpiri_stale:
            parts.append(f"QPIRI ancien ({self.qpiri_last_error or 'raison inconnue'})")
        return "; ".join(parts) if parts else None

    async def async_fetch_supported_currents(self) -> None:
        try:
            self.supported_max_charging_currents = await self.hass.async_add_executor_job(
                self._client.get_supported_max_charging_currents
            )
            self.supported_max_utility_charging_currents = await self.hass.async_add_executor_job(
                self._client.get_supported_max_utility_charging_currents
            )
        except AxpertError as err:
            _LOGGER.warning("Paliers de courant non lus (QMCHGCR/QMUCHGCR) : %s", err)

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self.hass.async_add_executor_job(self._poll)
        except AxpertError as err:
            self.consecutive_failures += 1
            self.last_error = str(err)

            age = (
                time.monotonic() - self._last_success_monotonic
                if self._last_success_monotonic is not None
                else None
            )

            await self.hass.async_add_executor_job(self._safe_close)

            if (
                self.data is not None
                and self.consecutive_failures < MAX_CONSECUTIVE_FAILURES
                and (age is None or age < MAX_STALE_AGE_SECONDS)
            ):
                self.data_stale = True
                _LOGGER.warning(
                    "Échec série transitoire %s/%s, conservation des dernières données : %s",
                    self.consecutive_failures,
                    MAX_CONSECUTIVE_FAILURES,
                    err,
                )
                return self.data

            raise UpdateFailed(str(err)) from err

        # Le cycle GLOBAL a réussi (QPIGS ok) — mais qmod_stale/qpiri_stale
        # ont pu être positionnés à l'intérieur de _poll() si QMOD/QPIRI
        # ont échoué isolément. On ne les touche PAS ici : ils reflètent
        # leur propre état, indépendant de la réussite globale du cycle.
        self.consecutive_failures = 0
        self.last_error = None
        self.data_stale = False
        self.last_success = dt_util.utcnow()
        self._last_success_monotonic = time.monotonic()
        return data

    def _poll(self) -> dict[str, Any]:
        if not self._port_open:
            self._client.open()
            self._port_open = True

        # QPIGS : critique, à chaque cycle. Une erreur ici fait échouer
        # tout le cycle (remonte vers _async_update_data), normal.
        qpigs = self._client.get_qpigs()

        # QMOD : moins critique, lu moins souvent (60s). Une erreur
        # PONCTUELLE ne fait plus échouer tout le cycle -> on garde le
        # dernier mode connu, mais on marque qmod_stale=True et on
        # conserve le message d'erreur, PERSISTANTS jusqu'à la prochaine
        # tentative réussie (pas remis à zéro tant qu'aucune nouvelle
        # tentative n'a eu lieu).
        if not self._qmod_cache or (time.monotonic() - self._last_qmod_fetch) > QMOD_REFRESH_SECONDS:
            try:
                self._qmod_cache = self._client.get_qmod()
                self._last_qmod_fetch = time.monotonic()
                self.qmod_stale = False
                self.qmod_last_error = None
            except AxpertError as err:
                self.qmod_stale = True
                self.qmod_last_error = str(err)
                if not self._qmod_cache:
                    _LOGGER.warning("QMOD indisponible (aucune valeur précédente) : %s", err)
                else:
                    _LOGGER.debug("QMOD indisponible, conservation du dernier mode connu : %s", err)

        # QPIRI : réglages stables, cache 10 min. Même logique de
        # persistance du drapeau "stale" que QMOD ci-dessus.
        qpiri_due = (
            not self._qpiri_cache
            or (time.monotonic() - self._last_qpiri_fetch) > QPIRI_REFRESH_SECONDS
        )
        if qpiri_due:
            try:
                self._qpiri_cache = self._client.get_settings()
                self._last_qpiri_fetch = time.monotonic()
                self.qpiri_stale = False
                self.qpiri_last_error = None
            except AxpertError as err:
                self.qpiri_stale = True
                self.qpiri_last_error = str(err)
                if not self._qpiri_cache:
                    _LOGGER.warning("QPIRI indisponible (aucune valeur précédente) : %s", err)
                else:
                    _LOGGER.debug("QPIRI indisponible, conservation des derniers réglages : %s", err)

        return {
            "qpigs": qpigs,
            "qmod": self._qmod_cache,
            "qpiri": self._qpiri_cache.get("qpiri", {}),
        }

    def _force_qpiri_refresh(self) -> None:
        self._qpiri_cache = {}

    async def async_set_output_mode(self, mode: str) -> None:
        try:
            await self.hass.async_add_executor_job(
                self._client.set_output_source_priority, mode
            )
        except AxpertCommandRejectedError:
            raise
        except AxpertError as err:
            raise UpdateFailed(str(err)) from err
        self._force_qpiri_refresh()
        await self.async_request_refresh()

    async def async_set_charger_priority(self, priority: str) -> None:
        try:
            await self.hass.async_add_executor_job(
                self._client.set_charger_source_priority, priority
            )
        except AxpertCommandRejectedError:
            raise
        except AxpertError as err:
            raise UpdateFailed(str(err)) from err
        self._force_qpiri_refresh()
        await self.async_request_refresh()

    async def async_set_max_charging_current(self, amps: int) -> None:
        try:
            await self.hass.async_add_executor_job(
                self._client.set_max_charging_current, amps
            )
        except AxpertCommandRejectedError:
            raise
        except AxpertError as err:
            raise UpdateFailed(str(err)) from err
        self._force_qpiri_refresh()
        await self.async_request_refresh()

    async def async_set_max_utility_charging_current(self, amps: int) -> None:
        try:
            await self.hass.async_add_executor_job(
                self._client.set_max_utility_charging_current, amps
            )
        except AxpertCommandRejectedError:
            raise
        except AxpertError as err:
            raise UpdateFailed(str(err)) from err
        self._force_qpiri_refresh()
        await self.async_request_refresh()

    async def async_send_raw(self, command: str) -> str:
        """Diagnostic : envoie une commande brute et retourne la réponse
        telle quelle. Utile pour tester un format de commande sur un
        clone PI30 dont le firmware diverge du standard (ex: largeur de
        padding numérique différente pour MCHGC/MUCHGC)."""
        return await self.hass.async_add_executor_job(self._client.send_raw, command)

    async def async_shutdown(self) -> None:
        await self.hass.async_add_executor_job(self._safe_close)
        await super().async_shutdown()

    def _safe_close(self) -> None:
        self._client.close()
        self._port_open = False
