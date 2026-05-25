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


def _simulate_with_kutt(hours: list[dict], trinn: list[tuple[float, int]], kutt_kwh: float = 0.5) -> dict[date, float]:
    """Anta Effektvakt fikk styre. Reduserer kwh med kutt_kwh i timer hvor risiko ville vært >= medium.

    kutt_kwh modellerer tre scenarier:
      0.15  - blind VVB (duty-cycle ~15%, 2 kW x 30 min x 0.15 = 0.15 kWh)
      1.0   - VVB med status-sensor (garantert 2 kW x 30 min = 1.0 kWh)
      2.5   - VVB med status + billader-pause (1.0 + 1.6 kWh ≈ 2.5 kWh)
    """
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
            ville_kuttet = margin <= safety_buffer_kw
            adjusted = kwh - kutt_kwh if ville_kuttet else kwh

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
    topp ~6 kWh i 5-10 kW-trinnet) vil sjelden vise målbar top-3-forbedring.
    Lastkutt hjelper kun når den aktuelle timen ER daglig topp. Det er forventet.
    Testen sjekker at systemet er ikke-negativt (invariant) og demonstrerer
    faktisk nytte i måneder nær en tier-grense.
    """
    trinn = KAPASITETSTRINN_PER_DSO["bkk"]["kapasitetstrinn"]

    forbedringer = []
    for path in BKK_FIXTURES:
        hours = _load_fixture(path)
        rå_daily = _aggregate_daily_max(hours)
        post_daily = _simulate_with_kutt(hours, trinn, kutt_kwh=0.5)

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


# Scenario-parametere: (kutt_kwh, label, min_forbedring_kw, min_måneder_med_forbedring, trinn_bevaring_krav)
_KUTT_SCENARIER = [
    pytest.param(
        0.15,
        "blind VVB (duty-cycle ~15%)",
        0.0,  # ingen forbedring forventet -- 0.15 kWh er for lite til å flytte topp-3
        0,
        0,
        id="blind_vvb",
    ),
    pytest.param(
        1.0,
        "VVB med status-sensor",
        0.3,  # garantert 1 kWh per event er nok til å skyve daglig topp
        1,
        0,
        id="vvb_med_status",
    ),
    pytest.param(
        2.5,
        "VVB med status + billader-pause",
        0.5,  # 2.5 kWh kutter dypt nok til >= 0.5 kW i minst 1 måned
        1,
        0,
        id="vvb_og_billader",
    ),
]


@pytest.mark.skipif(
    not FIXTURES_DIR.exists() or not BKK_FIXTURES,
    reason="strømkalkulator-fixturer ikke tilgjengelig",
)
@pytest.mark.parametrize("kutt_kwh,label,min_forbedring,min_måneder,min_trinn_bevaring", _KUTT_SCENARIER)
def test_replay_kutt_scenarier(
    kutt_kwh: float,
    label: str,
    min_forbedring: float,
    min_måneder: int,
    min_trinn_bevaring: int,
) -> None:
    """Tre VVB-scenarier mot reelle BKK-fixturer.

    Dokumenterer at blind lastkutt (duty-cycle-vektet) er tilnærmet verdiløst,
    mens status-sensor eller billader-kombinasjon gir målbar kapasitetsreduksjon.
    """
    trinn = KAPASITETSTRINN_PER_DSO["bkk"]["kapasitetstrinn"]

    print(f"\n--- Scenario: {label} (kutt_kwh={kutt_kwh}) ---")
    print(f"  {'Måned':<30} {'Rå topp-3':>10} {'Post topp-3':>11} {'Forbedring':>11}  Trinn")

    måneder_over_krav = 0
    måneder_med_trinn_bevaring = 0

    for path in BKK_FIXTURES:
        hours = _load_fixture(path)
        rå_daily = _aggregate_daily_max(hours)
        post_daily = _simulate_with_kutt(hours, trinn, kutt_kwh=kutt_kwh)

        rå_topp_3 = top_n_average(rå_daily, n=3) or 0.0
        post_topp_3 = top_n_average(post_daily, n=3) or 0.0
        forbedring = rå_topp_3 - post_topp_3

        rå_idx = _trinn_idx_for_kw(rå_topp_3, trinn)
        post_idx = _trinn_idx_for_kw(post_topp_3, trinn)
        trinn_info = f"idx {rå_idx} -> {post_idx}" if post_idx != rå_idx else f"idx {rå_idx} (uendret)"

        print(f"  {path.stem:<30} {rå_topp_3:>10.3f} {post_topp_3:>11.3f} {forbedring:>+11.3f}  {trinn_info}")

        # Invariant: styring skal aldri forverre
        assert forbedring >= 0.0, f"{path.stem}: scenario '{label}' forverret top-3-snittet med {forbedring:.3f} kW"

        if forbedring >= min_forbedring and min_forbedring > 0.0:
            måneder_over_krav += 1
        if post_idx > rå_idx:  # høyere idx = lavere trinn (færre kW)
            måneder_med_trinn_bevaring += 1

    print(f"  Måneder >= {min_forbedring} kW forbedring: {måneder_over_krav} (krav: {min_måneder})")
    print(f"  Måneder med trinn-bevaring: {måneder_med_trinn_bevaring} (krav: {min_trinn_bevaring})")

    if min_måneder > 0:
        # For scenariene med forventede forbedringer: enten nok måneder MED forbedring,
        # eller nok måneder med faktisk trinn-bevaring (fallback for billader-scenario).
        forbedring_ok = måneder_over_krav >= min_måneder
        trinn_ok = måneder_med_trinn_bevaring >= min_trinn_bevaring and min_trinn_bevaring > 0
        assert forbedring_ok or trinn_ok, (
            f"Scenario '{label}': "
            f"måneder >= {min_forbedring} kW: {måneder_over_krav} (krav {min_måneder}), "
            f"trinn-bevaring: {måneder_med_trinn_bevaring} (krav {min_trinn_bevaring})"
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
