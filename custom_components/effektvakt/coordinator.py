"""Coordinator for Effektvakt."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from .const import (
    MAX_POWER_CLAMP_W,
    RISIKO_HIGH,
    RISIKO_LEVELS,
    RISIKO_LOW,
    RISIKO_MEDIUM,
    RISIKO_NONE,
    RISIKO_RANK,
    VALID_ENERGY_UNITS,
    VALID_POWER_UNITS,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def read_power_kw(hass: HomeAssistant, entity_id: str | None) -> float | None:
    """Les power-sensor og returner verdi normalisert til kW.

    Returnerer None hvis sensor ikke finnes, er unavailable, har ugyldig
    unit, eller verdien er ikke-finit/over MAX_POWER_CLAMP_W.
    """
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in ("unknown", "unavailable", None):
        return None
    try:
        value = float(state.state)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(value):
        return None
    unit = (state.attributes or {}).get("unit_of_measurement")
    if unit not in VALID_POWER_UNITS:
        return None
    if unit == "W":
        if value > MAX_POWER_CLAMP_W:
            _LOGGER.warning("power_sensor %s = %s W > clamp %s", entity_id, value, MAX_POWER_CLAMP_W)
            return None
        return value / 1000
    return value  # kW


def read_energy_kwh(hass: HomeAssistant, entity_id: str | None) -> float | None:
    """Les energy-sensor og returner verdi normalisert til kWh.

    Returnerer None hvis sensor ikke finnes, er unavailable, eller har ugyldig
    unit.
    """
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in ("unknown", "unavailable", None):
        return None
    try:
        value = float(state.state)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    unit = (state.attributes or {}).get("unit_of_measurement")
    if unit not in VALID_ENERGY_UNITS:
        return None
    if unit == "Wh":
        return value / 1000
    return value  # kWh


def classify_raw_risk(*, margin_kw: float, safety_buffer_kw: float) -> str:
    """Klassifiser rå risiko basert på margin og safety_buffer.

    Returnerer en av RISIKO_NONE, RISIKO_LOW, RISIKO_MEDIUM, RISIKO_HIGH.
    Tabell:
      none:   margin > 2 × buffer
      low:    buffer < margin <= 2 × buffer
      medium: 0 < margin <= buffer
      high:   margin <= 0
    """
    if margin_kw <= 0:
        return RISIKO_HIGH
    if margin_kw <= safety_buffer_kw:
        return RISIKO_MEDIUM
    if margin_kw <= 2 * safety_buffer_kw:
        return RISIKO_LOW
    return RISIKO_NONE


def top_n_average(daily_max_kw: dict[date, float], *, n: int) -> float | None:
    """Snitt av de n høyeste verdiene i daily_max_kw.

    Returnerer None hvis dict er tom. Hvis det er færre enn n entries,
    returneres snittet av alle.
    """
    if not daily_max_kw:
        return None
    sorted_vals = sorted(daily_max_kw.values(), reverse=True)
    take = sorted_vals[:n]
    return sum(take) / len(take)


def compute_effective_threshold(
    *,
    next_tier_threshold_kw: float,
    daily_max_kw: dict[date, float],
) -> float:
    """Beregn effective_threshold for topp-3-bevissthet.

    Hvis < 2 dager logget: fall tilbake til next_tier_threshold (konservativt
    valg tidlig i måneden).

    Ellers: max(next_tier_threshold, snitt_av_topp_2_dager).
    """
    if len(daily_max_kw) < 2:
        return next_tier_threshold_kw
    topp_2 = top_n_average(daily_max_kw, n=2)
    assert topp_2 is not None
    return max(next_tier_threshold_kw, topp_2)


@dataclass(frozen=True)
class TierInfo:
    """Resultat fra tier-oppslag."""
    prev_threshold_kw: float | None
    next_threshold_kw: float | None
    next_pris_per_mnd: int | None


def lookup_tiers(
    *,
    projected_kw: float,
    trinn: list[tuple[float, int]],
) -> TierInfo:
    """Finn prev og next tier basert på projisert kW.

    Trinn-listen er sortert stigende på kW-terskel. "next" er det laveste
    trinnet hvor terskel >= projected_kw. "prev" er trinnet rett under.
    """
    if not trinn:
        return TierInfo(None, None, None)

    next_idx: int | None = None
    for i, (threshold, _) in enumerate(trinn):
        if projected_kw <= threshold:
            next_idx = i
            break

    if next_idx is None:
        prev_kw, _prev_pris = trinn[-1]
        return TierInfo(prev_threshold_kw=prev_kw, next_threshold_kw=None, next_pris_per_mnd=None)

    next_kw, next_pris = trinn[next_idx]
    prev_kw = trinn[next_idx - 1][0] if next_idx > 0 else None
    return TierInfo(prev_threshold_kw=prev_kw, next_threshold_kw=next_kw, next_pris_per_mnd=next_pris)


@dataclass
class HystereseState:
    """Stateful hysterese-tilstand."""
    nivå: str
    pending_nivå: str | None = None
    pending_since: datetime | None = None


def _nivå_ett_under(nivå: str) -> str:
    """Returner risiko-nivået ett trinn under det gitte. RISIKO_NONE returnerer seg selv."""
    idx = RISIKO_RANK[nivå]
    if idx == 0:
        return nivå
    return RISIKO_LEVELS[idx - 1]


def apply_hysteresis(
    state: HystereseState,
    *,
    rå_nivå: str,
    now: datetime,
    holdetid: timedelta,
) -> None:
    """Oppdater hysterese-state in-place.

    Oppgang er umiddelbar. Nedgang krever holdetid. Multi-step nedgang
    skjer ett trinn av gangen med ny timer per trinn. Se spec for full
    policy.
    """
    rå_rank = RISIKO_RANK[rå_nivå]
    cur_rank = RISIKO_RANK[state.nivå]

    if rå_rank >= cur_rank:
        state.nivå = rå_nivå
        state.pending_nivå = None
        state.pending_since = None
        return

    if state.pending_nivå != rå_nivå:
        state.pending_nivå = rå_nivå
        state.pending_since = now
        return

    if state.pending_since is None:
        state.pending_since = now
        return

    if (now - state.pending_since) >= holdetid:
        ett_under = _nivå_ett_under(state.nivå)
        state.nivå = ett_under
        if RISIKO_RANK[state.nivå] > rå_rank:
            state.pending_since = now
        else:
            state.pending_nivå = None
            state.pending_since = None


def compute_projected_avg(
    *,
    actual_kwh_this_hour: float,
    current_kw: float,
    elapsed_h: float,
) -> float:
    """Projisert time-snitt-kW.

    actual_kwh_this_hour: hva som er målt så langt denne klokketimen.
    current_kw: instant power-sensor-verdi.
    elapsed_h: hvor langt inn i timen vi er (0.0 til 1.0).
    """
    remaining_h = max(0.0, 1.0 - elapsed_h)
    return actual_kwh_this_hour + current_kw * remaining_h


def compute_elapsed_h(now: datetime) -> float:
    """Andel av klokketimen som er passert."""
    return (now.minute + now.second / 60) / 60
