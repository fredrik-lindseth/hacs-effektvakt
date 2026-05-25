"""Tester for watchdog som flagger stale coordinator."""

from __future__ import annotations

from datetime import datetime, timedelta

from custom_components.effektvakt.const import WATCHDOG_STALE_THRESHOLD_SECONDS
from custom_components.effektvakt.coordinator import is_coordinator_stale


NOW = datetime(2026, 5, 25, 14, 0, 0)


def test_stale_aldri_oppdatert():
    assert is_coordinator_stale(last_successful_update=None, now=NOW) is True


def test_stale_oppdatert_for_lenge_siden():
    last = NOW - timedelta(seconds=WATCHDOG_STALE_THRESHOLD_SECONDS + 1)
    assert is_coordinator_stale(last_successful_update=last, now=NOW) is True


def test_ikke_stale_oppdatert_nylig():
    last = NOW - timedelta(seconds=30)
    assert is_coordinator_stale(last_successful_update=last, now=NOW) is False


def test_ikke_stale_pa_grensen():
    last = NOW - timedelta(seconds=WATCHDOG_STALE_THRESHOLD_SECONDS - 1)
    assert is_coordinator_stale(last_successful_update=last, now=NOW) is False
