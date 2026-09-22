"""Tester for hysterese-state-maskinen."""

from __future__ import annotations

from datetime import datetime, timedelta

from custom_components.effektvakt.const import (
    RISIKO_GOD_MARGIN,
    RISIKO_LIKE_UNDER,
    RISIKO_NAERMER_SEG,
    RISIKO_OVER_TERSKEL,
)
from custom_components.effektvakt.hysterese import HystereseState, apply_hysteresis

HOLDETID = timedelta(minutes=5)
NOW = datetime(2026, 5, 25, 14, 0, 0)


def test_oppgang_er_umiddelbar():
    state = HystereseState(nivå=RISIKO_GOD_MARGIN, pending_nivå=None, pending_since=None)
    apply_hysteresis(state, rå_nivå=RISIKO_LIKE_UNDER, now=NOW, holdetid=HOLDETID)
    assert state.nivå == RISIKO_LIKE_UNDER
    assert state.pending_nivå is None


def test_oppgang_overskriver_pending():
    state = HystereseState(
        nivå=RISIKO_OVER_TERSKEL,
        pending_nivå=RISIKO_LIKE_UNDER,
        pending_since=NOW - timedelta(minutes=2),
    )
    apply_hysteresis(state, rå_nivå=RISIKO_OVER_TERSKEL, now=NOW, holdetid=HOLDETID)
    assert state.nivå == RISIKO_OVER_TERSKEL
    assert state.pending_nivå is None
    assert state.pending_since is None


def test_nedgang_starter_timer():
    state = HystereseState(nivå=RISIKO_OVER_TERSKEL, pending_nivå=None, pending_since=None)
    apply_hysteresis(state, rå_nivå=RISIKO_NAERMER_SEG, now=NOW, holdetid=HOLDETID)
    assert state.nivå == RISIKO_OVER_TERSKEL
    assert state.pending_nivå == RISIKO_NAERMER_SEG
    assert state.pending_since == NOW


def test_nedgang_holder_innenfor_holdetid():
    state = HystereseState(
        nivå=RISIKO_OVER_TERSKEL,
        pending_nivå=RISIKO_NAERMER_SEG,
        pending_since=NOW - timedelta(minutes=2),
    )
    apply_hysteresis(state, rå_nivå=RISIKO_NAERMER_SEG, now=NOW, holdetid=HOLDETID)
    assert state.nivå == RISIKO_OVER_TERSKEL


def test_nedgang_trigger_etter_holdetid_multi_step():
    """Hopp fra HIGH til NONE: går trinn-for-trinn med holdetid mellom."""
    state = HystereseState(
        nivå=RISIKO_OVER_TERSKEL,
        pending_nivå=RISIKO_GOD_MARGIN,
        pending_since=NOW - timedelta(minutes=5),
    )
    apply_hysteresis(state, rå_nivå=RISIKO_GOD_MARGIN, now=NOW, holdetid=HOLDETID)
    assert state.nivå == RISIKO_LIKE_UNDER
    assert state.pending_since == NOW


def test_oscillasjon_kansellerer_pending():
    state = HystereseState(
        nivå=RISIKO_OVER_TERSKEL,
        pending_nivå=RISIKO_NAERMER_SEG,
        pending_since=NOW - timedelta(minutes=2),
    )
    apply_hysteresis(state, rå_nivå=RISIKO_OVER_TERSKEL, now=NOW, holdetid=HOLDETID)
    assert state.nivå == RISIKO_OVER_TERSKEL
    assert state.pending_nivå is None
    assert state.pending_since is None


def test_endret_pending_nullstiller_timer():
    state = HystereseState(
        nivå=RISIKO_OVER_TERSKEL,
        pending_nivå=RISIKO_NAERMER_SEG,
        pending_since=NOW - timedelta(minutes=2),
    )
    apply_hysteresis(state, rå_nivå=RISIKO_LIKE_UNDER, now=NOW, holdetid=HOLDETID)
    assert state.nivå == RISIKO_OVER_TERSKEL
    assert state.pending_nivå == RISIKO_LIKE_UNDER
    assert state.pending_since == NOW


def test_full_nedgang_to_none_over_tid():
    state = HystereseState(nivå=RISIKO_OVER_TERSKEL, pending_nivå=None, pending_since=None)
    times = [NOW + timedelta(minutes=i) for i in range(0, 20)]

    apply_hysteresis(state, rå_nivå=RISIKO_NAERMER_SEG, now=times[0], holdetid=HOLDETID)
    assert state.nivå == RISIKO_OVER_TERSKEL

    apply_hysteresis(state, rå_nivå=RISIKO_NAERMER_SEG, now=times[5], holdetid=HOLDETID)
    assert state.nivå == RISIKO_LIKE_UNDER

    apply_hysteresis(state, rå_nivå=RISIKO_NAERMER_SEG, now=times[10], holdetid=HOLDETID)
    assert state.nivå == RISIKO_NAERMER_SEG

    apply_hysteresis(state, rå_nivå=RISIKO_NAERMER_SEG, now=times[15], holdetid=HOLDETID)
    assert state.nivå == RISIKO_NAERMER_SEG
