"""Coordinator for Effektvakt."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util_module

from .const import (
    CONF_DSO,
    CONF_ENERGY_SENSOR,
    CONF_KAPASITETSTRINN_CUSTOM,
    CONF_MIN_RISIKO_FOR_KUTT,
    CONF_POWER_SENSOR,
    CONF_RISIKO_HOLDETID_MINUTTER,
    CONF_SAFETY_BUFFER_KW,
    DEFAULT_MIN_RISIKO_FOR_KUTT,
    DEFAULT_RISIKO_HOLDETID_MINUTTER,
    DEFAULT_SAFETY_BUFFER_KW,
    DOMAIN,
    MAX_POWER_CLAMP_W,
    RISIKO_HIGH,
    RISIKO_LEVELS,
    RISIKO_LOW,
    RISIKO_MEDIUM,
    RISIKO_NONE,
    RISIKO_RANK,
    STORAGE_VERSION,
    TICK_INTERVAL_BY_RISIKO,
    VALID_ENERGY_UNITS,
    VALID_POWER_UNITS,
    WATCHDOG_STALE_THRESHOLD_SECONDS,
)
from .dso import KAPASITETSTRINN_PER_DSO

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def dt_util_now() -> datetime:
    """Wrapper for monkeypatch-vennlig now()."""
    return dt_util_module.now()


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


class EffektvaktCoordinator(DataUpdateCoordinator):
    """Coordinator for Effektvakt."""

    def __init__(self, hass: HomeAssistant, entry: object) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=TICK_INTERVAL_BY_RISIKO[RISIKO_NONE]),
        )
        self.entry = entry
        self.power_sensor: str | None = entry.data.get(CONF_POWER_SENSOR)
        self.energy_sensor: str | None = entry.data.get(CONF_ENERGY_SENSOR)
        self.safety_buffer_kw: float = float(entry.data.get(CONF_SAFETY_BUFFER_KW, DEFAULT_SAFETY_BUFFER_KW))
        self.min_risiko_for_kutt: str = entry.data.get(CONF_MIN_RISIKO_FOR_KUTT, DEFAULT_MIN_RISIKO_FOR_KUTT)
        self.risiko_holdetid: timedelta = timedelta(minutes=int(
            entry.data.get(CONF_RISIKO_HOLDETID_MINUTTER, DEFAULT_RISIKO_HOLDETID_MINUTTER)
        ))

        dso_id = entry.data.get(CONF_DSO)
        custom = entry.data.get(CONF_KAPASITETSTRINN_CUSTOM)
        if custom:
            self.kapasitetstrinn: list[tuple[float, int]] = [(float(t[0]), int(t[1])) for t in custom]
        else:
            dso_info = KAPASITETSTRINN_PER_DSO.get(dso_id)
            self.kapasitetstrinn = list(dso_info["kapasitetstrinn"]) if dso_info else []

        # Mutable state
        self._daily_max_kw: dict[date, float] = {}
        self._current_month: str = dt_util_now().strftime("%Y-%m")
        self._current_hour_kwh: float = 0.0
        self._current_hour_start: datetime | None = None
        self._current_hour_bucket: tuple[int, timedelta | None] | None = None
        self._energy_at_hour_start: float | None = None
        self._previous_month_top_3_snitt_kw: float | None = None
        self._previous_month_name: str | None = None
        self._hysterese_state = HystereseState(nivå=RISIKO_NONE)
        self._last_successful_update: datetime | None = None
        self._store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}")
        self._store_loaded = False

    async def _load_stored_data(self) -> None:
        if self._store_loaded:
            return
        stored = await self._store.async_load()
        self._store_loaded = True
        if not stored:
            return
        data = stored.get("data", {})
        for date_str, kw in (data.get("daily_max_kw") or {}).items():
            try:
                d = date.fromisoformat(date_str)
                self._daily_max_kw[d] = float(kw)
            except (ValueError, TypeError):
                continue
        self._current_hour_kwh = float(data.get("current_hour_kwh", 0.0))
        self._energy_at_hour_start = data.get("energy_at_hour_start")
        self._previous_month_top_3_snitt_kw = data.get("previous_month_top_3_snitt_kw")
        self._previous_month_name = data.get("previous_month_name")
        hyst = data.get("hysterese_state", {})
        if hyst.get("nivå") in RISIKO_LEVELS:
            self._hysterese_state.nivå = hyst["nivå"]

    async def _persist(self) -> None:
        await self._store.async_save({
            "data": {
                "current_month": self._current_month,
                "daily_max_kw": {d.isoformat(): kw for d, kw in self._daily_max_kw.items()},
                "current_hour_kwh": self._current_hour_kwh,
                "energy_at_hour_start": self._energy_at_hour_start,
                "previous_month_top_3_snitt_kw": self._previous_month_top_3_snitt_kw,
                "previous_month_name": self._previous_month_name,
                "hysterese_state": {
                    "nivå": self._hysterese_state.nivå,
                    "pending_nivå": self._hysterese_state.pending_nivå,
                    "pending_since": (
                        self._hysterese_state.pending_since.isoformat()
                        if self._hysterese_state.pending_since else None
                    ),
                },
            }
        })

    async def _async_update_data(self) -> dict:
        await self._load_stored_data()
        now = dt_util_now()

        hour_bucket = (now.hour, now.utcoffset())
        if self._current_hour_bucket is not None and self._current_hour_bucket != hour_bucket:
            self._finalize_hour()
        if self._current_hour_bucket is None or self._current_hour_bucket != hour_bucket:
            self._current_hour_bucket = hour_bucket
            self._current_hour_start = now.replace(minute=0, second=0, microsecond=0)
            self._current_hour_kwh = 0.0

        month_str = now.strftime("%Y-%m")
        if month_str != self._current_month:
            self._handle_month_rollover()
            self._current_month = month_str

        current_kw = read_power_kw(self.hass, self.power_sensor) or 0.0
        energy_now = read_energy_kwh(self.hass, self.energy_sensor)

        if energy_now is not None:
            if self._energy_at_hour_start is None:
                self._energy_at_hour_start = energy_now
            else:
                delta = energy_now - self._energy_at_hour_start - self._current_hour_kwh
                if delta > 0:
                    self._current_hour_kwh += delta

        elapsed_h = compute_elapsed_h(now)
        projected_avg = compute_projected_avg(
            actual_kwh_this_hour=self._current_hour_kwh,
            current_kw=current_kw,
            elapsed_h=elapsed_h,
        )

        tiers = lookup_tiers(projected_kw=projected_avg, trinn=self.kapasitetstrinn)

        if tiers.next_threshold_kw is None:
            effective_threshold = float("inf")
        else:
            effective_threshold = compute_effective_threshold(
                next_tier_threshold_kw=tiers.next_threshold_kw,
                daily_max_kw=self._daily_max_kw,
            )

        margin = effective_threshold - projected_avg
        rå = classify_raw_risk(margin_kw=margin, safety_buffer_kw=self.safety_buffer_kw)
        apply_hysteresis(self._hysterese_state, rå_nivå=rå, now=now, holdetid=self.risiko_holdetid)

        new_interval = timedelta(seconds=TICK_INTERVAL_BY_RISIKO[self._hysterese_state.nivå])
        if self.update_interval != new_interval:
            self.update_interval = new_interval

        self._last_successful_update = now

        topp_3 = top_n_average(self._daily_max_kw, n=3) or 0.0
        topp_2 = top_n_average(self._daily_max_kw, n=2)

        await self._persist()

        return {
            "projected_avg_kw": round(projected_avg, 3),
            "current_kw": round(current_kw, 3),
            "actual_kwh_this_hour": round(self._current_hour_kwh, 3),
            "elapsed_minutes_in_hour": int(elapsed_h * 60),
            "margin_kw": round(margin, 3),
            "effective_threshold_kw": effective_threshold,
            "next_tier_threshold_kw": tiers.next_threshold_kw,
            "prev_tier_threshold_kw": tiers.prev_threshold_kw,
            "next_tier_pris_per_maned": tiers.next_pris_per_mnd,
            "topp_3_snitt_denne_maned_kw": round(topp_3, 3),
            "topp_2_snitt_denne_maned_kw": round(topp_2, 3) if topp_2 else None,
            "kutt_anbefalt_kw": max(0.0, -margin),
            "risiko_niva": self._hysterese_state.nivå,
            "raw_risiko_niva": rå,
            "last_update": now.isoformat(),
        }

    def _finalize_hour(self) -> None:
        if self._current_hour_kwh > 0 and self._current_hour_start is not None:
            d = self._current_hour_start.date()
            existing = self._daily_max_kw.get(d, 0.0)
            if self._current_hour_kwh > existing:
                self._daily_max_kw[d] = round(self._current_hour_kwh, 3)
        self._current_hour_kwh = 0.0

    def _handle_month_rollover(self) -> None:
        topp_3 = top_n_average(self._daily_max_kw, n=3)
        if topp_3 is not None:
            self._previous_month_top_3_snitt_kw = round(topp_3, 3)
            self._previous_month_name = self._current_month
        self._daily_max_kw = {}


def is_coordinator_stale(
    *,
    last_successful_update: datetime | None,
    now: datetime,
) -> bool:
    """True hvis siste vellykkede oppdatering er eldre enn watchdog-terskel."""
    if last_successful_update is None:
        return True
    return (now - last_successful_update).total_seconds() > WATCHDOG_STALE_THRESHOLD_SECONDS
