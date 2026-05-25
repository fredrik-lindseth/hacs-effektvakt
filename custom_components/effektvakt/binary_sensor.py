"""Binary sensor for Effektvakt."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, RISIKO_RANK

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import EffektvaktCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EffektvaktCoordinator = entry.runtime_data
    async_add_entities([EffektvaktKuttNedAnbefaltBinarySensor(coordinator)])


class EffektvaktKuttNedAnbefaltBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """`on` når hysteresefull risiko >= min_risiko_for_kutt."""

    _attr_has_entity_name = True
    _attr_name = "Kutt ned anbefalt"

    def __init__(self, coordinator: EffektvaktCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_kutt_ned_anbefalt"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name="Effektvakt",
            manufacturer="Effektvakt",
            model="Kapasitetstrinn-styring",
        )

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        nivå = self.coordinator.data.get("risiko_niva")
        if nivå is None:
            return None
        threshold = self.coordinator.min_risiko_for_kutt
        return RISIKO_RANK.get(nivå, -1) >= RISIKO_RANK.get(threshold, 99)
