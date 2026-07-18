"""
Implémentation du protocole PI30 (Voltronic / MPP Solar / Axpert et clones
compatibles : Must, Easun, PowMr...).

Ce module ne fait AUCUNE I/O — il construit et parse des trames en mémoire.
Toute la communication série vit dans axpert.py, ce qui rend ce module
facilement testable sans matériel (voir test_protocol.py).

Référence : spécification "PI30" largement documentée dans la communauté
mpp-solar / Voltronic (format de trame identique sur la plupart des
onduleurs "Axpert-like").

Format d'une trame :
    Commande :  <ASCII command><CRC16 2 bytes><CR>
    Réponse  :  "(" <payload ASCII> <CRC16 2 bytes> <CR>
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# CRC16 (variante utilisée par les onduleurs Voltronic/PI30)
# ---------------------------------------------------------------------------

_CRC_TABLE = [
    0x0000, 0x1021, 0x2042, 0x3063, 0x4084, 0x50A5, 0x60C6, 0x70E7,
    0x8108, 0x9129, 0xA14A, 0xB16B, 0xC18C, 0xD1AD, 0xE1CE, 0xF1EF,
]


def crc16(data: bytes) -> bytes:
    """CRC16 sur 2 nibbles/octet, avec l'échappement propre au protocole PI30 :
    les octets de CRC égaux à 0x28 ('('), 0x0D (CR) ou 0x0A (LF) sont
    incrémentés de 1 pour ne jamais être confondus avec un délimiteur de trame.
    """
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
    """Construit une trame de commande complète, prête à écrire sur le port série."""
    payload = command.encode("ascii")
    return payload + crc16(payload) + b"\r"


def extract_payload(raw: bytes) -> str:
    """Valide le CRC d'une trame de réponse et retourne le payload décodé.

    `raw` doit être la trame complète, CR final inclus :
        b"(payload...." + crc(2 bytes) + b"\\r"
    """
    if len(raw) < 4 or not raw.endswith(b"\r"):
        raise ValueError(f"Trame incomplète ou mal terminée : {raw!r}")

    body = raw[:-3]          # tout sauf crc(2) + CR
    received_crc = raw[-3:-1]

    if not body.startswith(b"("):
        raise ValueError(f"Trame de réponse sans '(' initial : {raw!r}")

    expected_crc = crc16(body)
    if expected_crc != received_crc:
        raise ValueError(
            f"CRC invalide : reçu {received_crc.hex()}, attendu {expected_crc.hex()} "
            f"(trame : {raw!r}). Vérifier le câblage / la vitesse du port série."
        )

    return body[1:].decode("ascii", errors="replace")  # sans le '(' initial


# ---------------------------------------------------------------------------
# QMOD — Mode de fonctionnement (1 caractère)
# ---------------------------------------------------------------------------

QMOD_MAP = {
    "P": "Power On",
    "S": "Standby",
    "L": "Line",
    "B": "Battery",
    "F": "Fault",
    "H": "Power Saving",
    "D": "Shutdown",
}


def parse_qmod(payload: str) -> dict[str, Any]:
    code = payload.strip()
    return {
        "raw": code,
        "device_mode": QMOD_MAP.get(code, "Unknown"),
    }


# ---------------------------------------------------------------------------
# QPIGS — Paramètres de fonctionnement instantanés
# ---------------------------------------------------------------------------
# Ordre des champs conforme au format PI30 standard. À VALIDER sur ta trame
# réelle : certaines révisions de firmware ajoutent des champs en fin de
# ligne (device_status_2, pv2...) sans casser la compatibilité ascendante,
# donc on ignore silencieusement tout champ en trop.

_QPIGS_FIELDS = [
    "ac_input_voltage",
    "ac_input_frequency",
    "ac_output_voltage",
    "ac_output_frequency",
    "ac_output_apparent_power",
    "ac_output_active_power",
    "ac_output_load",
    "bus_voltage",
    "battery_voltage",
    "battery_charging_current",
    "battery_capacity",
    "inverter_heat_sink_temperature",
    "pv_input_current_for_battery",
    "pv_input_voltage",
    "battery_voltage_from_scc",
    "battery_discharge_current",
]

_DEVICE_STATUS_BITS = [
    "is_sbu_priority_version_added",
    "is_configuration_changed",
    "is_scc_firmware_updated",
    "is_load_on",
    "is_battery_voltage_to_steady_while_charging",
    "is_charging_on",
    "is_scc_charging_on",
    "is_ac_charging_on",
]


def parse_qpigs(payload: str) -> dict[str, Any]:
    parts = payload.split()

    result: dict[str, Any] = {"_command": "QPIGS"}

    for name, value in zip(_QPIGS_FIELDS, parts):
        try:
            result[name] = float(value)
        except ValueError:
            result[name] = value

    # Champ "device status" : chaîne de 8 caractères '0'/'1', juste après
    # battery_discharge_current dans une trame PI30 standard.
    if len(parts) > len(_QPIGS_FIELDS):
        status = parts[len(_QPIGS_FIELDS)]
        if len(status) == len(_DEVICE_STATUS_BITS):
            for bit_name, bit_value in zip(_DEVICE_STATUS_BITS, status):
                result[bit_name] = bit_value == "1"

    # Puissance PV : pas toujours native selon le firmware -> calculée en secours.
    if "pv_input_power" not in result and "pv_input_voltage" in result and "pv_input_current_for_battery" in result:
        try:
            result["pv_input_power"] = round(
                result["pv_input_voltage"] * result["pv_input_current_for_battery"], 1
            )
        except TypeError:
            pass

    return result


# ---------------------------------------------------------------------------
# QPIRI — Réglages actuels de l'onduleur
# ---------------------------------------------------------------------------

_OUTPUT_SOURCE_PRIORITY_MAP = {
    "0": "Utility first",
    "1": "Solar first",
    "2": "SBU first",
}

_CHARGER_SOURCE_PRIORITY_MAP = {
    "0": "Utility first",
    "1": "Solar first",
    "2": "Solar and utility",
    "3": "Solar only",
}

_QPIRI_FIELDS = [
    "grid_rating_voltage",
    "grid_rating_current",
    "ac_output_rating_voltage",
    "ac_output_rating_frequency",
    "ac_output_rating_current",
    "ac_output_rating_apparent_power",
    "ac_output_rating_active_power",
    "battery_rating_voltage",
    "battery_recharge_voltage",
    "battery_under_voltage",
    "battery_bulk_voltage",
    "battery_float_voltage",
    "battery_type_code",
    "max_ac_charging_current",
    "max_charging_current",
    "input_voltage_range",
    "output_source_priority_code",
    "charger_source_priority_code",
    "parallel_max_num",
    "machine_type",
    "topology",
    "output_mode",
]


def parse_qpiri(payload: str) -> dict[str, Any]:
    parts = payload.split()
    result: dict[str, Any] = {"_command": "QPIRI"}

    for name, value in zip(_QPIRI_FIELDS, parts):
        try:
            result[name] = float(value)
        except ValueError:
            result[name] = value

    if "output_source_priority_code" in result:
        code = str(int(result["output_source_priority_code"]))
        result["output_source_priority"] = _OUTPUT_SOURCE_PRIORITY_MAP.get(code, "Unknown")

    if "charger_source_priority_code" in result:
        code = str(int(result["charger_source_priority_code"]))
        result["charger_source_priority"] = _CHARGER_SOURCE_PRIORITY_MAP.get(code, "Unknown")

    return result


# ---------------------------------------------------------------------------
# Commandes d'écriture (changement de priorité de sortie)
# ---------------------------------------------------------------------------

OUTPUT_MODE_COMMANDS = {
    "E2C": "POP00",       # Utility first
    "SOLAIRE": "POP01",   # Solar first
    "BATTERIE": "POP02",  # SBU first
}

# PCP<NN> — priorité de CHARGE (différent de POP, qui est la priorité de
# SORTIE). "MIXTE" = Solar + Utility, "SOLAIRE_SEUL" = uniquement si le
# solaire suffit (protège la batterie de toute charge secteur).
CHARGER_PRIORITY_COMMANDS = {
    "E2C": "PCP00",           # Utility first
    "SOLAIRE": "PCP01",       # Solar first
    "MIXTE": "PCP02",         # Solar + Utility
    "SOLAIRE_SEUL": "PCP03",  # Solar only
}


def build_max_charging_current_command(amps: int) -> str:
    """MCHGC<nnn> — courant de charge max (toutes sources). La valeur doit
    faire partie des paliers acceptés par CET onduleur (interrogeables via
    QMCHGCR, non encore implémenté) — une valeur hors paliers renvoie NAK,
    ne casse rien mais n'est pas appliquée."""
    return f"MCHGC{amps:03d}"


def build_max_utility_charging_current_command(amps: int) -> str:
    """MUCHGC<nnn> — courant de charge max sur réseau uniquement. Mêmes
    réserves que ci-dessus (paliers spécifiques à l'onduleur)."""
    return f"MUCHGC{amps:03d}"


@dataclass
class AckResponse:
    ok: bool
    raw: str = field(default="")

    @classmethod
    def from_payload(cls, payload: str) -> "AckResponse":
        return cls(ok=payload.strip().upper().startswith("ACK"), raw=payload)
