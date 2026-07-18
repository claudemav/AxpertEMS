"""Entité de base : rattache chaque entité au même appareil 'Onduleur Axpert'."""

from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AxpertCoordinator


class AxpertEntity(CoordinatorEntity[AxpertCoordinator]):
    """Classe de base : gère le DeviceInfo commun et l'unique_id."""

    # Volontairement PAS de has_entity_name=True : on veut des entity_id
    # identiques à l'ancien système (sensor.axpert_grid_voltage, etc.) pour
    # que les YAML existants (energy_flows, meters, dashboards) n'aient
    # rien à changer lors de la bascule.

    def __init__(self, coordinator: AxpertCoordinator, unique_id_suffix: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{unique_id_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "inverter")},
            name="Onduleur Axpert",
            manufacturer="Voltronic / Axpert",
            model="PI30",
        )
