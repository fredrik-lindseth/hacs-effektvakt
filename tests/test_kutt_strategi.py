"""Tester for compute_tilgjengelig_kutt_kw."""

from __future__ import annotations

import pytest

from custom_components.effektvakt.const import (
    BLIND_ASSUMED_KUTT_KW,
    LEGACY_STRATEGI_MAPPING,
    STRATEGI_BLIND,
    STRATEGI_OPTIONS,
    STRATEGI_VVB_PLUSS_EKSTRA,
    STRATEGI_VVB_STATUS,
)
from custom_components.effektvakt.coordinator import compute_tilgjengelig_kutt_kw


def test_blind_returnerer_duty_cycle_estimat():
    result = compute_tilgjengelig_kutt_kw(
        strategi=STRATEGI_BLIND,
        vvb_power_w=None,
        ekstra_power_w=None,
    )
    assert result == BLIND_ASSUMED_KUTT_KW


def test_blind_ignorerer_vvb_sensor():
    result = compute_tilgjengelig_kutt_kw(
        strategi=STRATEGI_BLIND,
        vvb_power_w=2000.0,
        ekstra_power_w=None,
    )
    assert result == BLIND_ASSUMED_KUTT_KW


def test_vvb_status_med_aktiv_element():
    result = compute_tilgjengelig_kutt_kw(
        strategi=STRATEGI_VVB_STATUS,
        vvb_power_w=1800.0,
        ekstra_power_w=None,
    )
    assert result == pytest.approx(1.8)


def test_vvb_status_med_inaktiv_element():
    """VVB under terskel: tilgjengelig kutt = 0."""
    result = compute_tilgjengelig_kutt_kw(
        strategi=STRATEGI_VVB_STATUS,
        vvb_power_w=50.0,
        ekstra_power_w=None,
    )
    assert result == 0.0


def test_vvb_status_uten_sensor_returnerer_null():
    result = compute_tilgjengelig_kutt_kw(
        strategi=STRATEGI_VVB_STATUS,
        vvb_power_w=None,
        ekstra_power_w=None,
    )
    assert result == 0.0


def test_vvb_pluss_ekstra_summerer_begge():
    result = compute_tilgjengelig_kutt_kw(
        strategi=STRATEGI_VVB_PLUSS_EKSTRA,
        vvb_power_w=1800.0,
        ekstra_power_w=[3600.0],
    )
    assert result == pytest.approx(5.4)


def test_vvb_pluss_ekstra_uten_ekstra_aktiv():
    """Ekstra under 100 W: bidrar ikke."""
    result = compute_tilgjengelig_kutt_kw(
        strategi=STRATEGI_VVB_PLUSS_EKSTRA,
        vvb_power_w=2000.0,
        ekstra_power_w=[50.0],
    )
    assert result == pytest.approx(2.0)


def test_vvb_pluss_ekstra_kun_ekstra():
    """Hvis bare ekstra-sensor er aktiv: returner ekstra-effekt."""
    result = compute_tilgjengelig_kutt_kw(
        strategi=STRATEGI_VVB_PLUSS_EKSTRA,
        vvb_power_w=None,
        ekstra_power_w=[11000.0],
    )
    assert result == pytest.approx(11.0)


def test_vvb_pluss_ekstra_summerer_alle():
    result = compute_tilgjengelig_kutt_kw(
        strategi=STRATEGI_VVB_PLUSS_EKSTRA,
        vvb_power_w=2000.0,
        ekstra_power_w=[3600.0, 500.0, 50.0],  # billader, varmekabel, for liten
    )
    # 2.0 + 3.6 + 0.5 = 6.1 (50 W ignoreres)
    assert result == pytest.approx(6.1)


def test_vvb_pluss_ekstra_tom_liste():
    result = compute_tilgjengelig_kutt_kw(
        strategi=STRATEGI_VVB_PLUSS_EKSTRA,
        vvb_power_w=2000.0,
        ekstra_power_w=[],
    )
    assert result == pytest.approx(2.0)


def test_legacy_billader_strategi_mappes():
    """vvb_billader (gammel) skal kunne tolkes som vvb_pluss_ekstra."""
    assert LEGACY_STRATEGI_MAPPING["vvb_billader"] == STRATEGI_VVB_PLUSS_EKSTRA


def test_strategi_options_includes_alle_3():
    assert STRATEGI_BLIND in STRATEGI_OPTIONS
    assert STRATEGI_VVB_STATUS in STRATEGI_OPTIONS
    assert STRATEGI_VVB_PLUSS_EKSTRA in STRATEGI_OPTIONS
    assert len(STRATEGI_OPTIONS) == 3
