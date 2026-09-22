"""Tester for trinn-oppslaget: hvilket kapasitetstrinn en kW-verdi havner i.

Fram til september 2026 gjorde `lookup_tiers` dette oppslaget på den projiserte
timen og ga «neste trinn» derfra. Da flyttet referansen seg hver gang en enkelt
time spratt opp eller falt, og marginen målte mot noe annet enn brukeren trodde
(hacs-effektvakt-5ksx8m6). Nå gjøres oppslaget på topp-3-snittet, og
`beregn_terskel` og `compute_kostnad` deler den samme funksjonen.
"""

from __future__ import annotations

from datetime import date

import pytest

from custom_components.effektvakt.modell import beregn_terskel, compute_kostnad, trinn_indeks

BKK_TIER_EXAMPLE = [
    (2.0, 130),
    (5.0, 230),
    (10.0, 415),
    (15.0, 600),
    (20.0, 800),
    (25.0, 1000),
]

D1 = date(2026, 6, 1)
D2 = date(2026, 6, 2)
D3 = date(2026, 6, 3)


def test_trinn_indeks_under_forste_trinn():
    assert trinn_indeks(1.5, BKK_TIER_EXAMPLE) == 0


def test_trinn_indeks_paa_grense():
    """Terskelen hører til trinnet under seg: 5,0 kW er fortsatt 5 kW-trinnet."""
    assert trinn_indeks(5.0, BKK_TIER_EXAMPLE) == 1
    assert trinn_indeks(5.001, BKK_TIER_EXAMPLE) == 2


def test_trinn_indeks_over_hoyeste_terskel():
    """Uten et åpent topptrinn havner alt over siste terskel på øverste trinn."""
    assert trinn_indeks(30.0, BKK_TIER_EXAMPLE) == len(BKK_TIER_EXAMPLE) - 1


def test_referansen_folger_ikke_den_projiserte_timen():
    """Samme måned, tre ulike projeksjoner: måltrinnet står stille.

    Dette er kjernen i 5ksx8m6. Det målte tilfellet hos Fredrik var margin 3,50
    med projisert 0,38, fordi et lavt projisert tall valgte et lavt «neste
    trinn» og terskelen så ble løftet til topp-2-snittet.
    """
    maaned = {D1: 6.0, D2: 5.8}
    maal = {
        beregn_terskel(trinn=BKK_TIER_EXAMPLE, daily_max_kw=maaned, today=D3, projected_kw=p).maal_terskel_kw
        for p in (0.38, 3.0, 9.0)
    }
    assert maal == {5.0}


def test_varselet_forsvinner_ikke_naar_terskelen_passeres():
    """Trinnet skal ikke følge etter en time som spretter over det.

    Gjorde referansen det, ville marginen hoppet fra negativ til god i samme
    øyeblikk som brukeren burde kuttet.
    """
    maaned = {D1: 6.0, D2: 5.8}
    margin = [
        beregn_terskel(trinn=BKK_TIER_EXAMPLE, daily_max_kw=maaned, today=D3, projected_kw=p).margin_kw
        for p in (3.0, 3.2, 3.5, 5.0)
    ]
    assert all(m is not None for m in margin)
    assert margin == sorted(margin, reverse=True)
    assert margin[-1] == pytest.approx(-1.8)


def test_trinnet_maaneden_ligger_an_til_folger_projeksjonen():
    """Kostnadsbildet skal derimot vise trinnet timen er i ferd med å låse inn."""
    rolig = compute_kostnad(trinn=BKK_TIER_EXAMPLE, daily_max_kw={D1: 6.0, D2: 5.8}, today=D3, projected_kw=1.0)
    dyr = compute_kostnad(trinn=BKK_TIER_EXAMPLE, daily_max_kw={D1: 6.0, D2: 5.8}, today=D3, projected_kw=9.0)
    assert rolig is not None
    assert dyr is not None
    assert rolig.trinn_na_ovre_grense_kw == 5.0
    assert dyr.trinn_na_ovre_grense_kw == 10.0
