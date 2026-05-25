"""Tester for rå risikoklassifisering (uten hysterese)."""

from __future__ import annotations

import pytest

from custom_components.effektvakt.coordinator import classify_raw_risk
from custom_components.effektvakt.const import RISIKO_NONE, RISIKO_LOW, RISIKO_MEDIUM, RISIKO_HIGH


@pytest.mark.parametrize("margin,buffer,expected", [
    (5.0, 1.0, RISIKO_NONE),
    (2.5, 1.0, RISIKO_NONE),
    (2.0, 1.0, RISIKO_LOW),
    (1.5, 1.0, RISIKO_LOW),
    (1.0, 1.0, RISIKO_MEDIUM),
    (0.5, 1.0, RISIKO_MEDIUM),
    (0.001, 1.0, RISIKO_MEDIUM),
    (0.0, 1.0, RISIKO_HIGH),
    (-1.0, 1.0, RISIKO_HIGH),
    (3.0, 0.5, RISIKO_NONE),
    (0.4, 0.5, RISIKO_MEDIUM),
])
def test_classify_raw_risk(margin: float, buffer: float, expected: str):
    assert classify_raw_risk(margin_kw=margin, safety_buffer_kw=buffer) == expected
