"""Replay-test mot strømkalkulator-fixturer (NVE-modell: én topp-time per dag)."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from custom_components.effektvakt.coordinator import (
    compute_effective_threshold,
    lookup_tiers,
    top_n_average,
)
from custom_components.effektvakt.dso import KAPASITETSTRINN_PER_DSO

FIXTURES_DIR = Path(__file__).parent / "fixtures"
BKK_FIXTURES = sorted(FIXTURES_DIR.glob("bkk_*_hourly.json"))


def _load_fixture(path: Path) -> list[dict]:
    payload = json.loads(path.read_text())
    return payload["hours"]


def _aggregate_daily_max(hours: list[dict]) -> dict[date, float]:
    """Rå daily_max (uten styring). NVE-modellen: én topp-time per dag."""
    daily: dict[date, float] = {}
    for h in hours:
        if h["kwh"] is None:
            continue
        dt = datetime.fromisoformat(h["start_local"])
        d = dt.date()
        kwh = float(h["kwh"])
        if kwh > daily.get(d, 0.0):
            daily[d] = kwh
    return daily


def _simulate_with_shed(hours: list[dict], trinn: list[tuple[float, int]]) -> dict[date, float]:
    """Anta Effektvakt fikk styre. Reduserer kwh med 0.5 i timer hvor risiko ville vært >= medium."""
    daily_max_so_far: dict[date, float] = {}
    daily_result: dict[date, float] = {}
    safety_buffer_kw = 1.0

    for h in hours:
        if h["kwh"] is None:
            continue
        dt = datetime.fromisoformat(h["start_local"])
        d = dt.date()
        kwh = float(h["kwh"])

        tiers = lookup_tiers(projected_kw=kwh, trinn=trinn)
        if tiers.next_threshold_kw is None:
            adjusted = kwh
        else:
            effective_threshold = compute_effective_threshold(
                next_tier_threshold_kw=tiers.next_threshold_kw,
                daily_max_kw=daily_max_so_far,
            )
            margin = effective_threshold - kwh
            would_shed = margin <= safety_buffer_kw
            adjusted = kwh - 0.5 if would_shed else kwh

        if adjusted > daily_result.get(d, 0.0):
            daily_result[d] = adjusted
        if kwh > daily_max_so_far.get(d, 0.0):
            daily_max_so_far[d] = kwh

    return daily_result


def _trinn_idx_for_kw(kw: float, trinn: list[tuple[float, int]]) -> int:
    """Returner index av første trinn hvor kw <= terskel. -1 hvis over alle."""
    for i, (t, _) in enumerate(trinn):
        if kw <= t:
            return i
    return -1


@pytest.mark.skipif(
    not FIXTURES_DIR.exists() or not BKK_FIXTURES,
    reason="strømkalkulator-fixturer ikke tilgjengelig",
)
def test_replay_skadebegrensning_over_5_måneder():
    """Kontrafaktisk besparelse: styring skal aldri forverre og gi positiv effekt minst én måned.

    Måneder med høyt forbruk godt over en tier-grense (f.eks. jan/feb/des med
    topp ~6 kWh i 5-10 kW-trinnet) vil sjelden vise målbar top-3-forbedring --
    shedding hjelper kun når borter-time ER daglig topp. Det er forventet.
    Testen sjekker at systemet er ikke-negativt (invariant) og demonstrerer
    faktisk nytte i måneder nær en tier-grense.
    """
    trinn = KAPASITETSTRINN_PER_DSO["bkk"]["kapasitetstrinn"]

    forbedringer = []
    for path in BKK_FIXTURES:
        hours = _load_fixture(path)
        rå_daily = _aggregate_daily_max(hours)
        post_daily = _simulate_with_shed(hours, trinn)

        rå_topp_3 = top_n_average(rå_daily, n=3) or 0.0
        post_topp_3 = top_n_average(post_daily, n=3) or 0.0
        forbedringer.append((path.stem, rå_topp_3 - post_topp_3))

    print("\nMåned-for-måned forbedring:")
    for navn, forbedring in forbedringer:
        print(f"  {navn}: {forbedring:+.3f} kW")

    # Invariant: styring skal aldri forverre top-3-snittet
    for navn, forbedring in forbedringer:
        assert forbedring >= 0.0, f"{navn}: styring forverret top-3-snittet med {forbedring:.3f} kW"

    # Krav: minst én måned med >= 0.3 kW forbedring -- demonstrerer at logikken
    # faktisk hjelper i måneder nær en tier-grense.
    over_0_3 = sum(1 for _, f in forbedringer if f >= 0.3)
    assert over_0_3 >= 1, (
        f"Forventet minst 1 måned med >= 0.3 kW forbedring, fikk {over_0_3}. "
        f"Sjekk at fixture-data inneholder måneder nær en tier-grense."
    )


@pytest.mark.skipif(
    not FIXTURES_DIR.exists() or not BKK_FIXTURES,
    reason="strømkalkulator-fixturer ikke tilgjengelig",
)
def test_replay_ingen_false_positives_lavt_forbruk():
    """Effektvakt skal ikke forsøke kutt i timer langt under tier-grensa."""
    trinn = KAPASITETSTRINN_PER_DSO["bkk"]["kapasitetstrinn"]

    for path in BKK_FIXTURES:
        hours = _load_fixture(path)
        daily_max_so_far: dict[date, float] = {}

        for h in hours:
            if h["kwh"] is None:
                continue
            dt = datetime.fromisoformat(h["start_local"])
            d = dt.date()
            kwh = float(h["kwh"])
            # Cutoff at 1.0 kWh: ensures margin > 1.0 is achievable against
            # BKK's lowest tier (2.0 kW). Values between 1.0 and 2.0 are
            # legitimately borderline and not tested here.
            if kwh > 1.0:
                if kwh > daily_max_so_far.get(d, 0.0):
                    daily_max_so_far[d] = kwh
                continue

            tiers = lookup_tiers(projected_kw=kwh, trinn=trinn)
            if tiers.next_threshold_kw is None:
                continue
            effective_threshold = compute_effective_threshold(
                next_tier_threshold_kw=tiers.next_threshold_kw,
                daily_max_kw=daily_max_so_far,
            )
            margin = effective_threshold - kwh
            assert margin > 1.0, (
                f"{path.stem} {dt}: lav forbruks-time {kwh:.2f} kWh " f"gir margin {margin:.2f} (forventet > 1.0)"
            )

            if kwh > daily_max_so_far.get(d, 0.0):
                daily_max_so_far[d] = kwh
