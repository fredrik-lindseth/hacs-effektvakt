"""Livssyklusen i en ekte Home Assistant.

Det ``tests/`` ikke kan se: at manifestet faktisk lar seg laste, at
avhengighetene settes opp, at plattformene legger entiteter i den ekte
tilstandsmaskinen og entitetsregisteret, og at oppsettet taaler aa bli lastet
ut og lastet paa nytt. Stubbene i ``tests/`` sier ja til alt dette uansett.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component

from custom_components.effektvakt.const import DOMAIN

from .conftest import ALLE_ENTITETER, BINARY_SENSOR_ID, SENSOR_IDS, SWITCH_ID, lag_entry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

# Tjenestene er domenetjenester uten maal, registrert en gang for alle entries.
TJENESTER = ("set_safety_buffer", "reset_topp_3")


async def test_entryen_lastes_og_gir_hele_entitetsflaten(hass: HomeAssistant, oppsett: MockConfigEntry) -> None:
    """Seks sensorer, en binary_sensor og en switch, med id-ene docs lover."""
    assert oppsett.state is ConfigEntryState.LOADED
    for entity_id in ALLE_ENTITETER:
        assert hass.states.get(entity_id) is not None, f"{entity_id} kom aldri i tilstandsmaskinen"


async def test_unique_id_ene_er_entry_id_pluss_noekkel(hass: HomeAssistant, oppsett: MockConfigEntry) -> None:
    """Registeret laaser id-ene, saa noekkelen er kontrakt mot brukerens historikk."""
    registry = er.async_get(hass)
    for entity_id in ALLE_ENTITETER:
        oppforing = registry.async_get(entity_id)
        assert oppforing is not None, entity_id
        assert oppforing.unique_id.startswith(f"{oppsett.entry_id}_")
        assert oppforing.config_entry_id == oppsett.entry_id


async def test_alle_entitetene_henger_paa_en_enhet(hass: HomeAssistant, oppsett: MockConfigEntry) -> None:
    """En enhet per oppsett, og alt henger paa den. To enheter deler dashbordet i to."""
    enheter = dr.async_entries_for_config_entry(dr.async_get(hass), oppsett.entry_id)
    assert len(enheter) == 1
    enhet = enheter[0]

    registry = er.async_get(hass)
    assert {e.entity_id for e in er.async_entries_for_device(registry, enhet.id)} == set(ALLE_ENTITETER)


async def test_manifest_avhengighetene_settes_faktisk_opp(hass: HomeAssistant, oppsett: MockConfigEntry) -> None:
    """frontend.py trenger alle fire, og HA setter dem opp foer oss.

    Ryker en av dem ut av manifestet, laster integrasjonen fortsatt i
    ``tests/``, mens en ekte HA ville satt oss opp foer det vi bygger paa.
    """
    for komponent in ("http", "frontend", "lovelace", "websocket_api"):
        assert komponent in hass.config.components, komponent


async def test_domenet_kan_settes_opp_uten_yaml(hass: HomeAssistant) -> None:
    """CONFIG_SCHEMA finnes og godtar en konfigurasjon uten vaart domene.

    Uten skjemaet feller hassfest, og den porten er det eneste som merker
    det: ``tests/`` importerer modulen med stubbet HA og ser aldri
    konfigurasjonsvalideringen.
    """
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()


async def test_yaml_oppsett_av_domenet_melder_fra_til_brukeren(hass: HomeAssistant) -> None:
    """``effektvakt:`` i configuration.yaml gir en reparasjonssak, ikke stillhet.

    Det er den konkrete oppfoerselen ``config_entry_only_config_schema`` har:
    oppsettet gaar videre, men brukeren faar beskjed om at YAML ikke er veien
    inn. Et skjema som bare *fantes* ville sagt ja her uten aa si fra.
    """
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {"dso": "bkk"}})
    await hass.async_block_till_done()

    saker = ir.async_get(hass).issues
    assert ("homeassistant", f"config_entry_only_{DOMAIN}") in saker


async def test_tjenestene_registreres_og_kan_kalles(hass: HomeAssistant, oppsett: MockConfigEntry) -> None:
    """Kallet gaar gjennom den ekte tjenesteregistreringen, med skjemaet fra services.yaml."""
    for tjeneste in TJENESTER:
        assert hass.services.has_service(DOMAIN, tjeneste), tjeneste

    await hass.services.async_call(DOMAIN, "set_safety_buffer", {"kw": 2.5}, blocking=True)
    await hass.async_block_till_done()
    assert oppsett.runtime_data.safety_buffer_kw == 2.5

    await hass.services.async_call(DOMAIN, "reset_topp_3", {}, blocking=True)
    await hass.async_block_till_done()


async def test_unload_tar_med_seg_entiteter_og_tjenester(hass: HomeAssistant, oppsett: MockConfigEntry) -> None:
    """Siste entry ut slukker lyset: ingen entiteter, ingen tjenester igjen."""
    assert await hass.config_entries.async_unload(oppsett.entry_id)
    await hass.async_block_till_done()

    assert oppsett.state is ConfigEntryState.NOT_LOADED
    for entity_id in ALLE_ENTITETER:
        tilstand = hass.states.get(entity_id)
        # Registrerte entiteter blir staaende som «restored» og unavailable
        # naar plattformen er ute. Poenget er at de ikke fortsetter aa svare
        # med et tall ingen lenger regner ut.
        assert tilstand is not None and tilstand.state == STATE_UNAVAILABLE, entity_id
    for tjeneste in TJENESTER:
        assert not hass.services.has_service(DOMAIN, tjeneste), tjeneste


async def test_tjenestene_overlever_at_ett_av_to_oppsett_lastes_ut(
    hass: HomeAssistant, oppsett: MockConfigEntry
) -> None:
    """Tjenestene er domenetjenester: de ryddes foerst naar siste entry er ute."""
    andre = lag_entry(power_sensor="sensor.hytte_effekt")
    hass.states.async_set("sensor.hytte_effekt", "800", {"unit_of_measurement": "W", "device_class": "power"})
    andre.add_to_hass(hass)
    assert await hass.config_entries.async_setup(andre.entry_id)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(oppsett.entry_id)
    await hass.async_block_till_done()
    assert hass.services.has_service(DOMAIN, "set_safety_buffer")

    assert await hass.config_entries.async_unload(andre.entry_id)
    await hass.async_block_till_done()
    assert not hass.services.has_service(DOMAIN, "set_safety_buffer")


async def test_endrede_innstillinger_laster_oppsettet_paa_nytt(hass: HomeAssistant, oppsett: MockConfigEntry) -> None:
    """Oppdateringslytteren er koblet paa, og reloaden gaar helt rundt."""
    forste = oppsett.runtime_data

    hass.config_entries.async_update_entry(oppsett, data={**oppsett.data, "safety_buffer_kw": 3.0})
    await hass.async_block_till_done()

    assert oppsett.state is ConfigEntryState.LOADED
    assert oppsett.runtime_data is not forste
    assert oppsett.runtime_data.safety_buffer_kw == 3.0
    for entity_id in ALLE_ENTITETER:
        assert hass.states.get(entity_id) is not None, entity_id


@pytest.mark.parametrize(
    ("entity_id", "plattform"),
    [
        *[(sid, "sensor") for sid in SENSOR_IDS],
        (BINARY_SENSOR_ID, "binary_sensor"),
        (SWITCH_ID, "switch"),
    ],
)
async def test_visningsnavnet_kommer_fra_oversettelsen(
    hass: HomeAssistant, oppsett: MockConfigEntry, entity_id: str, plattform: str
) -> None:
    """has_entity_name pluss translation_key gir «Effektvakt <navn>» i UI-et.

    Teksten hentes fra translations/en.json her i testen framfor aa skrives
    av: da beviser testen at noekkelen slaar opp, uten aa maatte rettes hver
    gang noen formulerer et navn om.
    """
    oversettelser = json.loads(
        (Path(__file__).resolve().parents[1] / "custom_components/effektvakt/translations/en.json").read_text(
            encoding="utf-8"
        )
    )
    noekkel = er.async_get(hass).async_get(entity_id).translation_key
    forventet = oversettelser["entity"][plattform][noekkel]["name"]

    assert hass.states.get(entity_id).attributes["friendly_name"] == f"Effektvakt {forventet}"
