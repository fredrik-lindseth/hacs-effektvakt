"""Tester for sensor.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.effektvakt.sensor import (
    EffektvaktMarginSensor,
    EffektvaktProjisertSensor,
    EffektvaktRisikoSensor,
    EffektvaktTopp3Sensor,
)


@pytest.fixture
def coord_mock():
    coord = MagicMock()
    coord.entry.entry_id = "test_entry"
    coord.data = {
        "projected_avg_kw": 5.5,
        "margin_kw": 4.5,
        "topp_3_snitt_denne_maned_kw": 4.2,
        "risiko_niva": "low",
        "next_tier_threshold_kw": 10.0,
        "next_tier_pris_per_maned": 415,
        "prev_tier_threshold_kw": 5.0,
        "effective_threshold_kw": 10.0,
        "kutt_anbefalt_kw": 0.0,
        "topp_2_snitt_denne_maned_kw": 4.0,
        "elapsed_minutes_in_hour": 30,
        "actual_kwh_this_hour": 2.5,
        "current_kw": 5.5,
        "last_update": "2026-05-25T14:30:00",
    }
    return coord


def test_projisert_sensor_native_value(coord_mock):
    s = EffektvaktProjisertSensor(coord_mock)
    assert s.native_value == 5.5
    assert s.native_unit_of_measurement == "kW"


def test_margin_sensor_har_anbefalt_kw_attributt(coord_mock):
    s = EffektvaktMarginSensor(coord_mock)
    assert s.native_value == 4.5
    attrs = s.extra_state_attributes
    assert attrs["kutt_anbefalt_kw"] == 0.0
    assert attrs["next_tier_threshold_kw"] == 10.0
    assert attrs["prev_tier_threshold_kw"] == 5.0


def test_topp_3_sensor(coord_mock):
    s = EffektvaktTopp3Sensor(coord_mock)
    assert s.native_value == 4.2


def test_risiko_sensor_native_value(coord_mock):
    s = EffektvaktRisikoSensor(coord_mock)
    assert s.native_value == "low"


def test_risiko_sensor_options(coord_mock):
    s = EffektvaktRisikoSensor(coord_mock)
    assert "none" in s.options
    assert "high" in s.options
