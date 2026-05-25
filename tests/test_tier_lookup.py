"""Tester for next/prev-tier-oppslag fra kapasitetstrinn-liste."""

from __future__ import annotations

from custom_components.effektvakt.coordinator import lookup_tiers

BKK_TIER_EXAMPLE = [
    (2.0, 130),
    (5.0, 230),
    (10.0, 415),
    (15.0, 600),
    (20.0, 800),
    (25.0, 1000),
]


def test_lookup_tiers_under_forste_trinn():
    info = lookup_tiers(projected_kw=1.5, trinn=BKK_TIER_EXAMPLE)
    assert info.prev_threshold_kw is None
    assert info.next_threshold_kw == 2.0
    assert info.next_pris_per_mnd == 130


def test_lookup_tiers_i_forste_trinn():
    info = lookup_tiers(projected_kw=3.0, trinn=BKK_TIER_EXAMPLE)
    assert info.prev_threshold_kw == 2.0
    assert info.next_threshold_kw == 5.0
    assert info.next_pris_per_mnd == 230


def test_lookup_tiers_pa_grense():
    info = lookup_tiers(projected_kw=5.0, trinn=BKK_TIER_EXAMPLE)
    assert info.prev_threshold_kw == 2.0
    assert info.next_threshold_kw == 5.0


def test_lookup_tiers_over_grense():
    info = lookup_tiers(projected_kw=7.5, trinn=BKK_TIER_EXAMPLE)
    assert info.prev_threshold_kw == 5.0
    assert info.next_threshold_kw == 10.0


def test_lookup_tiers_over_hoyeste_trinn():
    info = lookup_tiers(projected_kw=30.0, trinn=BKK_TIER_EXAMPLE)
    assert info.prev_threshold_kw == 25.0
    assert info.next_threshold_kw is None
    assert info.next_pris_per_mnd is None
