"""Client série natif pour onduleurs Axpert / Voltronic (protocole PI30)."""

from __future__ import annotations

import logging
import threading
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
DEFAULT_TIMEOUT = 3.0
MAX_RESPONSE_BYTES = 256


class AxpertClient:
    """Communique avec un onduleur Axpert/Voltronic sur un port série.

    Un threading.Lock protège TOUTE la transaction execute() (écriture +
    lecture + validation) : ce client est partagé entre le coordinator
    (poll périodique) et les appels de service (select), potentiellement
    sur des threads différents du pool d'executors HA, en parallèle.
    Sans ce verrou, une écriture (POP02, PCP03...) peut s'interleaver
    avec une lecture QPIGS en cours et corrompre les deux trames.
    """

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
        self._lock = threading.Lock()

    def open(self) -> None:
        with self._lock:
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
        with self._lock:
            if self._serial and self._serial.is_open:
                self._serial.close()

    def __enter__(self) -> "AxpertClient":
        self.open()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _write(self, frame: bytes) -> None:
        assert self._serial is not None
        self._serial.reset_input_buffer()
        self._serial.write(frame)
        self._serial.flush()

    def _read_frame(self) -> bytes:
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
        """Toute la transaction (tentatives incluses) est sous verrou."""
        with self._lock:
            if not self._serial or not self._serial.is_open:
                raise AxpertCommunicationError(
                    "Port série non ouvert (appeler open() ou utiliser 'with')"
                )

            frame = protocol.build_command(command)
            last_error: Exception | None = None

            for attempt in range(retries + 1):
                if attempt > 0:
                    _LOGGER.debug("Nouvelle tentative pour %s (essai %d)", command, attempt + 1)
                    time.sleep(0.5)

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

    def get_qpigs(self) -> dict[str, Any]:
        return protocol.parse_qpigs(self.execute("QPIGS"))

    def get_qpiri(self) -> dict[str, Any]:
        return protocol.parse_qpiri(self.execute("QPIRI"))

    def get_qmod(self) -> dict[str, Any]:
        return protocol.parse_qmod(self.execute("QMOD"))

    def get_realtime_data(self) -> dict[str, Any]:
        return {"qpigs": self.get_qpigs(), "qmod": self.get_qmod()}

    def get_settings(self) -> dict[str, Any]:
        return {"qpiri": self.get_qpiri()}

    def get_all(self) -> dict[str, Any]:
        return {**self.get_realtime_data(), **self.get_settings()}

    def get_supported_max_charging_currents(self) -> list[int]:
        return protocol.parse_current_options(self.execute("QMCHGCR"))

    def get_supported_max_utility_charging_currents(self) -> list[int]:
        return protocol.parse_current_options(self.execute("QMUCHGCR"))

    def set_output_source_priority(self, mode: str) -> protocol.AckResponse:
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
        command = protocol.build_max_charging_current_command(amps)
        payload = self.execute(command)
        ack = protocol.AckResponse.from_payload(payload)
        if not ack.ok:
            raise AxpertCommandRejectedError(
                f"L'onduleur a rejeté {command} (réponse : {payload!r})"
            )
        return ack

    def set_max_utility_charging_current(self, amps: int) -> protocol.AckResponse:
        command = protocol.build_max_utility_charging_current_command(amps)
        payload = self.execute(command)
        ack = protocol.AckResponse.from_payload(payload)
        if not ack.ok:
            raise AxpertCommandRejectedError(
                f"L'onduleur a rejeté {command} (réponse : {payload!r})"
            )
        return ack

    def send_raw(self, command: str) -> str:
        return self.execute(command)
