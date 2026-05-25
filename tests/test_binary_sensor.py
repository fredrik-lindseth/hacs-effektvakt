"""Tester for binary_sensor.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.effektvakt.binary_sensor import EffektvaktKuttNedAnbefaltBinarySensor
from custom_components.effektvakt.const import RISIKO_HIGH, RISIKO_LOW, RISIKO_MEDIUM, RISIKO_NONE


@pytest.mark.parametrize("risiko,min_for_kutt,expected", [
    (RISIKO_NONE, "medium", False),
    (RISIKO_LOW, "medium", False),
    (RISIKO_MEDIUM, "medium", True),
    (RISIKO_HIGH, "medium", True),
    (RISIKO_LOW, "low", True),
    (RISIKO_HIGH, "high", True),
    (RISIKO_MEDIUM, "high", False),
])
def test_binary_sensor_is_on(risiko: str, min_for_kutt: str, expected: bool):
    coord = MagicMock()
    coord.entry.entry_id = "test"
    coord.min_risiko_for_kutt = min_for_kutt
    coord.data = {"risiko_niva": risiko}
    bs = EffektvaktKuttNedAnbefaltBinarySensor(coord)
    assert bs.is_on is expected


def test_binary_sensor_unknown_when_no_data():
    coord = MagicMock()
    coord.entry.entry_id = "test"
    coord.min_risiko_for_kutt = "medium"
    coord.data = None
    bs = EffektvaktKuttNedAnbefaltBinarySensor(coord)
    assert bs.is_on is None
