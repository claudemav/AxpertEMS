"""Entité de base : rattache chaque entité à l'appareil de SON entrée de config.

CORRIGÉ pour le multi-onduleurs : unique_id et DeviceInfo sont désormais
scopés par entry.entry_id (avant : globaux au domaine, ce qui aurait
créé des collisions avec une deuxième entrée de config). has_entity_name
= True : l'entity_id devient déterministe, dérivé automatiquement du
nom d'appareil + translation_key — plus de renommage manuel à
synchroniser entre le composant et les fichiers YAML qui le référencent
(cause du bug entity_id désynchronisé rencontré en août 2026).
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_NAME, DEFAULT_NAME, DOMAIN
from .coordinator import AxpertCoordinator


class AxpertEntity(CoordinatorEntity[AxpertCoordinator]):
    """Classe de base : gère le DeviceInfo scopé par entrée et l'unique_id."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AxpertCoordinator,
        entry: ConfigEntry,
        unique_id_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{unique_id_suffix}"
        device_name = entry.data.get(CONF_NAME, DEFAULT_NAME)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=device_name,
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