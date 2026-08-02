"""Implémentation du protocole PI30 (Voltronic / MPP Solar / Axpert et clones)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .exceptions import AxpertCommandRejectedError, AxpertResponseError

_CRC_TABLE = [
    0x0000, 0x1021, 0x2042, 0x3063, 0x4084, 0x50A5, 0x60C6, 0x70E7,
    0x8108, 0x9129, 0xA14A, 0xB16B, 0xC18C, 0xD1AD, 0xE1CE, 0xF1EF,
]


def crc16(data: bytes) -> bytes:
    crc = 0
    for byte in data:
        da = ((crc >> 8) & 0xFF) >> 4
        crc = ((crc << 4) & 0xFFFF) ^ _CRC_TABLE[da ^ (byte >> 4)]
        da = ((crc >> 8) & 0xFF) >> 4
        crc = ((crc << 4) & 0xFFFF) ^ _CRC_TABLE[da ^ (byte & 0x0F)]

    crc_low = crc & 0xFF
    crc_high = (crc >> 8) & 0xFF

    if crc_low in (0x28, 0x0D, 0x0A):
        crc_low += 1
    if crc_high in (0x28, 0x0D, 0x0A):
        crc_high += 1

    return bytes([crc_high, crc_low])


def build_command(command: str) -> bytes:
    payload = command.encode("ascii")
    return payload + crc16(payload) + b"\r"


def extract_payload(raw: bytes) -> str:
    if len(raw) < 4 or not raw.endswith(b"\r"):
        raise ValueError(f"Trame incomplète ou mal terminée : {raw!r}")

    body = raw[:-3]
    received_crc = raw[-3:-1]

    if not body.startswith(b"("):
        raise ValueError(f"Trame de réponse sans '(' initial : {raw!r}")

    expected_crc = crc16(body)
    if expected_crc != received_crc:
        raise ValueError(
            f"CRC invalide : reçu {received_crc.hex()}, attendu {expected_crc.hex()} "
            f"(trame : {raw!r}). Vérifier le câblage / la vitesse du port série."
        )

    return body[1:].decode("ascii", errors="replace")


QMOD_MAP = {
    "P": "Power On", "S": "Standby", "L": "Line", "B": "Battery",
    "F": "Fault", "H": "Power Saving", "D": "Shutdown",
}


def parse_qmod(payload: str) -> dict[str, Any]:
    code = payload.strip()
    return {"raw": code, "device_mode": QMOD_MAP.get(code, "Unknown")}


_QPIGS_FIELDS = [
    "ac_input_voltage", "ac_input_frequency", "ac_output_voltage",
    "ac_output_frequency", "ac_output_apparent_power", "ac_output_active_power",
    "ac_output_load", "bus_voltage", "battery_voltage", "battery_charging_current",
    "battery_capacity", "inverter_heat_sink_temperature", "pv_input_current_for_battery",
    "pv_input_voltage", "battery_voltage_from_scc", "battery_discharge_current",
]

_DEVICE_STATUS_BITS = [
    "is_sbu_priority_version_added", "is_configuration_changed",
    "is_scc_firmware_updated", "is_load_on",
    "is_battery_voltage_to_steady_while_charging", "is_charging_on",
    "is_scc_charging_on", "is_ac_charging_on",
]


def validate_field_count(parts: list[str], expected_fields: list[str], command: str) -> None:
    if len(parts) < len(expected_fields):
        raise AxpertResponseError(
            f"Trame {command} tronquée : {len(parts)} champs reçus, "
            f"{len(expected_fields)} attendus au minimum "
            f"(payload : {' '.join(parts)!r})"
        )


def parse_float_field(value: str) -> float | str:
    try:
        return float(value)
    except ValueError:
        return value


def parse_qpigs_status(parts: list[str]) -> dict[str, bool]:
    if len(parts) <= len(_QPIGS_FIELDS):
        return {}
    status = parts[len(_QPIGS_FIELDS)]
    if len(status) != len(_DEVICE_STATUS_BITS):
        return {}
    return {name: (bit == "1") for name, bit in zip(_DEVICE_STATUS_BITS, status)}


def parse_qpigs(payload: str) -> dict[str, Any]:
    parts = payload.split()
    validate_field_count(parts, _QPIGS_FIELDS, "QPIGS")

    result: dict[str, Any] = {"_command": "QPIGS"}
    for name, value in zip(_QPIGS_FIELDS, parts):
        result[name] = parse_float_field(value)

    result.update(parse_qpigs_status(parts))

    if "pv_input_power" not in result and "pv_input_voltage" in result and "pv_input_current_for_battery" in result:
        try:
            result["pv_input_power"] = round(
                result["pv_input_voltage"] * result["pv_input_current_for_battery"], 1
            )
        except TypeError:
            pass

    return result


_OUTPUT_SOURCE_PRIORITY_MAP = {"0": "Utility first", "1": "Solar first", "2": "SBU first"}
_CHARGER_SOURCE_PRIORITY_MAP = {
    "0": "Utility first", "1": "Solar first", "2": "Solar and utility", "3": "Solar only",
}

_QPIRI_FIELDS = [
    "grid_rating_voltage", "grid_rating_current", "ac_output_rating_voltage",
    "ac_output_rating_frequency", "ac_output_rating_current", "ac_output_rating_apparent_power",
    "ac_output_rating_active_power", "battery_rating_voltage", "battery_recharge_voltage",
    "battery_under_voltage", "battery_bulk_voltage", "battery_float_voltage",
    "battery_type_code", "max_ac_charging_current", "max_charging_current",
    "input_voltage_range", "output_source_priority_code", "charger_source_priority_code",
    "parallel_max_num", "machine_type", "topology", "output_mode",
]


def parse_qpiri(payload: str) -> dict[str, Any]:
    parts = payload.split()
    validate_field_count(parts, _QPIRI_FIELDS, "QPIRI")

    result: dict[str, Any] = {"_command": "QPIRI"}
    for name, value in zip(_QPIRI_FIELDS, parts):
        result[name] = parse_float_field(value)

    if "output_source_priority_code" in result:
        code = str(int(result["output_source_priority_code"]))
        result["output_source_priority"] = _OUTPUT_SOURCE_PRIORITY_MAP.get(code, "Unknown")
    if "charger_source_priority_code" in result:
        code = str(int(result["charger_source_priority_code"]))
        result["charger_source_priority"] = _CHARGER_SOURCE_PRIORITY_MAP.get(code, "Unknown")

    return result


def parse_current_options(payload: str) -> list[int]:
    """QMCHGCR / QMUCHGCR — paliers de courant acceptés par CET onduleur."""
    if "NAK" in payload.upper():
        raise AxpertCommandRejectedError(
            f"L'onduleur a rejeté la lecture des paliers de courant (réponse : {payload!r})"
        )

    options: list[int] = []
    for token in payload.split():
        try:
            options.append(int(float(token)))
        except ValueError:
            continue

    if not options:
        raise AxpertResponseError(
            f"Aucun palier de courant valide trouvé dans la réponse : {payload!r}"
        )

    return options


OUTPUT_MODE_COMMANDS = {"E2C": "POP00", "SOLAIRE": "POP01", "BATTERIE": "POP02"}

CHARGER_PRIORITY_COMMANDS = {
    "E2C": "PCP00", "SOLAIRE": "PCP01", "MIXTE": "PCP02", "SOLAIRE_SEUL": "PCP03",
}


def build_max_charging_current_command(amps: int) -> str:
    """MNCHGC — CONFIRMÉ empiriquement (QPIRI avant/après : 10A -> 30A) :
    ce firmware Victor NM-ECO utilise MNCHGC et non MCHGC (qui n'existe
    apparemment pas sur ce modèle, NAK systématique quel que soit le
    format testé). 3 chiffres, SANS numéro d'unité en parallèle —
    contrairement à la variante MNCHGC<m><nnn> à 4 chiffres documentée
    dans le manuel PIP-HS/MS/MSX, qui ne correspond pas à ce modèle.
    Fragmentation connue et documentée entre variantes de clones PI30."""
    return f"MNCHGC{amps:03d}"


def build_max_utility_charging_current_command(amps: int) -> str:
    """MUCHGC — CONFIRMÉ empiriquement (QPIRI avant/après : 2A -> 10A,
    ACK propre) : format 3 chiffres standard. Le correctif précédent
    (4 chiffres, basé sur une référence communautaire esphome-pipsolar)
    était erroné pour ce modèle précis — je reviens donc au format 3
    chiffres d'origine, maintenant validé par test réel plutôt que par
    une source externe."""
    return f"MUCHGC{amps:03d}"


@dataclass
class AckResponse:
    ok: bool
    raw: str = field(default="")

    @classmethod
    def from_payload(cls, payload: str) -> "AckResponse":
        return cls(ok=payload.strip().upper().startswith("ACK"), raw=payload)
