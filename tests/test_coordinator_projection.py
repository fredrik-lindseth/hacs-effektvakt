"""Tester for projisert time-snitt-beregning."""

from __future__ import annotations

import pytest

from custom_components.effektvakt.modell import compute_projected_avg


def test_projected_avg_uten_energy_sensor_starten_av_timen():
    """Ved minutt 0, projected = current_kw."""
    result = compute_projected_avg(
        actual_kwh_this_hour=0.0,
        current_kw=5.0,
        elapsed_h=0.0,
    )
    assert result == pytest.approx(5.0)


def test_projected_avg_midt_i_timen():
    """Ved minutt 30, halve timen er current_kw, halve er actual."""
    result = compute_projected_avg(
        actual_kwh_this_hour=2.0,
        current_kw=6.0,
        elapsed_h=0.5,
    )
    # 2 + 6 * 0.5 = 5.0
    assert result == pytest.approx(5.0)


def test_projected_avg_pa_slutten_av_timen():
    """Ved minutt 60, projected = actual_kwh."""
    result = compute_projected_avg(
        actual_kwh_this_hour=4.5,
        current_kw=10.0,
        elapsed_h=1.0,
    )
    assert result == pytest.approx(4.5)


def test_projected_avg_minutter_55_av_60_blindspot():
    """Ved minutt 55, ny stor last gir minimal effekt på prediksjon."""
    result = compute_projected_avg(
        actual_kwh_this_hour=3.0,
        current_kw=20.0,
        elapsed_h=55 / 60,
    )
    assert result == pytest.approx(3.0 + 20.0 * 5 / 60, rel=1e-3)
