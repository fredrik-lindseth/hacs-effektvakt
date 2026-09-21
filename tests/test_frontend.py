"""Tester for frontend-registrering og websocket-kommandoen effektvakt/faceplate."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.effektvakt import async_setup
from custom_components.effektvakt.const import (
    FRONTEND_CARD_FILENAME,
    FRONTEND_URL_BASE,
    WS_TYPE_FACEPLATE,
)
from custom_components.effektvakt.frontend import ws_faceplate
from tests.conftest import make_entry

MANIFEST = json.loads((Path(__file__).parent.parent / "custom_components/effektvakt/manifest.json").read_text())


def make_hass(entries: list | None = None) -> MagicMock:
    """hass-mock med tom data-dict og HTTP-registrering som AsyncMock."""
    hass = MagicMock()
    hass.data = {}
    hass.http.async_register_static_paths = AsyncMock()
    hass.config_entries.async_entries = MagicMock(return_value=list(entries or []))
    return hass


def integration_mock(versjon: str | None = MANIFEST["version"]) -> AsyncMock:
    integration = MagicMock()
    integration.version = versjon
    return AsyncMock(return_value=integration)


# --- async_setup ----------------------------------------------------------


@pytest.mark.asyncio
async def test_async_setup_registrerer_static_path_en_gang():
    hass = make_hass()
    with (
        patch("custom_components.effektvakt.frontend.frontend"),
        patch("custom_components.effektvakt.frontend.websocket_api"),
        patch("custom_components.effektvakt.frontend.async_get_integration", integration_mock()),
    ):
        assert await async_setup(hass, {}) is True

    hass.http.async_register_static_paths.assert_called_once()
    (konfigurasjoner,) = hass.http.async_register_static_paths.call_args.args
    assert len(konfigurasjoner) == 1
    konfig = konfigurasjoner[0]
    assert konfig.url_path == FRONTEND_URL_BASE
    assert Path(konfig.path).name == "frontend"
    assert Path(konfig.path).is_dir()
    assert konfig.cache_headers is True


@pytest.mark.asyncio
async def test_async_setup_melder_js_url_med_cache_buster():
    hass = make_hass()
    with (
        patch("custom_components.effektvakt.frontend.frontend") as ha_frontend,
        patch("custom_components.effektvakt.frontend.websocket_api"),
        patch("custom_components.effektvakt.frontend.async_get_integration", integration_mock()),
    ):
        await async_setup(hass, {})

    ha_frontend.add_extra_js_url.assert_called_once()
    _hass_arg, url = ha_frontend.add_extra_js_url.call_args.args
    assert url == f"{FRONTEND_URL_BASE}/{FRONTEND_CARD_FILENAME}?v={MANIFEST['version']}"


@pytest.mark.asyncio
async def test_async_setup_registrerer_websocket_kommandoen():
    hass = make_hass()
    with (
        patch("custom_components.effektvakt.frontend.frontend"),
        patch("custom_components.effektvakt.frontend.websocket_api") as ws,
        patch("custom_components.effektvakt.frontend.async_get_integration", integration_mock()),
    ):
        await async_setup(hass, {})

    ws.async_register_command.assert_called_once_with(hass, ws_faceplate)


@pytest.mark.asyncio
async def test_async_setup_registrerer_ikke_paa_nytt():
    """To kall skal ikke gi to static paths: den andre ville feilet i HA."""
    hass = make_hass()
    with (
        patch("custom_components.effektvakt.frontend.frontend") as ha_frontend,
        patch("custom_components.effektvakt.frontend.websocket_api") as ws,
        patch("custom_components.effektvakt.frontend.async_get_integration", integration_mock()),
    ):
        await async_setup(hass, {})
        await async_setup(hass, {})

    assert hass.http.async_register_static_paths.call_count == 1
    assert ha_frontend.add_extra_js_url.call_count == 1
    assert ws.async_register_command.call_count == 1


@pytest.mark.asyncio
async def test_async_setup_taaler_manifest_uten_versjon():
    hass = make_hass()
    with (
        patch("custom_components.effektvakt.frontend.frontend") as ha_frontend,
        patch("custom_components.effektvakt.frontend.websocket_api"),
        patch("custom_components.effektvakt.frontend.async_get_integration", integration_mock(None)),
    ):
        await async_setup(hass, {})

    _hass_arg, url = ha_frontend.add_extra_js_url.call_args.args
    assert url.endswith("?v=0")


def test_manifest_har_avhengighetene_frontendregistreringen_krever():
    """hass.data-nokkelen frontend bruker opprettes i frontends egen async_setup."""
    assert set(MANIFEST["dependencies"]) == {"http", "frontend", "websocket_api"}


# --- websocket-handleren --------------------------------------------------


def make_ws_hass(entry, *, entity_entry=None, entries: list | None = None) -> MagicMock:
    hass = make_hass(entries if entries is not None else ([entry] if entry else []))
    hass.config_entries.async_get_entry = MagicMock(return_value=entry)
    return hass


def registry_patch(entity_entry):
    er_mock = MagicMock()
    er_mock.async_get.return_value.async_get.return_value = entity_entry
    return patch("custom_components.effektvakt.frontend.er", er_mock)


@pytest.mark.asyncio
async def test_ws_faceplate_finner_entry_via_entity_registry():
    entry = make_entry(dso="bkk")
    entry.domain = "effektvakt"
    entry.runtime_data = None
    entity_entry = MagicMock()
    entity_entry.config_entry_id = entry.entry_id
    # Bare entity registry skal avgjoere: ingen entries aa falle tilbake paa.
    hass = make_ws_hass(entry, entries=[])
    connection = MagicMock()

    with registry_patch(entity_entry):
        await ws_faceplate(hass, connection, {"id": 4, "entity_id": "sensor.effektvakt_topp_3_snitt"})

    connection.send_error.assert_not_called()
    msg_id, resultat = connection.send_result.call_args.args
    assert msg_id == 4
    assert resultat["svg"].startswith("<svg")
    assert 'data-variant="card"' in resultat["svg"]
    assert resultat["maks_kw"] == 15.0
    assert resultat["dso_navn"] == "BKK"
    # Trinnene kommer fra DSO-oppslaget naar coordinatoren ikke er lastet.
    assert 'data-kr="155"' in resultat["svg"]


@pytest.mark.asyncio
async def test_ws_faceplate_faller_tilbake_paa_eneste_entry():
    entry = make_entry(dso="bkk")
    entry.domain = "effektvakt"
    entry.runtime_data = None
    hass = make_ws_hass(entry)
    connection = MagicMock()

    with registry_patch(None):
        await ws_faceplate(hass, connection, {"id": 1})

    _msg_id, resultat = connection.send_result.call_args.args
    assert resultat["svg"].startswith("<svg")


@pytest.mark.asyncio
async def test_ws_faceplate_bruker_trinn_fra_coordinatoren():
    entry = make_entry(dso="bkk")
    entry.domain = "effektvakt"
    entry.runtime_data = MagicMock()
    entry.runtime_data.kapasitetstrinn = [(5.0, 99), (float("inf"), 199)]
    hass = make_ws_hass(entry)
    connection = MagicMock()

    with registry_patch(None):
        await ws_faceplate(hass, connection, {"id": 2})

    _msg_id, resultat = connection.send_result.call_args.args
    assert 'data-kr="99"' in resultat["svg"]
    assert 'data-kr="155"' not in resultat["svg"]


@pytest.mark.asyncio
async def test_ws_faceplate_bruker_egendefinerte_trinn_naar_entryen_ikke_er_lastet():
    entry = make_entry(dso="bkk", kapasitetstrinn_custom=[[4.0, 123], [8.0, 456]])
    entry.domain = "effektvakt"
    entry.runtime_data = None
    hass = make_ws_hass(entry)
    connection = MagicMock()

    with registry_patch(None):
        await ws_faceplate(hass, connection, {"id": 6})

    _msg_id, resultat = connection.send_result.call_args.args
    assert 'data-kr="123"' in resultat["svg"]
    assert 'data-kr="155"' not in resultat["svg"]


@pytest.mark.asyncio
async def test_ws_faceplate_respekterer_maks_kw():
    entry = make_entry(dso="bkk")
    entry.domain = "effektvakt"
    entry.runtime_data = None
    hass = make_ws_hass(entry)
    connection = MagicMock()

    with registry_patch(None):
        await ws_faceplate(hass, connection, {"id": 3, "maks_kw": 20})

    _msg_id, resultat = connection.send_result.call_args.args
    # 20 rundes opp til naermeste multiplum av 15 saa hovedtallene blir hele.
    assert resultat["maks_kw"] == 30.0
    assert 'data-maks-kw="30"' in resultat["svg"]


@pytest.mark.asyncio
async def test_ws_faceplate_uten_entry_gir_feil():
    hass = make_ws_hass(None, entries=[])
    connection = MagicMock()

    with registry_patch(None):
        await ws_faceplate(hass, connection, {"id": 9})

    connection.send_result.assert_not_called()
    msg_id, kode, _tekst = connection.send_error.call_args.args
    assert msg_id == 9
    assert kode == "not_found"


@pytest.mark.asyncio
async def test_ws_faceplate_gir_feil_naar_flere_entries_og_ukjent_entitet():
    entry_a = make_entry(entry_id="a")
    entry_b = make_entry(entry_id="b")
    hass = make_ws_hass(None, entries=[entry_a, entry_b])
    connection = MagicMock()

    with registry_patch(None):
        await ws_faceplate(hass, connection, {"id": 5, "entity_id": "sensor.ukjent"})

    connection.send_result.assert_not_called()
    connection.send_error.assert_called_once()


def test_ws_kommandotypen_er_den_kortet_kaller():
    assert WS_TYPE_FACEPLATE == "effektvakt/faceplate"
