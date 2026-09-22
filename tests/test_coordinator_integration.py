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
    assert coord._daily_max_kw == {}


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
    assert coord._current_hour_kwh == 0.0
    assert coord._siste_maaler_kwh == 100.0

    # 14:45 - energi økt med 2.5 kWh
    states["sensor.energy"] = make_state("102.5", unit="kWh")
    coord.hass = make_hass_with_states(states)
    with patch(
        "custom_components.effektvakt.coordinator.dt_util_now",
        return_value=datetime(2026, 5, 25, 14, 45, 0),
    ):
        await coord._async_update_data()
    assert coord._current_hour_kwh == pytest.approx(2.5)

    # 15:00 - ny time, energi nå 103.0 kWh. Hele vinduet 14:45 til 15:00 lå i
    # timen 14, så de 0,5 kWh skal dit og ingenting til den nye timen.
    states["sensor.energy"] = make_state("103.0", unit="kWh")
    coord.hass = make_hass_with_states(states)
    with patch(
        "custom_components.effektvakt.coordinator.dt_util_now",
        return_value=datetime(2026, 5, 25, 15, 0, 0),
    ):
        await coord._async_update_data()
    assert coord._current_hour_kwh == 0.0
    assert coord._siste_maaler_kwh == 103.0
    assert coord._daily_max_kw[date(2026, 5, 25)] == pytest.approx(3.0)
