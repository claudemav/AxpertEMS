"""Entité de base : rattache chaque entité au même appareil 'Onduleur Axpert'."""

from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AxpertCoordinator


class AxpertEntity(CoordinatorEntity[AxpertCoordinator]):
    """Classe de base : gère le DeviceInfo commun et l'unique_id."""

    def __init__(self, coordinator: AxpertCoordinator, unique_id_suffix: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{unique_id_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "inverter")},
            name="Onduleur Axpert",
            manufacturer="Voltronic / Axpert",
            model="PI30",
        )


class AxpertDiagnosticEntity(AxpertEntity):
    """Base pour les entités de santé (communication, erreurs, échecs
    consécutifs...). Reste TOUJOURS disponible, même quand le coordinator
    est en échec dur (last_update_success=False) — sinon ces entités
    disparaîtraient exactement au moment où elles sont le plus utiles
    (pendant une vraie panne série)."""

    @property
    def available(self) -> bool:
        return True
