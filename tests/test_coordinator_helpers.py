"""Tester for helper-funksjoner i coordinator."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.effektvakt.coordinator import read_power_kw, read_energy_kwh
from tests.conftest import make_state


def test_read_power_kw_fra_watt():
    hass = MagicMock()
    hass.states.get.return_value = make_state("2500", unit="W")
    assert read_power_kw(hass, "sensor.p") == 2.5


def test_read_power_kw_fra_kw():
    hass = MagicMock()
    hass.states.get.return_value = make_state("3.2", unit="kW")
    assert read_power_kw(hass, "sensor.p") == 3.2


def test_read_power_kw_ukjent_unit_returnerer_none():
    hass = MagicMock()
    hass.states.get.return_value = make_state("1", unit="VA")
    assert read_power_kw(hass, "sensor.p") is None


def test_read_power_kw_unavailable_returnerer_none():
    hass = MagicMock()
    hass.states.get.return_value = make_state("unavailable", unit="W")
    assert read_power_kw(hass, "sensor.p") is None


def test_read_power_kw_ingen_sensor_returnerer_none():
    hass = MagicMock()
    assert read_power_kw(hass, None) is None


def test_read_energy_kwh_fra_kwh():
    hass = MagicMock()
    hass.states.get.return_value = make_state("124523.105", unit="kWh")
    assert read_energy_kwh(hass, "sensor.e") == 124523.105


def test_read_energy_kwh_fra_wh():
    hass = MagicMock()
    hass.states.get.return_value = make_state("124523105", unit="Wh")
    assert read_energy_kwh(hass, "sensor.e") == 124523.105
