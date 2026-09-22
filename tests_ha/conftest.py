"""Conftest for ekte-HA-testene.

Dette treet kjoeres mot en ekte Home Assistant fra
pytest-homeassistant-custom-component, i motsetning til ``tests/``, som stubber
``homeassistant.*`` i ``sys.modules``. De to kan ikke dele miljoe: stubbene og
den ekte pakken ville kollidert i samme ``sys.modules``. Derfor ligger de i
hvert sitt katalogtre med hver sin conftest, og i hvert sitt virtuelle miljoe
(``just test-unit`` mot gruppen ``unit``, ``just test-ha`` mot ``ha-minimum``
eller ``ha-current``).

Arbeidsdelingen mellom de to treene er med vilje skarp: ``tests/`` eier
regnestykkene og alt som kan avgjoeres uten HA, og dette treet eier bare det
som krever en ekte Home Assistant, altsaa flytmotoren, tilstandsmaskinen,
entitetsregisteret, HTTP-laget, Lovelace-ressursene og timerne. En test som
ville gaatt like godt i ``tests/`` hoerer ikke hjemme her: da er det to steder
aa vedlikeholde og ett svar.

Kjoeres via ``just test-ha target=minimum|current``.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

# Repo-roten paa sys.path, slik at baade `import custom_components.effektvakt`
# og HA-loaderens egen `import custom_components` finner integrasjonen.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from custom_components.effektvakt.const import (  # noqa: E402  (etter sys.path)
    CONF_DSO,
    CONF_ENERGY_SENSOR,
    CONF_POWER_SENSOR,
    DOMAIN,
)

# --- hass_frontend ---------------------------------------------------------
#
# manifest.json lister `frontend` som avhengighet, saa Home Assistant setter
# den opp foer Effektvakt. Frontend-komponenten importerer `hass_frontend` for
# aa finne de bygde web-filene, og den pakken er ikke en avhengighet av
# homeassistant-hjulet: den installeres av HA sin egen installer og veier godt
# over 50 MB. Uten den feiler oppsettet av `frontend`, og dermed av oss.
#
# Alternativet til aa staa inne for pakken her ville vaert aa markere
# `frontend` som alt satt opp i hass.config.components. Da ville
# `add_extra_js_url` kastet KeyError paa foerste kall, fordi UrlManager-en den
# skriver i opprettes nettopp i frontend sitt async_setup. Reserveveien i
# frontend.py ville altsaa vaert utestbar. Derfor faar den ekte komponenten
# lastes, mot et tomt filtre: det er bare stier den trenger, ikke innhold.
_FRONTEND_FILER = (
    "service_worker.js",
    "sw-modern.js",
    "sw-modern.js.map",
    "sw-legacy.js",
    "sw-legacy.js.map",
    "robots.txt",
    "onboarding.html",
    "authorize.html",
    "index.html",
)
# aiohttp sin StaticResource kaster paa en katalog som ikke finnes, saa disse
# tre maa eksistere. Filene over 404-er hoeyst i en forespoersel ingen gjoer.
_FRONTEND_KATALOGER = ("static", "frontend_latest", "frontend_es5")


def _installer_hass_frontend_stedfortreder() -> None:
    """Legg en `hass_frontend` med tomme filer i sys.modules, om den mangler."""
    if importlib.util.find_spec("hass_frontend") is not None:
        return

    rot = Path(tempfile.mkdtemp(prefix="hass_frontend_")) / "hass_frontend"
    rot.mkdir(parents=True)
    for navn in _FRONTEND_FILER:
        (rot / navn).write_text("")
    for navn in _FRONTEND_KATALOGER:
        (rot / navn).mkdir()

    modul = types.ModuleType("hass_frontend")
    modul.where = lambda rot=rot: rot  # type: ignore[attr-defined]
    sys.modules["hass_frontend"] = modul


_installer_hass_frontend_stedfortreder()


def _start_pycares_avslutningstraad() -> None:
    """Start pycares sin bakgrunnstraad foer foerste test, ikke under den.

    aiohttp-testklienten slaar opp navn gjennom aiodns, og pycares starter en
    daemon-traad foerste gang en kanal rives ned. Plugin-en sin
    ``verify_cleanup`` feller enhver test som etterlater seg en ny traad, saa
    uten dette ville den foerste testen som henter kortet over HTTP feilet i
    teardown, og hvilken test det ble hadde avhengt av rekkefoelgen.
    """
    try:
        import pycares
    except ImportError:  # aiodns er ikke installert i alle HA-versjoner
        return
    manager = getattr(pycares, "_shutdown_manager", None)
    if manager is not None:
        manager.start()


_start_pycares_avslutningstraad()

POWER_SENSOR = "sensor.hus_effekt"
ENERGY_SENSOR = "sensor.hus_energi"

# Entitetene integrasjonen skal legge i tilstandsmaskinen. Id-ene er kontrakt:
# de staar i docs, i blueprintene og i kortet, og de er laast av
# entitetsregisteret gjennom unique_id.
SENSOR_IDS: tuple[str, ...] = (
    "sensor.effektvakt_projisert_time_snitt",
    "sensor.effektvakt_margin_til_neste_trinn",
    "sensor.effektvakt_topp_3_snitt_denne_maned",
    "sensor.effektvakt_risiko_niva",
    "sensor.effektvakt_tilgjengelig_kutt",
    "sensor.effektvakt_kostnad_neste_trinn",
)
BINARY_SENSOR_ID = "binary_sensor.effektvakt_kutt_ned_anbefalt"
SWITCH_ID = "switch.effektvakt_automatikk"
ALLE_ENTITETER: tuple[str, ...] = (*SENSOR_IDS, BINARY_SENSOR_ID, SWITCH_ID)


def pytest_collection_modifyitems(session, config, items: list) -> None:
    """Tom collection er roedt.

    Et ekte-HA-miljoe som ikke fant en eneste test har ikke bevist noe. Uten
    denne vakten ville `just test-ha` gaatt groenn paa en feilstavet sti eller
    en import som stille sluttet aa samles inn.
    """
    if not items:
        pytest.exit("tests_ha samlet inn null tester. Det er roedt, ikke groent.", returncode=1)


@pytest.fixture(autouse=True)
def _enable_custom(enable_custom_integrations):
    """Slaa paa lasting av custom_components/ for alle ekte-HA-tester."""
    yield


@pytest.fixture(autouse=True)
def _ingen_ekte_http_server():
    """Hindre at http-komponenten aapner en ekte lytteport.

    ``http`` starter web-serveren sin i det ``frontend`` er satt opp, og vi
    drar inn frontend gjennom manifestet. pytest-socket blokkerer socketen,
    HA svelger feilen, og hver eneste test hadde faatt et stacktrace i loggen
    for noe som ikke er vaart. Testklienten snakker uansett direkte med
    ``hass.http.app`` og trenger ingen lytteport.
    """
    with patch("homeassistant.components.http.HomeAssistantHTTP.start"):
        yield


@pytest.fixture
def maalere(hass: HomeAssistant) -> None:
    """Effekt- og energimaaleren config flowen og coordinatoren leser.

    Enhetene er de config_flow.py godtar, saa en test som vil se en avvisning
    setter sin egen tilstand framfor aa bruke denne.
    """
    hass.states.async_set(
        POWER_SENSOR,
        "1500",
        {"unit_of_measurement": "W", "device_class": "power", "friendly_name": "Hus effekt"},
    )
    hass.states.async_set(
        ENERGY_SENSOR,
        "12345.0",
        {
            "unit_of_measurement": "kWh",
            "device_class": "energy",
            "state_class": "total_increasing",
            "friendly_name": "Hus energi",
        },
    )


def lag_entry(**overstyr: Any) -> MockConfigEntry:
    """En config entry slik config flowen ville skrevet den."""
    data: dict[str, Any] = {
        CONF_DSO: "bkk",
        CONF_POWER_SENSOR: POWER_SENSOR,
        CONF_ENERGY_SENSOR: ENERGY_SENSOR,
    }
    data.update(overstyr)
    return MockConfigEntry(
        domain=DOMAIN,
        title="BKK",
        data=data,
        unique_id=f"{DOMAIN}_{data[CONF_POWER_SENSOR]}",
    )


@pytest.fixture
async def oppsett(hass: HomeAssistant, maalere: None) -> MockConfigEntry:
    """Effektvakt lastet i en ekte Home Assistant, med entiteter i drift."""
    entry = lag_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
