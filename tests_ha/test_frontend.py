"""Kortet, servert og meldt inn av en ekte Home Assistant.

Kveldens dyreste feil bodde her: kortet tegnet seg ikke ved kald lasting
fordi ``add_extra_js_url`` la inn et ``import()`` ingen ventet paa.
``tests/`` kunne ikke se det, for der er baade HTTP-laget og
Lovelace-registeret fakes vi selv har skrevet, og en fake sier det den er
bedt om aa si.

Her gaar det gjennom HA sitt eget: en HTTP-klient som henter kortfilen, det
ekte ressursregisteret til Lovelace, og en ekte websocket-tilkobling.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.components import frontend
from homeassistant.setup import async_setup_component

from custom_components.effektvakt.const import (
    DOMAIN,
    FRONTEND_CARD_FILENAME,
    FRONTEND_URL_BASE,
    WS_TYPE_FACEPLATE,
)
from custom_components.effektvakt.frontend import LOVELACE_DATA_KEY

from .conftest import lag_entry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

KORT_URL = f"{FRONTEND_URL_BASE}/{FRONTEND_CARD_FILENAME}"
KORTFIL = Path(__file__).resolve().parents[1] / "custom_components/effektvakt/www" / FRONTEND_CARD_FILENAME
MANIFEST = Path(__file__).resolve().parents[1] / "custom_components/effektvakt/manifest.json"


def _manifestversjon() -> str:
    return str(json.loads(MANIFEST.read_text(encoding="utf-8"))["version"])


def _ressurssamling(hass: HomeAssistant):
    """Lovelace sitt ekte ressursregister, uansett hvordan HA lagrer det."""
    data = hass.data[LOVELACE_DATA_KEY]
    return data["resources"] if isinstance(data, dict) else data.resources


def _ressurser(hass: HomeAssistant) -> list[dict]:
    """Oppfoeringene i ressursregisteret som peker paa kortet."""
    return [i for i in _ressurssamling(hass).async_items() if i["url"].split("?", 1)[0] == KORT_URL]


def _ekstra_modul_urler(hass: HomeAssistant) -> set[str]:
    """URL-ene add_extra_js_url har lagt inn, altsaa reserveveien."""
    return set(hass.data[frontend.DATA_EXTRA_MODULE_URL].urls)


async def test_kortet_serveres_uten_innlogging(
    hass: HomeAssistant, oppsett: MockConfigEntry, hass_client_no_auth
) -> None:
    """Lovelace laster kortet som en modul, foer brukeren er autentisert.

    Filen som kommer ut skal vaere den i repoet, ikke en kopi som har drevet
    fra hverandre.
    """
    klient = await hass_client_no_auth()
    svar = await klient.get(KORT_URL)

    assert svar.status == 200
    assert await svar.text() == KORTFIL.read_text(encoding="utf-8")


async def test_statisk_servering_staar_allerede_foer_foerste_oppsett(hass: HomeAssistant, hass_client_no_auth) -> None:
    """``async_setup`` serverer kortet, saa en HA uten entries har det ogsaa.

    Uten dette ville et dashbord med kortet vist «Konfigurasjonsfeil» helt
    til noen la inn et oppsett.
    """
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    klient = await hass_client_no_auth()
    assert (await klient.get(KORT_URL)).status == 200


async def test_kortet_er_meldt_inn_som_lovelace_ressurs_med_cache_buster(
    hass: HomeAssistant, oppsett: MockConfigEntry
) -> None:
    """Noeyaktig en oppfoering, av typen module, med ``?v=`` fra manifestet.

    Cache-busteren er ikke pynt: uten den serverer nettleseren forrige
    versjon av kortet etter en oppdatering.
    """
    vaare = _ressurser(hass)
    assert len(vaare) == 1
    assert vaare[0]["url"] == f"{KORT_URL}?v={_manifestversjon()}"
    assert vaare[0]["type"] == "module"


async def test_ressursregisteret_er_veien_inn_og_ikke_add_extra_js_url(
    hass: HomeAssistant, oppsett: MockConfigEntry
) -> None:
    """To veier inn til samme fil gir to innlastinger og en kastende define.

    ``add_extra_js_url`` er reserveveien for Lovelace i YAML-modus. Naar
    registeret tok imot, skal den staa urort. Her leses HA sin egen
    URL-samling, altsaa den index-HTML-en faktisk bygges av.
    """
    assert _ressurser(hass)
    assert not [u for u in _ekstra_modul_urler(hass) if u.startswith(FRONTEND_URL_BASE)]


async def test_reload_gir_ikke_en_ny_ressursoppforing(hass: HomeAssistant, oppsett: MockConfigEntry) -> None:
    """Registeret deles med HACS og brukeren, saa vi skal ikke gro i det."""
    await hass.config_entries.async_reload(oppsett.entry_id)
    await hass.async_block_till_done()

    assert len(_ressurser(hass)) == 1


async def test_oppforingen_ryddes_naar_siste_oppsett_fjernes(hass: HomeAssistant, oppsett: MockConfigEntry) -> None:
    """``async_remove_entry`` tar kortet ut igjen ved avinstallasjon."""
    assert _ressurser(hass)

    await hass.config_entries.async_remove(oppsett.entry_id)
    await hass.async_block_till_done()

    assert _ressurser(hass) == []


async def test_oppforingen_blir_staaende_saa_lenge_ett_oppsett_er_igjen(
    hass: HomeAssistant, oppsett: MockConfigEntry
) -> None:
    andre = lag_entry(power_sensor="sensor.hytte_effekt")
    hass.states.async_set("sensor.hytte_effekt", "800", {"unit_of_measurement": "W"})
    andre.add_to_hass(hass)
    assert await hass.config_entries.async_setup(andre.entry_id)
    await hass.async_block_till_done()

    await hass.config_entries.async_remove(oppsett.entry_id)
    await hass.async_block_till_done()

    assert len(_ressurser(hass)) == 1


async def test_websocket_kommandoen_leverer_skiven(
    hass: HomeAssistant, oppsett: MockConfigEntry, hass_ws_client
) -> None:
    """Kortet henter skiven over websocket framfor aa tegne den i JavaScript.

    Kallet gaar gjennom HA sin ekte websocket-server her, saa baade
    registreringen, skjemavalideringen og serialiseringen av svaret er med.
    En SVG med inf i seg, eller en palett med en verdi orjson ikke kjenner,
    ville stoppet nettopp her.
    """
    klient = await hass_ws_client(hass)
    await klient.send_json({"id": 1, "type": WS_TYPE_FACEPLATE})
    svar = await klient.receive_json()

    assert svar["success"], svar
    resultat = svar["result"]
    assert resultat["svg"].lstrip().startswith("<svg")
    assert resultat["dso_navn"]
    assert resultat["stiler"]
    assert resultat["palett"]


async def test_websocket_kommandoen_avviser_en_ugyldig_stil(
    hass: HomeAssistant, oppsett: MockConfigEntry, hass_ws_client
) -> None:
    """Skjemaet paa kommandoen er HA sitt, og det skal si nei her."""
    klient = await hass_ws_client(hass)
    await klient.send_json({"id": 1, "type": WS_TYPE_FACEPLATE, "stil": "finnes-ikke"})
    svar = await klient.receive_json()

    assert not svar["success"]
    assert svar["error"]["code"] == "invalid_format"


async def test_websocket_kommandoen_sier_fra_naar_ingen_entry_finnes(hass: HomeAssistant, hass_ws_client) -> None:
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    klient = await hass_ws_client(hass)
    await klient.send_json({"id": 1, "type": WS_TYPE_FACEPLATE})
    svar = await klient.receive_json()

    assert not svar["success"]
    assert svar["error"]["code"] == "not_found"
