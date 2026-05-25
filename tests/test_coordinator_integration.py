"""Tester for full coordinator-pipeline (sensor -> projected -> risiko)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.effektvakt.const import RISIKO_NONE
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


@pytest.mark.asyncio
async def test_coordinator_low_power_gir_none_risk(base_states):
    """500 W, BKK-trinn, lav buffer: projisert langt under første trinn, risiko = none."""
    coord = _make_coordinator(base_states, entry_overrides={"safety_buffer_kw": 0.5})
    with patch(
        "custom_components.effektvakt.coordinator.dt_util_now",
        return_value=datetime(2026, 5, 25, 14, 30, 0),
    ):
        data = await coord._async_update_data()
    assert data["risiko_niva"] == RISIKO_NONE
    assert data["projected_avg_kw"] < 5
