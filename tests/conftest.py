"""Pytest configuration, shared helpers og fixtures for Effektvakt-tester.

Mocker hele Home Assistant-stacken slik at vi slipper å installere HA
i CI. Følger samme mønster som strømkalkulator.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components"))

# Mock Home Assistant-moduler før vi importerer vår kode
sys.modules["homeassistant"] = MagicMock()
sys.modules["homeassistant.const"] = MagicMock()
sys.modules["homeassistant.core"] = MagicMock()
sys.modules["homeassistant.config_entries"] = MagicMock()
sys.modules["homeassistant.data_entry_flow"] = MagicMock()
sys.modules["homeassistant.helpers"] = MagicMock()
sys.modules["homeassistant.helpers.device_registry"] = MagicMock()
sys.modules["homeassistant.helpers.event"] = MagicMock()
sys.modules["homeassistant.helpers.issue_registry"] = MagicMock()
sys.modules["homeassistant.helpers.storage"] = MagicMock()


# DataUpdateCoordinator must be a real class so subclasses work with normal
# __setattr__ semantics. A MagicMock base intercepts attribute assignments.
class _DataUpdateCoordinatorStub:
    update_interval = None

    def __init__(self, hass, logger, *, name, update_interval=None):
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval


class _CoordinatorEntityStub:
    """Minimal stub for CoordinatorEntity so subclasses can use normal __setattr__."""

    def __init__(self, coordinator) -> None:
        self.coordinator = coordinator


class _SensorEntityStub:
    """Minimal stub for SensorEntity. Mirrors HA's _attr_* property pattern."""

    @property
    def native_unit_of_measurement(self) -> str | None:
        return getattr(self, "_attr_native_unit_of_measurement", None)

    @property
    def state_class(self):
        return getattr(self, "_attr_state_class", None)

    @property
    def device_class(self):
        return getattr(self, "_attr_device_class", None)


class _BinarySensorEntityStub:
    """Minimal stub for BinarySensorEntity."""


_update_coordinator_mod = MagicMock()
_update_coordinator_mod.DataUpdateCoordinator = _DataUpdateCoordinatorStub
_update_coordinator_mod.CoordinatorEntity = _CoordinatorEntityStub
sys.modules["homeassistant.helpers.update_coordinator"] = _update_coordinator_mod

sys.modules["homeassistant.helpers.entity"] = MagicMock()
sys.modules["homeassistant.helpers.selector"] = MagicMock()

_sensor_mod = MagicMock()
_sensor_mod.SensorEntity = _SensorEntityStub
_sensor_mod.SensorDeviceClass = MagicMock()
_sensor_mod.SensorStateClass = MagicMock()
sys.modules["homeassistant.components.sensor"] = _sensor_mod

_binary_sensor_mod = MagicMock()
_binary_sensor_mod.BinarySensorEntity = _BinarySensorEntityStub
_binary_sensor_mod.BinarySensorDeviceClass = MagicMock()
sys.modules["homeassistant.components.binary_sensor"] = _binary_sensor_mod

_dt_util_mock = MagicMock()
_dt_util_mock.now.return_value = datetime(2026, 6, 15, 12, 0, 0)
_ha_util_mock = MagicMock()
_ha_util_mock.dt = _dt_util_mock
sys.modules["homeassistant.util"] = _ha_util_mock
sys.modules["homeassistant.util.dt"] = _dt_util_mock


def make_state(value, *, unit: str | None = None, state_class: str | None = None):
    """Mock HA state-objekt."""
    state = MagicMock()
    state.state = str(value)
    state.attributes = {}
    if unit is not None:
        state.attributes["unit_of_measurement"] = unit
    if state_class is not None:
        state.attributes["state_class"] = state_class
    return state


def make_entry(
    entry_id: str = "test_entry",
    dso: str = "bkk",
    power_sensor: str = "sensor.power",
    energy_sensor: str | None = "sensor.energy",
    safety_buffer_kw: float = 1.0,
    min_risiko_for_kutt: str = "medium",
    risiko_holdetid_minutter: int = 5,
    kapasitetstrinn_custom: list | None = None,
):
    """Mock config entry med Effektvakt-defaults."""
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.data = {
        "dso": dso,
        "power_sensor": power_sensor,
        "energy_sensor": energy_sensor,
        "safety_buffer_kw": safety_buffer_kw,
        "min_risiko_for_kutt": min_risiko_for_kutt,
        "risiko_holdetid_minutter": risiko_holdetid_minutter,
    }
    if kapasitetstrinn_custom is not None:
        entry.data["kapasitetstrinn_custom"] = kapasitetstrinn_custom
    return entry


def make_hass_with_states(states: dict[str, object]):
    """Mock hass-objekt med states.get som leter i en gitt dict."""
    hass = MagicMock()
    hass.states.get = lambda entity_id: states.get(entity_id)
    return hass


@pytest.fixture
def hass():
    """Default hass-mock."""
    return make_hass_with_states({})


@pytest.fixture
def entry():
    """Default config entry."""
    return make_entry()
