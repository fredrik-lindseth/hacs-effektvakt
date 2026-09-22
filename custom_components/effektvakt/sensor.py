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
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, RISIKO_LEVELS

# Inngaar i unique_id, saa den er laast av entitetsregisteret.
TILGJENGELIG_KUTT_KEY = "tilgjengelig_kutt"

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
    """Set up sensors from config entry.

    Sensoren for tilgjengelig kutt opprettes bare naar brukeren faktisk har
    konfigurert kuttbare laster. Uten laster finnes det ikke noe svar aa gi,
    og en sensor som viser et anslag ingen har gitt grunnlag for er verre enn
    ingen sensor: den stod paa 0,3 kW hele doegnet fram til september 2026, og
    tallet var en antagelse om en varmtvannsbereder vi ikke visste om fantes.
    """
    coordinator: EffektvaktCoordinator = entry.runtime_data
    sensorer: list[SensorEntity] = [
        EffektvaktProjisertSensor(coordinator),
        EffektvaktMarginSensor(coordinator),
        EffektvaktTopp3Sensor(coordinator),
        EffektvaktRisikoSensor(coordinator),
        EffektvaktKostnadNesteTrinnSensor(coordinator),
    ]
    if coordinator.laster:
        sensorer.append(EffektvaktTilgjengeligKuttSensor(coordinator))
    else:
        _glem_tilgjengelig_kutt(hass, entry)
    async_add_entities(sensorer)


def _glem_tilgjengelig_kutt(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Ta sensoren ut av entitetsregisteret naar siste last er fjernet.

    Uten dette blir den staaende som `unavailable` i det uendelige: registeret
    husker entiteter plattformen slutter aa opprette, og brukeren maa slette
    den for haand. Kommer en last tilbake, opprettes sensoren paa nytt med den
    samme unique_id-en, saa historikken henger med.
    """
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_{TILGJENGELIG_KUTT_KEY}")
    if entity_id:
        registry.async_remove(entity_id)


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
            "minutter_igjen_av_timen": d.get("minutter_igjen_av_timen"),
            "actual_kwh_this_hour": d.get("actual_kwh_this_hour"),
            "current_kw": d.get("current_kw"),
            # Referansen marginen måles mot, i den rekkefølgen den regnes ut:
            # måltrinnet, taket for dagen, og taket for timen vi står i.
            "maal_terskel_kw": d.get("maal_terskel_kw"),
            "maal_trinn_kr": d.get("maal_trinn_kr"),
            "dagstak_kw": d.get("dagstak_kw"),
            "time_tak_kw": d.get("time_tak_kw"),
            "dagens_maks_kw": d.get("dagens_maks_kw"),
            "topp_2_andre_dager_kw": d.get("topp_2_andre_dager_kw"),
            "kutt_anbefalt_kw": d.get("kutt_anbefalt_kw"),
            "kan_legge_paa_kw": d.get("kan_legge_paa_kw"),
            # Marginen oversatt til last man kan slaa paa naa: margin delt paa
            # resten av timen. Ti minutter igjen gjoer 1 kW margin til 6 kW.
            "kan_legge_paa_resten_av_timen_kw": d.get("kan_legge_paa_resten_av_timen_kw"),
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
    """Hvor mye timen vi står i har igjen før den flytter måneden opp et trinn.

    Marginen måles mot `time_tak_kw`, og attributtene viser hele regnestykket:
    `maal_terskel_kw` er trinnet måneden kan ende på, `dagstak_kw` hva dagen i
    dag tåler gitt de to høyeste andre dagene, og `time_tak_kw` det samme med
    dagens eget dagsmaks lagt inn. Referansen flytter seg gjennom måneden,
    derfor står den i klartekst.
    """

    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = "kW"
    _attr_state_class = SensorStateClass.MEASUREMENT

    _sensor_key = "margin_til_neste_trinn"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get("margin_kw") if self.coordinator.data else None


class EffektvaktTopp3Sensor(_EffektvaktBaseSensor):
    """Topp-3-snittet måneden har låst inn: sum av inntil tre dagsmaks delt på tre.

    Alltid delt på tre, også med færre enn tre dager. Da stiger tallet gjennom
    måneden og faller aldri, og det er samtidig en nedre skranke for hva
    måneden kan ende på. Delte vi på antall dager i stedet, ville en rolig dag
    nummer tre dratt tallet ned og gitt inntrykk av at noe var reddet.
    """

    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = "kW"
    _attr_state_class = SensorStateClass.MEASUREMENT

    _sensor_key = "topp_3_snitt_denne_maned"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get("topp_3_snitt_denne_maned_kw") if self.coordinator.data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        d = self.coordinator.data
        if not d:
            return None
        felles = super().extra_state_attributes or {}
        return {
            **felles,
            "topp_3_dager": d.get("topp_3_dager"),
            "topp_3_inkluderer_i_dag": d.get("topp_3_inkluderer_i_dag"),
            "dag_som_ryker": d.get("dag_som_ryker"),
        }


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
    """Summen av de konfigurerte lastene som trekker over terskelen sin akkurat nå.

    Finnes bare når minst én last er konfigurert, se `async_setup_entry`.
    Tilstanden er summen av `effekt_w` for kildene med `teller_med: true` i
    attributtet `kutt_kilder`, så tallet kan alltid forklares av lista.
    """

    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = "kW"
    _attr_state_class = SensorStateClass.MEASUREMENT

    _sensor_key = TILGJENGELIG_KUTT_KEY

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
            "kutt_kilder": d.get("kutt_kilder"),
            "kuttet_naa_kw": d.get("kuttet_naa_kw"),
        }


class EffektvaktKostnadNesteTrinnSensor(_EffektvaktBaseSensor):
    """Kronene den inneværende timen er i ferd med å låse inn.

    Tilstanden er `kostnad_denne_timen_kr`, ikke hoppet til neste trinn. Hoppet
    står fast hele måneden, og en sensor som viser det samme tallet i 30 døgn
    er en attributtpose, ikke en måling. Timens kostnad er null nesten alltid
    og spiker i det timen faktisk flytter måneden opp et trinn, og det er den
    en graf og en automasjon kan gjøre noe med. Hoppet ligger i attributtet
    `kostnad_neste_trinn_kr`.
    """

    # Ingen device_class: MONETARY krever ISO-valutakode som enhet og en total-state_class,
    # og satser holdes i kr/mnd, slik strømkalkulator gjør det. Timens kostnad er
    # også kr/mnd: det er månedsregningen timen flytter, ikke en timepris.
    _attr_native_unit_of_measurement = "kr/mnd"
    _attr_state_class = SensorStateClass.MEASUREMENT

    _sensor_key = "kostnad_neste_trinn"

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("kostnad_denne_timen_kr") if self.coordinator.data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        d = self.coordinator.data
        if not d:
            return None
        felles = super().extra_state_attributes or {}
        return {
            **felles,
            "kostnad_neste_trinn_kr": d.get("kostnad_neste_trinn_kr"),
            "trinn_na_kr": d.get("trinn_na_kr"),
            "trinn_na_ovre_grense_kw": d.get("trinn_na_ovre_grense_kw"),
            "trinn_neste_kr": d.get("trinn_neste_kr"),
            "besparelse_trinn_under_kr": d.get("besparelse_trinn_under_kr"),
            "trinn_under_terskel_kw": d.get("trinn_under_terskel_kw"),
            "trinn_under_oppnaelig": d.get("trinn_under_oppnaelig"),
            "trinn_under_realistisk": d.get("trinn_under_realistisk"),
            "kostnad_denne_timen_kr": d.get("kostnad_denne_timen_kr"),
            "topp_3_projisert_kw": d.get("topp_3_projisert_kw"),
            "minste_mulige_topp_3_kw": d.get("minste_mulige_topp_3_kw"),
            "kapasitetstrinn": _kapasitetstrinn_json(self.coordinator.kapasitetstrinn),
        }
