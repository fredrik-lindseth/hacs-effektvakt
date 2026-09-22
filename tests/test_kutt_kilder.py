"""Tester for kutt_kilder: hva som faktisk utgjør tilgjengelig kutt."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.effektvakt.const import (
    EKSTRA_SENSOR_ACTIVE_THRESHOLD_W,
    STRATEGI_BLIND,
    STRATEGI_VVB_PLUSS_EKSTRA,
    STRATEGI_VVB_STATUS,
    VVB_ACTIVE_THRESHOLD_W,
)
from custom_components.effektvakt.coordinator import EffektvaktCoordinator
from custom_components.effektvakt.laster import (
    ROLLE_EKSTRA,
    ROLLE_VVB,
    KildeAvlesning,
    build_kutt_kilder,
)
from custom_components.effektvakt.sensor import EffektvaktTilgjengeligKuttSensor
from tests.conftest import make_entry, make_hass_with_states, make_state

VVB_ENTITY = "sensor.vvb_power"
EKSTRA_ENTITY = "sensor.varmekabler_bad"


def _avlesninger(vvb_w: float | None, *ekstra_w: float | None) -> list[KildeAvlesning]:
    kilder = [KildeAvlesning(VVB_ENTITY, "Varmtvannsbereder", vvb_w, ROLLE_VVB)]
    for i, w in enumerate(ekstra_w):
        kilder.append(KildeAvlesning(f"sensor.ekstra_{i}", f"Ekstra {i}", w, ROLLE_EKSTRA))
    return kilder


def test_kilde_over_terskel_teller_med():
    kilder = build_kutt_kilder(
        strategi=STRATEGI_VVB_PLUSS_EKSTRA,
        avlesninger=_avlesninger(1800.0, 550.0),
    )
    assert [k.teller_med for k in kilder] == [True, True]
    assert [k.effekt_w for k in kilder] == [1800.0, 550.0]
    assert [k.rolle for k in kilder] == [ROLLE_VVB, ROLLE_EKSTRA]
    assert [k.terskel_w for k in kilder] == [
        VVB_ACTIVE_THRESHOLD_W,
        EKSTRA_SENSOR_ACTIVE_THRESHOLD_W,
    ]


def test_kilde_under_terskel_er_med_men_teller_ikke():
    """VVB i pause er fortsatt en kilde, den bidrar bare ikke akkurat nå."""
    kilder = build_kutt_kilder(
        strategi=STRATEGI_VVB_PLUSS_EKSTRA,
        avlesninger=_avlesninger(40.0, 12.0),
    )
    assert [k.teller_med for k in kilder] == [False, False]
    assert [k.effekt_w for k in kilder] == [40.0, 12.0]


def test_terskel_er_streng():
    """Nøyaktig på terskelen holder ikke, det må være over."""
    kilder = build_kutt_kilder(
        strategi=STRATEGI_VVB_PLUSS_EKSTRA,
        avlesninger=_avlesninger(VVB_ACTIVE_THRESHOLD_W, EKSTRA_SENSOR_ACTIVE_THRESHOLD_W),
    )
    assert [k.teller_med for k in kilder] == [False, False]


def test_utilgjengelig_sensor_gir_null_ikke_null_watt():
    """Forskjellen mellom "bruker ingenting" og "vi vet ikke" betyr noe."""
    kilder = build_kutt_kilder(
        strategi=STRATEGI_VVB_PLUSS_EKSTRA,
        avlesninger=_avlesninger(None, None),
    )
    assert [k.effekt_w for k in kilder] == [None, None]
    assert [k.teller_med for k in kilder] == [False, False]


def test_vvb_status_teller_ikke_ekstra_men_lister_den():
    kilder = build_kutt_kilder(
        strategi=STRATEGI_VVB_STATUS,
        avlesninger=_avlesninger(1800.0, 3600.0),
    )
    assert [k.teller_med for k in kilder] == [True, False]
    assert kilder[1].effekt_w == 3600.0


def test_blind_teller_ingen_kilder():
    """blind leser ingen sensorer, men konfigurerte kilder skal fortsatt vises."""
    kilder = build_kutt_kilder(
        strategi=STRATEGI_BLIND,
        avlesninger=_avlesninger(1800.0, 3600.0),
    )
    assert [k.teller_med for k in kilder] == [False, False]
    assert len(kilder) == 2


def test_ukjent_strategi_teller_ingenting():
    kilder = build_kutt_kilder(
        strategi="tull",
        avlesninger=_avlesninger(1800.0, 3600.0),
    )
    assert [k.teller_med for k in kilder] == [False, False]


def test_navn_kan_mangle():
    kilder = build_kutt_kilder(
        strategi=STRATEGI_VVB_STATUS,
        avlesninger=[KildeAvlesning(VVB_ENTITY, None, 1800.0, ROLLE_VVB)],
    )
    assert kilder[0].navn is None
    assert kilder[0].entity_id == VVB_ENTITY


def _make_coordinator(states, *, strategi, vvb=VVB_ENTITY, ekstra=None):
    entry = make_entry(safety_buffer_kw=0.5)
    entry.data.update(
        {
            "kutt_strategi": strategi,
            "vvb_power_sensor": vvb,
            "ekstra_power_sensors": ekstra or [],
        }
    )
    hass = make_hass_with_states(states)
    with patch("custom_components.effektvakt.coordinator.Store"):
        coord = EffektvaktCoordinator(hass, entry)
    coord._store = MagicMock()
    coord._store.async_load = AsyncMock(return_value=None)
    coord._store.async_save = AsyncMock()
    return coord


async def _tick(coord):
    with patch(
        "custom_components.effektvakt.coordinator.dt_util_now",
        return_value=datetime(2026, 5, 25, 14, 30, 0),
    ):
        return await coord._async_update_data()


def _base_states(vvb="1800", ekstra="550"):
    return {
        "sensor.power": make_state("500", unit="W"),
        "sensor.energy": make_state("100.0", unit="kWh"),
        VVB_ENTITY: make_state(vvb, unit="W", friendly_name="Varmtvannsbereder"),
        EKSTRA_ENTITY: make_state(ekstra, unit="W", friendly_name="Varmekabler bad"),
    }


@pytest.mark.asyncio
async def test_coordinator_eksponerer_kilder_med_navn():
    coord = _make_coordinator(
        _base_states(),
        strategi=STRATEGI_VVB_PLUSS_EKSTRA,
        ekstra=[EKSTRA_ENTITY],
    )
    data = await _tick(coord)
    assert data["kutt_kilder"] == [
        {
            "entity_id": VVB_ENTITY,
            "navn": "Varmtvannsbereder",
            "effekt_w": 1800.0,
            "teller_med": True,
            "rolle": ROLLE_VVB,
            "terskel_w": VVB_ACTIVE_THRESHOLD_W,
        },
        {
            "entity_id": EKSTRA_ENTITY,
            "navn": "Varmekabler bad",
            "effekt_w": 550.0,
            "teller_med": True,
            "rolle": ROLLE_EKSTRA,
            "terskel_w": EKSTRA_SENSOR_ACTIVE_THRESHOLD_W,
        },
    ]


@pytest.mark.asyncio
async def test_coordinator_kilder_er_json_serialiserbare():
    """Attributter går gjennom recorder og websocket, så de må tåle JSON."""
    coord = _make_coordinator(
        _base_states(),
        strategi=STRATEGI_VVB_PLUSS_EKSTRA,
        ekstra=[EKSTRA_ENTITY],
    )
    data = await _tick(coord)
    assert json.loads(json.dumps(data["kutt_kilder"])) == data["kutt_kilder"]


@pytest.mark.asyncio
async def test_coordinator_uten_konfigurerte_kilder_gir_tom_liste():
    coord = _make_coordinator(_base_states(), strategi=STRATEGI_BLIND, vvb=None)
    data = await _tick(coord)
    assert data["kutt_kilder"] == []


@pytest.mark.asyncio
async def test_unavailable_sensor_gir_null_effekt_i_coordinator():
    states = _base_states()
    states[VVB_ENTITY] = make_state("unavailable", unit="W", friendly_name="Varmtvannsbereder")
    coord = _make_coordinator(
        states,
        strategi=STRATEGI_VVB_PLUSS_EKSTRA,
        ekstra=[EKSTRA_ENTITY],
    )
    data = await _tick(coord)
    vvb = data["kutt_kilder"][0]
    assert vvb["effekt_w"] is None
    assert vvb["teller_med"] is False
    assert vvb["navn"] == "Varmtvannsbereder"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("strategi", "vvb", "ekstra"),
    [
        (STRATEGI_VVB_STATUS, "1800", "550"),
        (STRATEGI_VVB_STATUS, "40", "550"),
        (STRATEGI_VVB_PLUSS_EKSTRA, "1800", "550"),
        (STRATEGI_VVB_PLUSS_EKSTRA, "1800", "12"),
        (STRATEGI_VVB_PLUSS_EKSTRA, "40", "3600"),
        (STRATEGI_VVB_PLUSS_EKSTRA, "unavailable", "3600"),
        (STRATEGI_VVB_PLUSS_EKSTRA, "unknown", "unavailable"),
    ],
)
async def test_summen_av_tellende_kilder_er_sensorens_tilstand(strategi, vvb, ekstra):
    """Hele poenget med attributtet: tallet skal kunne regnes ut av lista."""
    coord = _make_coordinator(
        _base_states(vvb=vvb, ekstra=ekstra),
        strategi=strategi,
        ekstra=[EKSTRA_ENTITY],
    )
    data = await _tick(coord)
    sum_kw = sum(k["effekt_w"] for k in data["kutt_kilder"] if k["teller_med"]) / 1000.0
    assert sum_kw == pytest.approx(data["tilgjengelig_kutt_kw"], abs=0.001)


@pytest.mark.asyncio
async def test_blind_tilstand_er_en_antagelse_ikke_en_sum():
    """blind rapporterer duty cycle-estimatet, ikke noe kildene kan forklare."""
    coord = _make_coordinator(
        _base_states(),
        strategi=STRATEGI_BLIND,
        ekstra=[EKSTRA_ENTITY],
    )
    data = await _tick(coord)
    assert data["tilgjengelig_kutt_kw"] == 0.3
    assert not any(k["teller_med"] for k in data["kutt_kilder"])


@pytest.mark.asyncio
async def test_sensoren_eksponerer_kilder():
    coord = _make_coordinator(
        _base_states(),
        strategi=STRATEGI_VVB_PLUSS_EKSTRA,
        ekstra=[EKSTRA_ENTITY],
    )
    data = await _tick(coord)
    coord.data = data
    attrs = EffektvaktTilgjengeligKuttSensor(coord).extra_state_attributes
    assert attrs["kutt_strategi"] == STRATEGI_VVB_PLUSS_EKSTRA
    assert attrs["ekstra_power_w_total"] == pytest.approx(550.0)
    assert [k["entity_id"] for k in attrs["kutt_kilder"]] == [VVB_ENTITY, EKSTRA_ENTITY]
    assert attrs["current_kw"] == data["current_kw"]


def test_sensoren_uten_coordinator_data():
    coord = MagicMock()
    coord.entry.entry_id = "test_entry"
    coord.data = None
    assert EffektvaktTilgjengeligKuttSensor(coord).extra_state_attributes is None
