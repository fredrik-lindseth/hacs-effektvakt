"""Tester for binary_sensor.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.effektvakt.binary_sensor import (
    BINARY_SENSOR_KEY,
    EffektvaktKuttNedAnbefaltBinarySensor,
)
from custom_components.effektvakt.const import (
    RISIKO_GOD_MARGIN,
    RISIKO_LIKE_UNDER,
    RISIKO_NAERMER_SEG,
    RISIKO_OVER_TERSKEL,
)


@pytest.mark.parametrize(
    "risiko,min_for_kutt,expected",
    [
        (RISIKO_GOD_MARGIN, RISIKO_LIKE_UNDER, False),
        (RISIKO_NAERMER_SEG, RISIKO_LIKE_UNDER, False),
        (RISIKO_LIKE_UNDER, RISIKO_LIKE_UNDER, True),
        (RISIKO_OVER_TERSKEL, RISIKO_LIKE_UNDER, True),
        (RISIKO_NAERMER_SEG, RISIKO_NAERMER_SEG, True),
        (RISIKO_OVER_TERSKEL, RISIKO_OVER_TERSKEL, True),
        (RISIKO_LIKE_UNDER, RISIKO_OVER_TERSKEL, False),
    ],
)
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
    coord.min_risiko_for_kutt = RISIKO_LIKE_UNDER
    coord.data = None
    bs = EffektvaktKuttNedAnbefaltBinarySensor(coord)
    assert bs.is_on is None


def test_binary_sensor_er_oversettbar_og_beholder_id_en():
    """Navnet kommer fra oversettelsen, id-en er den docs og blueprintene navngir."""
    coord = MagicMock()
    coord.entry.entry_id = "test"
    bs = EffektvaktKuttNedAnbefaltBinarySensor(coord)
    assert bs._attr_translation_key == BINARY_SENSOR_KEY
    assert not hasattr(bs, "_attr_name")
    assert bs.entity_id == "binary_sensor.effektvakt_kutt_ned_anbefalt"
    assert bs._attr_unique_id == "test_kutt_ned_anbefalt"
