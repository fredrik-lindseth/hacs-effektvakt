"""Tester for frontend-registrering og websocket-kommandoen effektvakt/faceplate."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.effektvakt import async_remove_entry, async_setup
from custom_components.effektvakt.const import (
    FRONTEND_CARD_FILENAME,
    FRONTEND_DIR_NAME,
    FRONTEND_URL_BASE,
    WS_TYPE_FACEPLATE,
)
from custom_components.effektvakt.faceplate import (
    PALETT,
    PALETT_GOSSEN,
    STILNAVN,
    tilgjengelige_stiler,
)
from custom_components.effektvakt.frontend import ws_faceplate
from tests.conftest import make_entry

PAKKE = Path(__file__).parent.parent / "custom_components/effektvakt"
MANIFEST = json.loads((PAKKE / "manifest.json").read_text())


def kortets_fargeroller() -> set[str]:
    """Rollenavnene kortets CSS slaar opp som custom properties."""
    css = (PAKKE / FRONTEND_DIR_NAME / FRONTEND_CARD_FILENAME).read_text()
    return set(re.findall(r"--effektvakt-([a-z0-9-]+)", css))


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


KORT_URL = f"{FRONTEND_URL_BASE}/{FRONTEND_CARD_FILENAME}?v={MANIFEST['version']}"

# Ressursene i Fredriks eget register. De skal staa uroert etter alt vi gjoer.
HACS_RESSURSER = [
    {"id": "a", "url": "/hacsfiles/battery-state-card/battery-state-card.js?hacstag=1", "type": "module"},
    {"id": "b", "url": "/hacsfiles/kiosk-mode/kiosk-mode.js?hacstag=2", "type": "module"},
]


class FakeRessurser:
    """Speiler ResourceStorageCollection saa langt frontend.py bruker den."""

    def __init__(self, items: list | None = None) -> None:
        self.items = [dict(item) for item in (items or [])]
        self.opprettet: list[dict] = []
        self.oppdatert: list[tuple[str, dict]] = []
        self.slettet: list[str] = []
        self.lastet = 0

    async def async_get_info(self) -> dict[str, int]:
        self.lastet += 1
        return {"resources": len(self.items)}

    def async_items(self) -> list[dict]:
        return list(self.items)

    async def async_create_item(self, data: dict) -> dict:
        item = {"id": f"ny-{len(self.items)}", "url": data["url"], "type": data["res_type"]}
        self.items.append(item)
        self.opprettet.append(dict(data))
        return item

    async def async_update_item(self, item_id: str, updates: dict) -> dict:
        self.oppdatert.append((item_id, dict(updates)))
        for item in self.items:
            if item["id"] == item_id:
                item.update({"url": updates["url"], "type": updates["res_type"]})
                return item
        raise KeyError(item_id)

    async def async_delete_item(self, item_id: str) -> None:
        self.slettet.append(item_id)
        self.items = [item for item in self.items if item["id"] != item_id]

    def urler(self) -> list[str]:
        return [item["url"] for item in self.items]


class YamlRessurser:
    """ResourceYAMLCollection: kan leses, men ikke skrives i."""

    def __init__(self, items: list | None = None) -> None:
        self.items = list(items or [])

    async def async_get_info(self) -> dict[str, int]:
        return {"resources": len(self.items)}

    def async_items(self) -> list[dict]:
        return list(self.items)


class SprengtRessurser(FakeRessurser):
    """Et register som feiler, slik en oedelagt lagerfil ville gjort."""

    async def async_get_info(self) -> dict[str, int]:
        raise OSError("lagerfila er oedelagt")


def med_lovelace(hass: MagicMock, ressurser: object) -> MagicMock:
    """Heng en ressurssamling paa hass.data slik Lovelace gjoer."""
    hass.data["lovelace"] = MagicMock(resources=ressurser)
    return hass


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
    assert Path(konfig.path).name == FRONTEND_DIR_NAME
    assert Path(konfig.path).is_dir()
    assert konfig.cache_headers is True


@pytest.mark.asyncio
async def test_async_setup_uten_lovelace_faller_tilbake_paa_js_url():
    """Uten et skrivbart register er add_extra_js_url det eneste vi har."""
    hass = make_hass()
    with (
        patch("custom_components.effektvakt.frontend.frontend") as ha_frontend,
        patch("custom_components.effektvakt.frontend.websocket_api"),
        patch("custom_components.effektvakt.frontend.async_get_integration", integration_mock()),
    ):
        await async_setup(hass, {})

    ha_frontend.add_extra_js_url.assert_called_once()
    _hass_arg, url = ha_frontend.add_extra_js_url.call_args.args
    assert url == KORT_URL


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
    """lovelace maa vaere satt opp foer oss, ellers finnes ikke ressursregisteret."""
    assert set(MANIFEST["dependencies"]) == {"http", "frontend", "lovelace", "websocket_api"}


def test_static_katalogen_kolliderer_ikke_med_modulnavnet():
    """En katalog frontend/ ville skygget for frontend.py og stoppet importen."""
    assert (PAKKE / FRONTEND_DIR_NAME).is_dir()
    assert not (PAKKE / "frontend").exists()


# --- Lovelace-ressursen ---------------------------------------------------


VERSJON = MANIFEST["version"]


async def kjor_setup(hass: MagicMock, *, versjon: str | None = VERSJON, ganger: int = 1) -> MagicMock:
    """Kjoer async_setup med HA-modulene stubbet. Gir frontend-stubben tilbake."""
    with (
        patch("custom_components.effektvakt.frontend.frontend") as ha_frontend,
        patch("custom_components.effektvakt.frontend.websocket_api"),
        patch("custom_components.effektvakt.frontend.async_get_integration", integration_mock(versjon)),
    ):
        for _ in range(ganger):
            await async_setup(hass, {})
    return ha_frontend


@pytest.mark.asyncio
async def test_registrerer_kortet_som_lovelace_ressurs():
    """Lovelace venter paa ressursene sine, saa kortet maa staa der."""
    ressurser = FakeRessurser(HACS_RESSURSER)
    hass = med_lovelace(make_hass(), ressurser)

    ha_frontend = await kjor_setup(hass)

    assert ressurser.opprettet == [{"res_type": "module", "url": KORT_URL}]
    assert ressurser.urler() == [*[r["url"] for r in HACS_RESSURSER], KORT_URL]
    # Da trengs ikke reserveveien, og to veier inn til samme fil unngaas.
    ha_frontend.add_extra_js_url.assert_not_called()


@pytest.mark.asyncio
async def test_skriver_ikke_naar_oppforingen_alt_staar_riktig():
    """Registeret er brukerens eget: ingen skriving uten grunn."""
    ressurser = FakeRessurser([*HACS_RESSURSER, {"id": "e", "url": KORT_URL, "type": "module"}])
    hass = med_lovelace(make_hass(), ressurser)

    await kjor_setup(hass)

    assert ressurser.opprettet == []
    assert ressurser.oppdatert == []
    assert ressurser.slettet == []


@pytest.mark.asyncio
async def test_oppdaterer_oppforingen_naar_versjonen_endrer_seg():
    """Ny ?v= skal oppdatere den samme oppfoeringen, ikke legge en ny ved siden av."""
    gammel = {"id": "e", "url": f"{FRONTEND_URL_BASE}/{FRONTEND_CARD_FILENAME}?v=0.0.1", "type": "module"}
    ressurser = FakeRessurser([*HACS_RESSURSER, gammel])
    hass = med_lovelace(make_hass(), ressurser)

    await kjor_setup(hass)

    assert ressurser.oppdatert == [("e", {"res_type": "module", "url": KORT_URL})]
    assert ressurser.opprettet == []
    assert ressurser.urler().count(KORT_URL) == 1
    assert len(ressurser.items) == len(HACS_RESSURSER) + 1


@pytest.mark.asyncio
async def test_rydder_duplikater_av_vaar_egen_oppforing():
    """Har en tidligere utgave lagt inn to, skal vi ende paa en."""
    ressurser = FakeRessurser(
        [
            {"id": "e1", "url": KORT_URL, "type": "module"},
            *HACS_RESSURSER,
            {"id": "e2", "url": f"{FRONTEND_URL_BASE}/{FRONTEND_CARD_FILENAME}?v=0.0.1", "type": "module"},
        ]
    )
    hass = med_lovelace(make_hass(), ressurser)

    await kjor_setup(hass)

    assert ressurser.slettet == ["e2"]
    assert ressurser.urler() == [KORT_URL, *[r["url"] for r in HACS_RESSURSER]]


@pytest.mark.asyncio
async def test_reload_og_omstart_gir_bare_en_oppforing():
    """Flere kall skal ikke kunne legge kortet inn to ganger."""
    ressurser = FakeRessurser(HACS_RESSURSER)
    hass = med_lovelace(make_hass(), ressurser)

    await kjor_setup(hass, ganger=3)

    assert ressurser.urler().count(KORT_URL) == 1
    assert len(ressurser.opprettet) == 1


@pytest.mark.asyncio
async def test_yaml_modus_faller_tilbake_paa_js_url():
    """YAML-registeret er skrivebeskyttet, og da er reserveveien det vi har."""
    hass = med_lovelace(make_hass(), YamlRessurser())

    ha_frontend = await kjor_setup(hass, ganger=2)

    # En gang, ikke en per kall: dobbel import() ville definert kortet to ganger.
    ha_frontend.add_extra_js_url.assert_called_once_with(hass, KORT_URL)


@pytest.mark.asyncio
async def test_feil_i_registeret_velter_ikke_oppstarten():
    hass = med_lovelace(make_hass(), SprengtRessurser(HACS_RESSURSER))

    ha_frontend = await kjor_setup(hass)

    ha_frontend.add_extra_js_url.assert_called_once_with(hass, KORT_URL)


@pytest.mark.asyncio
async def test_async_remove_entry_fjerner_bare_vaar_oppforing():
    ressurser = FakeRessurser([*HACS_RESSURSER, {"id": "e", "url": KORT_URL, "type": "module"}])
    hass = med_lovelace(make_hass(entries=[]), ressurser)

    await async_remove_entry(hass, make_entry())

    assert ressurser.urler() == [r["url"] for r in HACS_RESSURSER]


@pytest.mark.asyncio
async def test_async_remove_entry_beholder_oppforingen_naar_flere_oppsett_staar_igjen():
    ressurser = FakeRessurser([*HACS_RESSURSER, {"id": "e", "url": KORT_URL, "type": "module"}])
    hass = med_lovelace(make_hass(entries=[make_entry()]), ressurser)

    await async_remove_entry(hass, make_entry(entry_id="borte"))

    assert KORT_URL in ressurser.urler()


@pytest.mark.asyncio
async def test_async_remove_entry_taaler_yaml_modus_og_feil():
    for samling in (YamlRessurser([{"id": "e", "url": KORT_URL}]), SprengtRessurser(HACS_RESSURSER)):
        hass = med_lovelace(make_hass(entries=[]), samling)
        await async_remove_entry(hass, make_entry())


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
    # 20 er en skalatopp som gir hele hovedtall, saa den brukes som den er.
    assert resultat["maks_kw"] == 20.0
    assert 'data-maks-kw="20"' in resultat["svg"]


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


@pytest.mark.asyncio
async def test_ws_faceplate_gir_stilregister_og_palett():
    """Kortet skal slippe aa kopiere hverken stilnavn eller farger."""
    entry = make_entry(dso="bkk")
    entry.domain = "effektvakt"
    entry.runtime_data = None
    hass = make_ws_hass(entry)
    connection = MagicMock()

    with registry_patch(None):
        await ws_faceplate(hass, connection, {"id": 10})

    _msg_id, resultat = connection.send_result.call_args.args
    assert resultat["stil"] == STILNAVN[0]
    assert resultat["stiler"] == tilgjengelige_stiler()
    # Rollenavnene kortets CSS slaar opp. Bommer de, faller fargene stille
    # tilbake paa reserven i kortet, saa de sjekkes her.
    assert kortets_fargeroller() <= set(resultat["palett"])
    assert resultat["palett"]["emalje"] == PALETT["emalje"]


@pytest.mark.asyncio
async def test_ws_faceplate_tegner_valgt_stil():
    entry = make_entry(dso="bkk")
    entry.domain = "effektvakt"
    entry.runtime_data = None
    hass = make_ws_hass(entry)
    connection = MagicMock()

    with registry_patch(None):
        await ws_faceplate(hass, connection, {"id": 11, "stil": "gossen"})

    _msg_id, resultat = connection.send_result.call_args.args
    assert resultat["stil"] == "gossen"
    assert 'data-stil="gossen"' in resultat["svg"]
    # Gossen overstyrer emaljen i sin egen palett.
    assert resultat["palett"]["emalje"] == PALETT_GOSSEN["emalje"]


def test_kortet_slaar_opp_fargeroller_som_finnes():
    """Bommer kortet paa et rollenavn, faller fargen stille tilbake paa reserven."""
    roller = kortets_fargeroller()
    assert roller
    assert roller <= set(PALETT), f"kortet bruker roller som ikke finnes: {roller - set(PALETT)}"
