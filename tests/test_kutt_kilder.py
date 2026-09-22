"""Tester for kutt_kilder: kontrakten mot dashbordet og kortet.

Reglene bak tallene står i test_laster.py. Her er det veien gjennom
coordinatoren som prøves: at sensorene og bryterne leses fra tilstandsmaskinen,
at attributtet tåler JSON, og at summen alltid kan forklares av lista.
"""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.effektvakt.coordinator import EffektvaktCoordinator
from custom_components.effektvakt.sensor import EffektvaktTilgjengeligKuttSensor
from tests.conftest import make_entry, make_hass_with_states, make_state

BEREDER = "sensor.bereder_effekt"
BEREDER_BRYTER = "switch.bereder"
KABLER = "sensor.varmekabler_bad"

LASTER = [
    {
        "effekt_sensor": BEREDER,
        "navn": "Bereder",
        "bryter": BEREDER_BRYTER,
        "terskel_w": 1000.0,
    },
    {"effekt_sensor": KABLER, "terskel_w": 100.0},
]


def _make_coordinator(states, *, laster=None):
    entry = make_entry(safety_buffer_kw=0.5)
    entry.data["laster"] = LASTER if laster is None else laster
    hass = make_hass_with_states(states)
    with patch("custom_components.effektvakt.coordinator.Store"):
        coord = EffektvaktCoordinator(hass, entry)
    coord._store = MagicMock()
    coord._store.async_load = AsyncMock(return_value=None)
    coord._store.async_save = AsyncMock()
    return coord


async def _tick(coord, *, now=datetime(2026, 5, 25, 14, 30, 0)):
    with patch("custom_components.effektvakt.coordinator.dt_util_now", return_value=now):
        return await coord._async_update_data()


def _base_states(bereder="1800", kabler="550", bryter="on"):
    return {
        "sensor.power": make_state("500", unit="W"),
        "sensor.energy": make_state("100.0", unit="kWh"),
        BEREDER: make_state(bereder, unit="W", friendly_name="Bereder effekt"),
        KABLER: make_state(kabler, unit="W", friendly_name="Varmekabler bad"),
        BEREDER_BRYTER: make_state(bryter),
    }


@pytest.mark.asyncio
async def test_coordinator_eksponerer_lastene_med_navn_og_bryter():
    data = await _tick(_make_coordinator(_base_states()))
    assert data["kutt_kilder"] == [
        {
            "entity_id": BEREDER,
            "navn": "Bereder",
            "effekt_w": 1800.0,
            "teller_med": True,
            "terskel_w": 1000.0,
            "bryter": BEREDER_BRYTER,
            "bryter_paa": True,
            "kuttet": False,
            "kuttet_siden": None,
        },
        {
            "entity_id": KABLER,
            "navn": "Varmekabler bad",
            "effekt_w": 550.0,
            "teller_med": True,
            "terskel_w": 100.0,
            "bryter": None,
            "bryter_paa": None,
            "kuttet": False,
            "kuttet_siden": None,
        },
    ]


@pytest.mark.asyncio
async def test_kildene_er_json_serialiserbare():
    """Attributter går gjennom recorder og websocket, så de må tåle JSON."""
    data = await _tick(_make_coordinator(_base_states()))
    assert json.loads(json.dumps(data["kutt_kilder"])) == data["kutt_kilder"]


@pytest.mark.asyncio
async def test_uten_konfigurerte_laster_er_det_ingen_kilder_og_intet_tall():
    """Ingen laster: tom liste, og tilgjengelig kutt er None framfor 0,3."""
    data = await _tick(_make_coordinator(_base_states(), laster=[]))
    assert data["kutt_kilder"] == []
    assert data["tilgjengelig_kutt_kw"] is None


@pytest.mark.asyncio
async def test_unavailable_sensor_gir_null_effekt_ikke_null_watt():
    states = _base_states()
    states[BEREDER] = make_state("unavailable", unit="W", friendly_name="Bereder effekt")
    data = await _tick(_make_coordinator(states))
    bereder = data["kutt_kilder"][0]
    assert bereder["effekt_w"] is None
    assert bereder["teller_med"] is False
    assert bereder["navn"] == "Bereder"


@pytest.mark.asyncio
async def test_bryter_som_ikke_svarer_er_ikke_av():
    states = _base_states(bryter="unavailable")
    data = await _tick(_make_coordinator(states))
    assert data["kutt_kilder"][0]["bryter_paa"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("bereder", "kabler"),
    [
        ("1800", "550"),
        ("40", "550"),
        ("1800", "12"),
        ("unavailable", "3600"),
        ("unknown", "unavailable"),
        ("0", "0"),
    ],
)
async def test_summen_av_tellende_laster_er_sensorens_tilstand(bereder, kabler):
    """Hele poenget med attributtet: tallet skal kunne regnes ut av lista."""
    data = await _tick(_make_coordinator(_base_states(bereder=bereder, kabler=kabler)))
    sum_kw = sum(k["effekt_w"] for k in data["kutt_kilder"] if k["teller_med"]) / 1000.0
    assert sum_kw == pytest.approx(data["tilgjengelig_kutt_kw"], abs=0.001)


@pytest.mark.asyncio
async def test_integrasjonen_ser_at_lasten_ble_kuttet():
    """Bryteren gaar av mens kutt er anbefalt: da er det vaart kutt, med tidspunkt."""
    coord = _make_coordinator(_base_states())
    coord.min_risiko_for_kutt = "god_margin"  # alt er over terskelen, saa kutt er anbefalt
    await _tick(coord)

    coord.hass.states.get = _base_states(bereder="0", bryter="off").get
    naa = datetime(2026, 5, 25, 14, 31, 0)
    data = await _tick(coord, now=naa)

    bereder = data["kutt_kilder"][0]
    assert bereder["kuttet"] is True
    assert bereder["kuttet_siden"] == naa.isoformat()
    assert data["kuttet_naa_kw"] == pytest.approx(1.8)


@pytest.mark.asyncio
async def test_kutt_uten_anbefaling_regnes_ikke_som_vaart():
    coord = _make_coordinator(_base_states())
    coord.min_risiko_for_kutt = "over_terskel"
    await _tick(coord)

    coord.hass.states.get = _base_states(bereder="0", bryter="off").get
    data = await _tick(coord, now=datetime(2026, 5, 25, 14, 31, 0))

    assert data["kutt_kilder"][0]["kuttet"] is False
    assert data["kuttet_naa_kw"] == 0.0


@pytest.mark.asyncio
async def test_sensoren_eksponerer_kildene():
    coord = _make_coordinator(_base_states())
    coord.data = await _tick(coord)
    attrs = EffektvaktTilgjengeligKuttSensor(coord).extra_state_attributes
    assert [k["entity_id"] for k in attrs["kutt_kilder"]] == [BEREDER, KABLER]
    assert attrs["kuttet_naa_kw"] == 0.0
    assert attrs["current_kw"] == coord.data["current_kw"]


def test_sensoren_uten_coordinator_data():
    coord = MagicMock()
    coord.entry.entry_id = "test_entry"
    coord.data = None
    assert EffektvaktTilgjengeligKuttSensor(coord).extra_state_attributes is None
