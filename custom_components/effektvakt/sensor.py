"""Sensor-plattformer for Effektvakt."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, ClassVar

from homeassistant.components.sensor import (
    ENTITY_ID_FORMAT,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, RISIKO_LEVELS

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
            EffektvaktKostnadNesteTrinnSensor(coordinator),
        ]
    )


def _kapasitetstrinn_json(trinn: list[tuple[float, int]]) -> list[list[float | int | None]]:
    """Trinn-tabellen som [kW, kr]-par et dashboard kan lese.

    Øverste terskel er float("inf") internt. inf er ugyldig JSON og knekker både
    recorder og websocket, så den sendes som None.
    """
    return [[None if math.isinf(terskel) else terskel, pris] for terskel, pris in trinn]


class _EffektvaktBaseSensor(CoordinatorEntity, SensorEntity):
    """Felles base for Effektvakt-sensorer."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EffektvaktCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = self._sensor_key
        # Entitets-id-en settes eksplisitt fordi HA ellers utleder object_id-en
        # fra det engelske entitetsnavnet, og da ville en fersk installasjon
        # fått sensor.effektvakt_projected_hourly_average. Docs, blueprintene og
        # kortet navngir de norske id-ene, og de skal stå likt på alle språk.
        # Eksisterende entiteter beholder id-en sin uansett, den er låst av
        # entitetsregisteret gjennom unique_id.
        self.entity_id = ENTITY_ID_FORMAT.format(f"{DOMAIN}_{self._sensor_key}")
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{self._sensor_key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name="Effektvakt",
            manufacturer="Effektvakt",
            model="Kapasitetstrinn-styring",
        )

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
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = "kW"
    _attr_state_class = SensorStateClass.MEASUREMENT

    _sensor_key = "projisert_time_snitt"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get("projected_avg_kw") if self.coordinator.data else None


class EffektvaktMarginSensor(_EffektvaktBaseSensor):
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = "kW"
    _attr_state_class = SensorStateClass.MEASUREMENT

    _sensor_key = "margin_til_neste_trinn"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get("margin_kw") if self.coordinator.data else None


class EffektvaktTopp3Sensor(_EffektvaktBaseSensor):
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = "kW"
    _attr_state_class = SensorStateClass.MEASUREMENT

    _sensor_key = "topp_3_snitt_denne_maned"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get("topp_3_snitt_denne_maned_kw") if self.coordinator.data else None


class EffektvaktRisikoSensor(_EffektvaktBaseSensor):
    """Hvor nær neste kapasitetstrinn timen ligger an til å komme."""

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
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = "kW"
    _attr_state_class = SensorStateClass.MEASUREMENT

    _sensor_key = "tilgjengelig_kutt"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get("tilgjengelig_kutt_kw") if self.coordinator.data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        d = self.coordinator.data
        if not d:
            return None
        felles = super().extra_state_attributes or {}
        return {
            **felles,
            "kutt_strategi": d.get("kutt_strategi"),
            "vvb_power_w": d.get("vvb_power_w"),
            "ekstra_power_w_total": d.get("ekstra_power_w_total"),
            "kutt_kilder": d.get("kutt_kilder"),
        }


class EffektvaktKostnadNesteTrinnSensor(_EffektvaktBaseSensor):
    """Kronene per måned som står på spill mellom trinnet vi ligger an til og neste."""

    # Ingen device_class: MONETARY krever ISO-valutakode som enhet og en total-state_class,
    # og satser holdes i kr/mnd, slik strømkalkulator gjør det.
    _attr_native_unit_of_measurement = "kr/mnd"
    _attr_state_class = SensorStateClass.MEASUREMENT

    _sensor_key = "kostnad_neste_trinn"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("kostnad_neste_trinn_kr") if self.coordinator.data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        d = self.coordinator.data
        if not d:
            return None
        felles = super().extra_state_attributes or {}
        return {
            **felles,
            "trinn_na_kr": d.get("trinn_na_kr"),
            "trinn_na_ovre_grense_kw": d.get("trinn_na_ovre_grense_kw"),
            "trinn_neste_kr": d.get("trinn_neste_kr"),
            "besparelse_trinn_under_kr": d.get("besparelse_trinn_under_kr"),
            "trinn_under_oppnaelig": d.get("trinn_under_oppnaelig"),
            "kostnad_denne_timen_kr": d.get("kostnad_denne_timen_kr"),
            "topp_3_projisert_kw": d.get("topp_3_projisert_kw"),
            "minste_mulige_topp_3_kw": d.get("minste_mulige_topp_3_kw"),
            "kapasitetstrinn": _kapasitetstrinn_json(self.coordinator.kapasitetstrinn),
        }
