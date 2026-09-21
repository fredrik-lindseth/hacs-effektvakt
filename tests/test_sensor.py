"""Tester for sensor.py."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from custom_components.effektvakt.sensor import (
    EffektvaktKostnadNesteTrinnSensor,
    EffektvaktMarginSensor,
    EffektvaktProjisertSensor,
    EffektvaktRisikoSensor,
    EffektvaktTilgjengeligKuttSensor,
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
        "kostnad_neste_trinn_kr": 185,
        "trinn_na_kr": 415,
        "trinn_na_ovre_grense_kw": 10.0,
        "trinn_neste_kr": 600,
        "besparelse_trinn_under_kr": 165,
        "trinn_under_oppnaelig": True,
        "kostnad_denne_timen_kr": 0,
        "topp_3_projisert_kw": 8.4,
        "minste_mulige_topp_3_kw": 4.2,
        "hoyeste_trinn": False,
    }
    coord.kapasitetstrinn = [
        (2.0, 155),
        (5.0, 250),
        (10.0, 415),
        (15.0, 600),
        (float("inf"), 6900),
    ]
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


def test_tilgjengelig_kutt_sensor(coord_mock):
    coord_mock.data["tilgjengelig_kutt_kw"] = 2.5
    s = EffektvaktTilgjengeligKuttSensor(coord_mock)
    assert s.native_value == 2.5
    assert s.native_unit_of_measurement == "kW"


def test_kostnad_sensor_native_value(coord_mock):
    s = EffektvaktKostnadNesteTrinnSensor(coord_mock)
    assert s.native_value == 185
    assert s.native_unit_of_measurement == "kr/mnd"


def test_kostnad_sensor_har_ingen_device_class(coord_mock):
    """MONETARY krever ISO-valuta og total-state_class, så satsen står uten device_class."""
    s = EffektvaktKostnadNesteTrinnSensor(coord_mock)
    assert s.device_class is None


def test_kostnad_sensor_attributter(coord_mock):
    attrs = EffektvaktKostnadNesteTrinnSensor(coord_mock).extra_state_attributes
    assert attrs["trinn_na_kr"] == 415
    assert attrs["trinn_na_ovre_grense_kw"] == 10.0
    assert attrs["trinn_neste_kr"] == 600
    assert attrs["besparelse_trinn_under_kr"] == 165
    assert attrs["trinn_under_oppnaelig"] is True
    assert attrs["kostnad_denne_timen_kr"] == 0
    assert attrs["topp_3_projisert_kw"] == 8.4
    assert attrs["minste_mulige_topp_3_kw"] == 4.2


def test_kostnad_sensor_beholder_fellesattributtene(coord_mock):
    attrs = EffektvaktKostnadNesteTrinnSensor(coord_mock).extra_state_attributes
    assert attrs["current_kw"] == 5.5
    assert attrs["last_update"] == "2026-05-25T14:30:00"


def test_kapasitetstrinn_serialiserer_inf_som_null(coord_mock):
    """inf er ugyldig JSON og knekker recorder og websocket."""
    attrs = EffektvaktKostnadNesteTrinnSensor(coord_mock).extra_state_attributes
    assert attrs["kapasitetstrinn"] == [
        [2.0, 155],
        [5.0, 250],
        [10.0, 415],
        [15.0, 600],
        [None, 6900],
    ]
    json.dumps(attrs["kapasitetstrinn"])


def test_kapasitetstrinn_hele_attributtsettet_er_json_serialiserbart(coord_mock):
    attrs = EffektvaktKostnadNesteTrinnSensor(coord_mock).extra_state_attributes
    assert json.loads(json.dumps(attrs))["kapasitetstrinn"][-1] == [None, 6900]


def test_kostnad_sensor_uten_kjente_trinn(coord_mock):
    """Ukjent nettselskap gir None på alle ti nøklene, og tom trinn-liste."""
    for nokkel in (
        "kostnad_neste_trinn_kr",
        "trinn_na_kr",
        "trinn_na_ovre_grense_kw",
        "trinn_neste_kr",
        "besparelse_trinn_under_kr",
        "trinn_under_oppnaelig",
        "kostnad_denne_timen_kr",
        "topp_3_projisert_kw",
        "minste_mulige_topp_3_kw",
        "hoyeste_trinn",
    ):
        coord_mock.data[nokkel] = None
    coord_mock.kapasitetstrinn = []

    s = EffektvaktKostnadNesteTrinnSensor(coord_mock)
    assert s.native_value is None
    attrs = s.extra_state_attributes
    assert attrs["kapasitetstrinn"] == []
    assert attrs["trinn_neste_kr"] is None


def test_kostnad_sensor_uten_coordinator_data(coord_mock):
    coord_mock.data = None
    s = EffektvaktKostnadNesteTrinnSensor(coord_mock)
    assert s.native_value is None
    assert s.extra_state_attributes is None
