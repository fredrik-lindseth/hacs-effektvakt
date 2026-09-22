"""Tester for rå risikoklassifisering (uten hysterese)."""

from __future__ import annotations

import pytest

from custom_components.effektvakt.const import (
    RISIKO_GOD_MARGIN,
    RISIKO_LIKE_UNDER,
    RISIKO_NAERMER_SEG,
    RISIKO_OVER_TERSKEL,
)
from custom_components.effektvakt.modell import classify_raw_risk


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
    """Marginen alene, når timen faktisk flytter trinnet."""
    assert classify_raw_risk(margin_kw=margin, safety_buffer_kw=buffer, timen_flytter_trinnet=True) == expected


@pytest.mark.parametrize(
    "margin,expected",
    [
        (5.0, RISIKO_GOD_MARGIN),
        (1.5, RISIKO_NAERMER_SEG),
        (0.5, RISIKO_NAERMER_SEG),
        (0.0, RISIKO_NAERMER_SEG),
        (-3.0, RISIKO_NAERMER_SEG),
    ],
)
def test_en_gratis_time_naar_aldri_hoyere_enn_naermer_seg(margin: float, expected: str):
    """Flytter ikke timen trinnet, koster den ingenting, og da kuttes det ikke.

    De to øverste nivåene er forbeholdt timer som faktisk koster penger. Uten
    taket melder en vannkoker ved minutt to `over_terskel` på en projeksjon som
    nesten bare er øyeblikkseffekten, og timen ender langt under.
    """
    assert classify_raw_risk(margin_kw=margin, safety_buffer_kw=1.0, timen_flytter_trinnet=False) == expected


def test_uten_terskel_aa_maale_mot_er_det_ingenting_aa_advare_om():
    """Ukjent nettselskap eller øverste trinn gir margin None, ikke uendelig.

    Uendelig er ugyldig JSON og knekker recorder og websocket, og «vet ikke»
    skal ikke leses som «over terskelen».
    """
    assert classify_raw_risk(margin_kw=None, safety_buffer_kw=1.0, timen_flytter_trinnet=False) == RISIKO_GOD_MARGIN


def test_verdiene_beskriver_naerheten_til_terskelen():
    """Verdiene skal kunne leses i en automasjon uten oppslagstabell."""
    assert classify_raw_risk(margin_kw=-0.5, safety_buffer_kw=1.0, timen_flytter_trinnet=True) == "over_terskel"
    assert classify_raw_risk(margin_kw=0.5, safety_buffer_kw=1.0, timen_flytter_trinnet=True) == "like_under_terskel"
