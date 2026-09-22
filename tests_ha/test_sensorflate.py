"""Entitetsflaten slik Home Assistant selv ser den.

``tests/`` leser ``_attr_*`` fra klassene gjennom stubber. Det sier hva koden
mente, ikke hva HA gjorde med det. Her leses tilstandsmaskinen og
sensor-komponentens egne tabeller: fikk enhetene en gyldig kombinasjon av
``device_class`` og enhet, ble enum-sensoren godtatt, og taaler attributtene
turen gjennom websocket og recorder.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pytest
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.sensor.const import DEVICE_CLASS_UNITS
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.json import json_dumps
from homeassistant.util import slugify

from custom_components.effektvakt.const import RISIKO_LEVELS

from .conftest import BINARY_SENSOR_ID, SENSOR_IDS, SWITCH_ID

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

# kW-sensorene: samme device_class, enhet og state_class hele veien. Trekker
# noen en av dem ut, er det her det vises, ikke i attributtlisten.
EFFEKTSENSORER = (
    "sensor.effektvakt_projisert_time_snitt",
    "sensor.effektvakt_margin_til_neste_trinn",
    "sensor.effektvakt_topp_3_snitt_denne_maned",
    "sensor.effektvakt_tilgjengelig_kutt",
)


@pytest.mark.parametrize("entity_id", EFFEKTSENSORER)
async def test_effektsensorene_er_kw_med_maalt_effekt(
    hass: HomeAssistant, oppsett: MockConfigEntry, entity_id: str
) -> None:
    """device_class power, enhet kW, state_class measurement."""
    attributter = hass.states.get(entity_id).attributes
    assert attributter["device_class"] == SensorDeviceClass.POWER
    assert attributter["unit_of_measurement"] == "kW"
    assert attributter["state_class"] == "measurement"


@pytest.mark.parametrize("entity_id", EFFEKTSENSORER)
async def test_enheten_er_en_home_assistant_godtar_for_device_class_en(
    hass: HomeAssistant, oppsett: MockConfigEntry, entity_id: str
) -> None:
    """Paret staar i HA sin egen tabell, og gjoer det i begge HA-versjonene.

    Et ugyldig par gir statistikk som ikke konverterer og en enhetsvelger som
    ikke virker, og HA sier fra om det med en advarsel i loggen som er lett
    aa overse. Tabellen er kilden, saa testen felles hvis en framtidig HA
    slutter aa godta kW her.
    """
    attributter = hass.states.get(entity_id).attributes
    assert attributter["unit_of_measurement"] in DEVICE_CLASS_UNITS[attributter["device_class"]]


async def test_risikosensoren_er_et_enum_med_alle_nivaaene(hass: HomeAssistant, oppsett: MockConfigEntry) -> None:
    """HA avviser en enum-sensor med enhet, state_class eller ukjent tilstand.

    Sensoren staar altsaa i tilstandsmaskinen fordi valideringen gikk
    gjennom, og verdiene er de automasjonene sammenligner mot.
    """
    tilstand = hass.states.get("sensor.effektvakt_risiko_niva")
    assert tilstand.attributes["device_class"] == SensorDeviceClass.ENUM
    assert tilstand.attributes["options"] == RISIKO_LEVELS
    assert "unit_of_measurement" not in tilstand.attributes
    assert "state_class" not in tilstand.attributes
    assert tilstand.state in RISIKO_LEVELS


async def test_kostnadssensoren_har_kroner_per_maaned_uten_device_class(
    hass: HomeAssistant, oppsett: MockConfigEntry
) -> None:
    """MONETARY ville krevd ISO-valutakode som enhet, og satsene er kr/mnd."""
    attributter = hass.states.get("sensor.effektvakt_kostnad_neste_trinn").attributes
    assert "device_class" not in attributter
    assert attributter["unit_of_measurement"] == "kr/mnd"
    assert attributter["state_class"] == "measurement"


def _ikke_endelige_tall(verdi: object, sti: str = "") -> list[str]:
    """Stiene inn til hver float som ikke er et endelig tall."""
    if isinstance(verdi, dict):
        return [f for n, v in verdi.items() for f in _ikke_endelige_tall(v, f"{sti}.{n}")]
    if isinstance(verdi, list | tuple):
        return [f for i, v in enumerate(verdi) for f in _ikke_endelige_tall(v, f"{sti}[{i}]")]
    if isinstance(verdi, float) and not math.isfinite(verdi):
        return [f"{sti} = {verdi}"]
    return []


@pytest.mark.parametrize("entity_id", [*SENSOR_IDS, BINARY_SENSOR_ID, SWITCH_ID])
async def test_ingen_attributter_er_inf_eller_nan(
    hass: HomeAssistant, oppsett: MockConfigEntry, entity_id: str
) -> None:
    """Oeverste kapasitetstrinn er ``float("inf")`` internt, og maa bli None ut.

    Serialiseringen fanger det ikke: orjson, som websocket og recorder bruker,
    gjoer stille om inf til null. Da forsvinner ikke problemet, det bare
    flytter seg til dashbordet, som viser en tom oeverste terskel uten at noe
    har sagt fra. Derfor sjekkes verdiene, ikke om de lot seg serialisere.
    """
    attributter = dict(hass.states.get(entity_id).attributes)
    assert _ikke_endelige_tall(attributter, entity_id) == []
    # Serialiseringen skal likevel gaa: en verdi orjson ikke kjenner, som en
    # dato eller et dataclass-objekt, ville stoppet websocketen.
    json_dumps(attributter)


@pytest.mark.parametrize("entity_id", [*SENSOR_IDS, BINARY_SENSOR_ID, SWITCH_ID])
async def test_entitets_id_en_foelger_ikke_spraaket_i_navnet(
    hass: HomeAssistant, oppsett: MockConfigEntry, entity_id: str
) -> None:
    """Norsk id, engelsk visningsnavn, i den samme entiteten.

    HA utleder ellers object_id-en fra entitetsnavnet, og navnet kommer fra
    oversettelsen. Uten den eksplisitte entity_id-en hadde en fersk
    installasjon paa engelsk faatt ``sensor.effektvakt_projected_hourly_average``,
    og docs, blueprintene og kortet hadde pekt i tomme luften. ``hass``-fixturen
    kjoerer paa engelsk, saa spriket er synlig her og bare her.
    """
    assert hass.config.language == "en"
    oppforing = er.async_get(hass).async_get(entity_id)
    assert oppforing is not None
    # Navnet er oversatt, id-en er det ikke. Hadde HA laget id-en av navnet,
    # ville slugen av navnet vaert halen i entity_id-en.
    navne_slug = slugify(oppforing.original_name)
    assert not entity_id.endswith(navne_slug)
