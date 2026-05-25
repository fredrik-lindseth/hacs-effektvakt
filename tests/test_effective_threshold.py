"""Tester for effective_threshold-beregning."""

from __future__ import annotations

from datetime import date

import pytest

from custom_components.effektvakt.coordinator import (
    compute_effective_threshold,
    top_n_average,
)


def test_top_n_average_tom_dict():
    assert top_n_average({}, n=2) is None


def test_top_n_average_en_dag():
    assert top_n_average({date(2026, 5, 1): 5.0}, n=2) == pytest.approx(5.0)


def test_top_n_average_to_dager():
    dm = {date(2026, 5, 1): 5.0, date(2026, 5, 2): 7.0}
    assert top_n_average(dm, n=2) == pytest.approx(6.0)


def test_top_n_average_tre_dager_velger_de_to_hoyeste():
    dm = {
        date(2026, 5, 1): 5.0,
        date(2026, 5, 2): 7.0,
        date(2026, 5, 3): 3.0,
    }
    assert top_n_average(dm, n=2) == pytest.approx(6.0)


def test_top_n_average_topp_3():
    dm = {
        date(2026, 5, 1): 5.0,
        date(2026, 5, 2): 7.0,
        date(2026, 5, 3): 3.0,
        date(2026, 5, 4): 9.0,
    }
    assert top_n_average(dm, n=3) == pytest.approx((9 + 7 + 5) / 3)


def test_effective_threshold_med_for_fa_dager():
    dm = {date(2026, 5, 1): 5.0}
    assert compute_effective_threshold(
        next_tier_threshold_kw=10.0,
        daily_max_kw=dm,
    ) == 10.0


def test_effective_threshold_topp_2_under_terskel():
    dm = {date(2026, 5, 1): 6.0, date(2026, 5, 2): 7.0}
    assert compute_effective_threshold(
        next_tier_threshold_kw=10.0,
        daily_max_kw=dm,
    ) == 10.0


def test_effective_threshold_topp_2_over_terskel():
    dm = {date(2026, 5, 1): 11.0, date(2026, 5, 2): 13.0}
    assert compute_effective_threshold(
        next_tier_threshold_kw=10.0,
        daily_max_kw=dm,
    ) == pytest.approx(12.0)


def test_effective_threshold_eksempel_fra_spec():
    dm = {date(2026, 5, 1): 12.0, date(2026, 5, 2): 12.0, date(2026, 5, 3): 12.0}
    assert compute_effective_threshold(
        next_tier_threshold_kw=15.0,
        daily_max_kw=dm,
    ) == pytest.approx(15.0)
