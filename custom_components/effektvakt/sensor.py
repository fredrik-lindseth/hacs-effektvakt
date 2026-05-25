"""Sensor-plattformer for Effektvakt."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import RISIKO_LEVELS

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
    """Set up sensors from config entry."""
    coordinator: EffektvaktCoordinator = entry.runtime_data
    async_add_entities(
        [
            EffektvaktProjisertSensor(coordinator),
            EffektvaktMarginSensor(coordinator),
            EffektvaktTopp3Sensor(coordinator),
            EffektvaktRisikoSensor(coordinator),
            EffektvaktTilgjengeligKuttSensor(coordinator),
        ]
    )


class _EffektvaktBaseSensor(CoordinatorEntity, SensorEntity):
    """Felles base for Effektvakt-sensorer."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EffektvaktCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{self._sensor_key}"

    @property
    def _sensor_key(self) -> str:
        raise NotImplementedError

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        d = self.coordinator.data
        if not d:
            return None
        return {
            "elapsed_minutes_in_hour": d.get("elapsed_minutes_in_hour"),
            "actual_kwh_this_hour": d.get("actual_kwh_this_hour"),
            "current_kw": d.get("current_kw"),
            "next_tier_threshold_kw": d.get("next_tier_threshold_kw"),
            "next_tier_pris_per_maned": d.get("next_tier_pris_per_maned"),
            "prev_tier_threshold_kw": d.get("prev_tier_threshold_kw"),
            "effective_threshold_kw": d.get("effective_threshold_kw"),
            "kutt_anbefalt_kw": d.get("kutt_anbefalt_kw"),
            "topp_2_snitt_denne_maned_kw": d.get("topp_2_snitt_denne_maned_kw"),
            "last_update": d.get("last_update"),
        }


class EffektvaktProjisertSensor(_EffektvaktBaseSensor):
    _attr_name = "Projisert time-snitt"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = "kW"
    _attr_state_class = SensorStateClass.MEASUREMENT

    _sensor_key = "projisert_time_snitt"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get("projected_avg_kw") if self.coordinator.data else None


class EffektvaktMarginSensor(_EffektvaktBaseSensor):
    _attr_name = "Margin til neste trinn"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = "kW"
    _attr_state_class = SensorStateClass.MEASUREMENT

    _sensor_key = "margin_til_neste_trinn"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get("margin_kw") if self.coordinator.data else None


class EffektvaktTopp3Sensor(_EffektvaktBaseSensor):
    _attr_name = "Topp-3 snitt denne måned"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = "kW"
    _attr_state_class = SensorStateClass.MEASUREMENT

    _sensor_key = "topp_3_snitt_denne_maned"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get("topp_3_snitt_denne_maned_kw") if self.coordinator.data else None


class EffektvaktRisikoSensor(_EffektvaktBaseSensor):
    _attr_name = "Risiko-nivå"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options: ClassVar[list[str]] = list(RISIKO_LEVELS)

    _sensor_key = "risiko_niva"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.get("risiko_niva") if self.coordinator.data else None

    @property
    def options(self) -> list[str]:
        return list(RISIKO_LEVELS)


class EffektvaktTilgjengeligKuttSensor(_EffektvaktBaseSensor):
    _attr_name = "Tilgjengelig kutt"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = "kW"
    _attr_state_class = SensorStateClass.MEASUREMENT

    _sensor_key = "tilgjengelig_kutt"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get("tilgjengelig_kutt_kw") if self.coordinator.data else None
