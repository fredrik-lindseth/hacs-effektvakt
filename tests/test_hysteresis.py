"""Tester for hysterese-state-maskinen."""

from __future__ import annotations

from datetime import datetime, timedelta

from custom_components.effektvakt.const import RISIKO_HIGH, RISIKO_LOW, RISIKO_MEDIUM, RISIKO_NONE
from custom_components.effektvakt.coordinator import HystereseState, apply_hysteresis

HOLDETID = timedelta(minutes=5)
NOW = datetime(2026, 5, 25, 14, 0, 0)


def test_oppgang_er_umiddelbar():
    state = HystereseState(nivå=RISIKO_NONE, pending_nivå=None, pending_since=None)
    apply_hysteresis(state, rå_nivå=RISIKO_MEDIUM, now=NOW, holdetid=HOLDETID)
    assert state.nivå == RISIKO_MEDIUM
    assert state.pending_nivå is None


def test_oppgang_overskriver_pending():
    state = HystereseState(
        nivå=RISIKO_HIGH,
        pending_nivå=RISIKO_MEDIUM,
        pending_since=NOW - timedelta(minutes=2),
    )
    apply_hysteresis(state, rå_nivå=RISIKO_HIGH, now=NOW, holdetid=HOLDETID)
    assert state.nivå == RISIKO_HIGH
    assert state.pending_nivå is None
    assert state.pending_since is None


def test_nedgang_starter_timer():
    state = HystereseState(nivå=RISIKO_HIGH, pending_nivå=None, pending_since=None)
    apply_hysteresis(state, rå_nivå=RISIKO_LOW, now=NOW, holdetid=HOLDETID)
    assert state.nivå == RISIKO_HIGH
    assert state.pending_nivå == RISIKO_LOW
    assert state.pending_since == NOW


def test_nedgang_holder_innenfor_holdetid():
    state = HystereseState(
        nivå=RISIKO_HIGH,
        pending_nivå=RISIKO_LOW,
        pending_since=NOW - timedelta(minutes=2),
    )
    apply_hysteresis(state, rå_nivå=RISIKO_LOW, now=NOW, holdetid=HOLDETID)
    assert state.nivå == RISIKO_HIGH


def test_nedgang_trigger_etter_holdetid_multi_step():
    """Hopp fra HIGH til NONE: går trinn-for-trinn med holdetid mellom."""
    state = HystereseState(
        nivå=RISIKO_HIGH,
        pending_nivå=RISIKO_NONE,
        pending_since=NOW - timedelta(minutes=5),
    )
    apply_hysteresis(state, rå_nivå=RISIKO_NONE, now=NOW, holdetid=HOLDETID)
    assert state.nivå == RISIKO_MEDIUM
    assert state.pending_since == NOW


def test_oscillasjon_kansellerer_pending():
    state = HystereseState(
        nivå=RISIKO_HIGH,
        pending_nivå=RISIKO_LOW,
        pending_since=NOW - timedelta(minutes=2),
    )
    apply_hysteresis(state, rå_nivå=RISIKO_HIGH, now=NOW, holdetid=HOLDETID)
    assert state.nivå == RISIKO_HIGH
    assert state.pending_nivå is None
    assert state.pending_since is None


def test_endret_pending_nullstiller_timer():
    state = HystereseState(
        nivå=RISIKO_HIGH,
        pending_nivå=RISIKO_LOW,
        pending_since=NOW - timedelta(minutes=2),
    )
    apply_hysteresis(state, rå_nivå=RISIKO_MEDIUM, now=NOW, holdetid=HOLDETID)
    assert state.nivå == RISIKO_HIGH
    assert state.pending_nivå == RISIKO_MEDIUM
    assert state.pending_since == NOW


def test_full_nedgang_to_none_over_tid():
    state = HystereseState(nivå=RISIKO_HIGH, pending_nivå=None, pending_since=None)
    times = [NOW + timedelta(minutes=i) for i in range(0, 20)]

    apply_hysteresis(state, rå_nivå=RISIKO_LOW, now=times[0], holdetid=HOLDETID)
    assert state.nivå == RISIKO_HIGH

    apply_hysteresis(state, rå_nivå=RISIKO_LOW, now=times[5], holdetid=HOLDETID)
    assert state.nivå == RISIKO_MEDIUM

    apply_hysteresis(state, rå_nivå=RISIKO_LOW, now=times[10], holdetid=HOLDETID)
    assert state.nivå == RISIKO_LOW

    apply_hysteresis(state, rå_nivå=RISIKO_LOW, now=times[15], holdetid=HOLDETID)
    assert state.nivå == RISIKO_LOW
