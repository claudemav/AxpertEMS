"""
Client série natif pour onduleurs Axpert / Voltronic (protocole PI30).

Remplace la chaîne script bash -> mpp-solar -> SSH -> fichier JSON par une
communication directe en Python. Conçu pour être utilisé :
  - en synchrone, tel quel, pour des tests / scripts ;
  - depuis un DataUpdateCoordinator Home Assistant via
    `hass.async_add_executor_job(...)` (le futur coordinator.py de
    l'intégration s'appuiera sur cette classe sans la modifier).
"""

from __future__ import annotations

import logging
import time
from typing import Any

import serial

from .exceptions import (
    AxpertCommandRejectedError,
    AxpertCommunicationError,
    AxpertResponseError,
)
from . import protocol

_LOGGER = logging.getLogger(__name__)

DEFAULT_BAUDRATE = 2400
DEFAULT_TIMEOUT = 2.0
MAX_RESPONSE_BYTES = 256


class AxpertClient:
    """Communique avec un onduleur Axpert/Voltronic sur un port série."""

    def __init__(
        self,
        port: str,
        baudrate: int = DEFAULT_BAUDRATE,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._port_name = port
        self._baudrate = baudrate
        self._timeout = timeout
        self._serial: serial.Serial | None = None

    # -- gestion du port -----------------------------------------------

    def open(self) -> None:
        if self._serial and self._serial.is_open:
            return
        try:
            self._serial = serial.Serial(
                port=self._port_name,
                baudrate=self._baudrate,
                timeout=self._timeout,
                write_timeout=self._timeout,
            )
        except serial.SerialException as err:
            raise AxpertCommunicationError(
                f"Impossible d'ouvrir le port {self._port_name} : {err}"
            ) from err

    def close(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()

    def __enter__(self) -> "AxpertClient":
        self.open()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- I/O bas niveau --------------------------------------------------

    def _write(self, frame: bytes) -> None:
        assert self._serial is not None
        self._serial.reset_input_buffer()
        self._serial.write(frame)
        self._serial.flush()

    def _read_frame(self) -> bytes:
        """Lit jusqu'au CR terminal, ou lève une erreur au timeout."""
        assert self._serial is not None
        buffer = bytearray()
        deadline = time.monotonic() + self._timeout

        while time.monotonic() < deadline:
            chunk = self._serial.read(1)
            if not chunk:
                continue
            buffer.extend(chunk)
            if chunk == b"\r":
                return bytes(buffer)
            if len(buffer) > MAX_RESPONSE_BYTES:
                raise AxpertResponseError(
                    f"Réponse trop longue sans CR terminal : {bytes(buffer)!r}"
                )

        raise AxpertCommunicationError(
            f"Timeout ({self._timeout}s) en attente de réponse de l'onduleur "
            f"(données reçues jusqu'ici : {bytes(buffer)!r})"
        )

    def execute(self, command: str, retries: int = 1) -> str:
        """Envoie une commande brute (ex: 'QPIGS') et retourne le payload validé.

        `retries` : nombre de tentatives SUPPLÉMENTAIRES en cas de timeout/erreur
        de réponse avant d'abandonner (1 par défaut = 2 tentatives au total).
        Les liaisons RS232/USB-série vers ces onduleurs sont connues pour avoir
        des ratés ponctuels (bruit électrique, micro-coupure) — une nouvelle
        tentative immédiate absorbe l'immense majorité des cas sans masquer une
        vraie panne persistante (qui, elle, échouera aussi à la 2e tentative).
        """
        if not self._serial or not self._serial.is_open:
            raise AxpertCommunicationError("Port série non ouvert (appeler open() ou utiliser 'with')")

        frame = protocol.build_command(command)
        last_error: Exception | None = None

        for attempt in range(retries + 1):
            if attempt > 0:
                _LOGGER.debug("Nouvelle tentative pour %s (essai %d)", command, attempt + 1)
                time.sleep(0.3)

            _LOGGER.debug("-> %s (%r)", command, frame)
            try:
                self._write(frame)
                raw = self._read_frame()
            except (serial.SerialException, AxpertCommunicationError, AxpertResponseError) as err:
                last_error = (
                    AxpertCommunicationError(f"Erreur I/O série : {err}")
                    if isinstance(err, serial.SerialException)
                    else err
                )
                continue

            _LOGGER.debug("<- %r", raw)

            try:
                return protocol.extract_payload(raw)
            except ValueError as err:
                last_error = AxpertResponseError(str(err))
                continue

        assert last_error is not None
        raise last_error

    # -- API haut niveau : lecture ---------------------------------------

    def get_qpigs(self) -> dict[str, Any]:
        return protocol.parse_qpigs(self.execute("QPIGS"))

    def get_qpiri(self) -> dict[str, Any]:
        return protocol.parse_qpiri(self.execute("QPIRI"))

    def get_qmod(self) -> dict[str, Any]:
        return protocol.parse_qmod(self.execute("QMOD"))

    def get_all(self) -> dict[str, Any]:
        """Lit QPIGS + QMOD + QPIRI en une fois (utile pour un cycle de polling)."""
        return {
            "qpigs": self.get_qpigs(),
            "qmod": self.get_qmod(),
            "qpiri": self.get_qpiri(),
        }

    # -- API haut niveau : écriture ---------------------------------------

    def set_output_source_priority(self, mode: str) -> protocol.AckResponse:
        """mode: 'E2C' | 'SOLAIRE' | 'BATTERIE' (voir protocol.OUTPUT_MODE_COMMANDS)."""
        if mode not in protocol.OUTPUT_MODE_COMMANDS:
            raise ValueError(
                f"Mode inconnu '{mode}', attendu un de {list(protocol.OUTPUT_MODE_COMMANDS)}"
            )
        command = protocol.OUTPUT_MODE_COMMANDS[mode]
        payload = self.execute(command)
        ack = protocol.AckResponse.from_payload(payload)
        if not ack.ok:
            raise AxpertCommandRejectedError(
                f"L'onduleur a rejeté la commande {command} (réponse : {payload!r})"
            )
        return ack

    def set_charger_source_priority(self, priority: str) -> protocol.AckResponse:
        """priority: 'E2C' | 'SOLAIRE' | 'MIXTE' | 'SOLAIRE_SEUL'
        (voir protocol.CHARGER_PRIORITY_COMMANDS). Différent de la priorité
        de SORTIE (set_output_source_priority) : ceci contrôle d'où vient le
        courant de CHARGE de la batterie, pas d'où vient l'alimentation de
        la maison."""
        if priority not in protocol.CHARGER_PRIORITY_COMMANDS:
            raise ValueError(
                f"Priorité inconnue '{priority}', attendu un de "
                f"{list(protocol.CHARGER_PRIORITY_COMMANDS)}"
            )
        command = protocol.CHARGER_PRIORITY_COMMANDS[priority]
        payload = self.execute(command)
        ack = protocol.AckResponse.from_payload(payload)
        if not ack.ok:
            raise AxpertCommandRejectedError(
                f"L'onduleur a rejeté la commande {command} (réponse : {payload!r})"
            )
        return ack

    def set_max_charging_current(self, amps: int) -> protocol.AckResponse:
        """MCHGC — courant de charge max, toutes sources confondues.
        L'onduleur n'accepte que certains paliers spécifiques à son modèle
        (interrogeables via QMCHGCR, non implémenté ici) : une valeur hors
        palier renvoie NAK -> AxpertCommandRejectedError, sans rien casser."""
        command = protocol.build_max_charging_current_command(amps)
        payload = self.execute(command)
        ack = protocol.AckResponse.from_payload(payload)
        if not ack.ok:
            raise AxpertCommandRejectedError(
                f"L'onduleur a rejeté {command} (valeur hors paliers acceptés ? réponse : {payload!r})"
            )
        return ack

    def set_max_utility_charging_current(self, amps: int) -> protocol.AckResponse:
        """MUCHGC — courant de charge max sur réseau uniquement. Même
        réserve que set_max_charging_current sur les paliers acceptés."""
        command = protocol.build_max_utility_charging_current_command(amps)
        payload = self.execute(command)
        ack = protocol.AckResponse.from_payload(payload)
        if not ack.ok:
            raise AxpertCommandRejectedError(
                f"L'onduleur a rejeté {command} (valeur hors paliers acceptés ? réponse : {payload!r})"
            )
        return ack

    def send_raw(self, command: str) -> str:
        """Passe-plat pour une commande PI30 non encore mappée dans ce driver."""
        return self.execute(command)
