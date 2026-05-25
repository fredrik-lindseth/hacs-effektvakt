"""Tester for config_flow-helpers."""

from __future__ import annotations

import pytest

from custom_components.effektvakt.config_flow import looks_like_peak_sensor


@pytest.mark.parametrize(
    "entity_id,friendly,expected",
    [
        ("sensor.tibber_max_power", "Tibber Max Power", True),
        ("sensor.house_peak_power", "House Peak", True),
        ("sensor.power_max_per_hour", "Power Max Per Hour", True),
        ("sensor.tibber_pulse_power", "Tibber Pulse Power", False),
        ("sensor.house_power", "House Power", False),
        ("sensor.average_power", "Average Power", True),
        ("sensor.power_average_per_hour", "Power Average", True),
    ],
)
def test_looks_like_peak_sensor(entity_id: str, friendly: str, expected: bool):
    assert looks_like_peak_sensor(entity_id, friendly_name=friendly) is expected
