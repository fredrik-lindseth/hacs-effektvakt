"""Tester for rå risikoklassifisering (uten hysterese)."""

from __future__ import annotations

import pytest

from custom_components.effektvakt.const import (
    RISIKO_GOD_MARGIN,
    RISIKO_LIKE_UNDER,
    RISIKO_NAERMER_SEG,
    RISIKO_OVER_TERSKEL,
)
from custom_components.effektvakt.coordinator import classify_raw_risk


@pytest.mark.parametrize(
    "margin,buffer,expected",
    [
        (5.0, 1.0, RISIKO_GOD_MARGIN),
        (2.5, 1.0, RISIKO_GOD_MARGIN),
        (2.0, 1.0, RISIKO_NAERMER_SEG),
        (1.5, 1.0, RISIKO_NAERMER_SEG),
        (1.0, 1.0, RISIKO_LIKE_UNDER),
        (0.5, 1.0, RISIKO_LIKE_UNDER),
        (0.001, 1.0, RISIKO_LIKE_UNDER),
        (0.0, 1.0, RISIKO_OVER_TERSKEL),
        (-1.0, 1.0, RISIKO_OVER_TERSKEL),
        (3.0, 0.5, RISIKO_GOD_MARGIN),
        (0.4, 0.5, RISIKO_LIKE_UNDER),
    ],
)
def test_classify_raw_risk(margin: float, buffer: float, expected: str):
    assert classify_raw_risk(margin_kw=margin, safety_buffer_kw=buffer) == expected


def test_verdiene_beskriver_naerheten_til_terskelen():
    """Verdiene skal kunne leses i en automasjon uten oppslagstabell."""
    assert classify_raw_risk(margin_kw=-0.5, safety_buffer_kw=1.0) == "over_terskel"
    assert classify_raw_risk(margin_kw=0.5, safety_buffer_kw=1.0) == "like_under_terskel"
