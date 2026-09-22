"""Tester for full coordinator-pipeline (sensor -> projected -> risiko)."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.effektvakt.const import RISIKO_GOD_MARGIN, RISIKO_LIKE_UNDER, RISIKO_OVER_TERSKEL
from custom_components.effektvakt.coordinator import EffektvaktCoordinator
from tests.conftest import make_entry, make_hass_with_states, make_state


@pytest.fixture
def base_states():
    return {
        "sensor.power": make_state("500", unit="W"),
        "sensor.energy": make_state("100.0", unit="kWh"),
    }


def _make_coordinator(states, entry_overrides=None):
    overrides = entry_overrides or {}
    entry = make_entry(**overrides)
    hass = make_hass_with_states(states)
    with patch("custom_components.effektvakt.coordinator.Store"):
        coord = EffektvaktCoordinator(hass, entry)
    coord._store = MagicMock()
    coord._store.async_load = AsyncMock(return_value=None)
    coord._store.async_save = AsyncMock()
    return coord


def test_coordinator_init_leser_konfig(base_states):
    coord = _make_coordinator(base_states)
    assert coord.power_sensor == "sensor.power"
    assert coord.energy_sensor == "sensor.energy"
    assert coord.safety_buffer_kw == 1.0
    assert coord._regnskap.daily_max_kw == {}


def test_gammel_risikoverdi_i_config_entryen_oversettes(base_states):
    """En entry fra før omdøpingen har "medium" lagret. Faller den utenfor
    RISIKO_RANK, slår binary-sensoren aldri på igjen."""
    coord = _make_coordinator(base_states, entry_overrides={"min_risiko_for_kutt": "medium"})
    assert coord.min_risiko_for_kutt == RISIKO_LIKE_UNDER


@pytest.mark.asyncio
async def test_gammel_risikoverdi_i_lagret_hysterese_oversettes(base_states):
    coord = _make_coordinator(base_states)
    coord._store.async_load = AsyncMock(return_value={"data": {"hysterese_state": {"nivå": "high"}}})
    await coord._load_stored_data()
    assert coord._hysterese_state.nivå == RISIKO_OVER_TERSKEL


@pytest.mark.asyncio
async def test_coordinator_low_power_gir_god_margin(base_states):
    """500 W, BKK-trinn, lav buffer: projisert langt under første trinn."""
    coord = _make_coordinator(base_states, entry_overrides={"safety_buffer_kw": 0.5})
    with patch(
        "custom_components.effektvakt.coordinator.dt_util_now",
        return_value=datetime(2026, 5, 25, 14, 30, 0),
    ):
        data = await coord._async_update_data()
    assert data["risiko_niva"] == RISIKO_GOD_MARGIN
    assert data["projected_avg_kw"] < 5


@pytest.mark.asyncio
async def test_maalerdelta_over_timeskiftet_havner_paa_timen_foer():
    """Etter time-rollover skal første tick ikke gi falsk delta-spike.

    kWh-en måleren melder ved timeskiftet ble brukt i timen som nettopp ble
    ferdig, ikke i den som så vidt har begynt.
    """
    states = {
        "sensor.power": make_state("500", unit="W"),
        "sensor.energy": make_state("100.0", unit="kWh"),
    }
    coord = _make_coordinator(states, entry_overrides={"safety_buffer_kw": 0.5})

    # 14:30 - første tick, setter baseline
    with patch(
        "custom_components.effektvakt.coordinator.dt_util_now",
        return_value=datetime(2026, 5, 25, 14, 30, 0),
    ):
        await coord._async_update_data()
    assert coord._regnskap.current_hour_kwh == 0.0
    assert coord._regnskap.siste_maaler_kwh == 100.0

    # 14:45 - energi økt med 2.5 kWh
    states["sensor.energy"] = make_state("102.5", unit="kWh")
    coord.hass = make_hass_with_states(states)
    with patch(
        "custom_components.effektvakt.coordinator.dt_util_now",
        return_value=datetime(2026, 5, 25, 14, 45, 0),
    ):
        await coord._async_update_data()
    assert coord._regnskap.current_hour_kwh == pytest.approx(2.5)

    # 15:00 - ny time, energi nå 103.0 kWh. Hele vinduet 14:45 til 15:00 lå i
    # timen 14, så de 0,5 kWh skal dit og ingenting til den nye timen.
    states["sensor.energy"] = make_state("103.0", unit="kWh")
    coord.hass = make_hass_with_states(states)
    with patch(
        "custom_components.effektvakt.coordinator.dt_util_now",
        return_value=datetime(2026, 5, 25, 15, 0, 0),
    ):
        await coord._async_update_data()
    assert coord._regnskap.current_hour_kwh == 0.0
    assert coord._regnskap.siste_maaler_kwh == 103.0
    assert coord._regnskap.daily_max_kw[date(2026, 5, 25)] == pytest.approx(3.0)


@pytest.mark.asyncio
async def test_to_tunge_dager_bak_seg_gir_kutt_og_ikke_god_margin():
    """Hele poenget i hacs-effektvakt-2p7wpch, gjennom hele pipeline.

    6,0 og 5,8 kW logget, 10 kW nå midt i timen, altså 5,0 kW projisert. Topp-3
    lander da på (6,0 + 5,8 + 5,0) / 3 = 5,6 og måneden går fra 250 til 415 kr.
    Terskelen dagen tåler er 3,2, så marginen er -1,8 og vakten skal si kutt.

    Modellen som sto her til september 2026 ga max(5,0, 5,9) = 5,9 og dermed
    margin +0,90: «like under terskelen», ikke over den.
    """
    states = {
        "sensor.power": make_state("10000", unit="W"),
        "sensor.energy": make_state("100.0", unit="kWh"),
    }
    coord = _make_coordinator(states)
    coord._regnskap.daily_max_kw = {date(2026, 6, 1): 6.0, date(2026, 6, 2): 5.8}

    with patch(
        "custom_components.effektvakt.coordinator.dt_util_now",
        return_value=datetime(2026, 6, 3, 14, 30, 0),
    ):
        data = await coord._async_update_data()

    assert data["projected_avg_kw"] == pytest.approx(5.0)
    assert data["maal_terskel_kw"] == 5.0
    assert data["maal_trinn_kr"] == 250
    assert data["dagstak_kw"] == pytest.approx(3.2)
    assert data["time_tak_kw"] == pytest.approx(3.2)
    assert data["margin_kw"] == pytest.approx(-1.8)
    assert data["kutt_anbefalt_kw"] == pytest.approx(1.8)
    assert data["kan_legge_paa_kw"] == 0.0
    assert data["risiko_niva"] == RISIKO_OVER_TERSKEL
    # Og kronene er ekte: topp-3 går fra 5 kW-trinnet til 10 kW-trinnet
    assert data["kostnad_denne_timen_kr"] == 165


@pytest.mark.asyncio
async def test_topp_3_sensoren_er_monoton_gjennom_maaneden():
    """En rolig dag nummer tre skal ikke dra topp-3-tallet ned igjen.

    Med deling på antall dager ga 6,0 og 4,0 et topp-3 på 5,0, som falt til
    3,67 i det en tredje dag på 1,0 kom til. Nå deles det alltid på tre.
    """
    states = {
        "sensor.power": make_state("500", unit="W"),
        "sensor.energy": make_state("100.0", unit="kWh"),
    }
    coord = _make_coordinator(states)

    verdier = []
    for dager in (
        {date(2026, 6, 1): 6.0},
        {date(2026, 6, 1): 6.0, date(2026, 6, 2): 4.0},
        {date(2026, 6, 1): 6.0, date(2026, 6, 2): 4.0, date(2026, 6, 3): 1.0},
    ):
        coord._regnskap.daily_max_kw = dict(dager)
        coord._store_loaded = True
        with patch(
            "custom_components.effektvakt.coordinator.dt_util_now",
            return_value=datetime(2026, 6, 4, 14, 30, 0),
        ):
            data = await coord._async_update_data()
        verdier.append(data["topp_3_snitt_denne_maned_kw"])

    assert verdier == [2.0, pytest.approx(3.333, abs=0.001), pytest.approx(3.667, abs=0.001)]
    assert verdier == sorted(verdier)
