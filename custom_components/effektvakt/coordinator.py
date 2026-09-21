"""Coordinator for Effektvakt."""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass, fields
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util_module

from .const import (
    BLIND_ASSUMED_KUTT_KW,
    CONF_DSO,
    CONF_EKSTRA_POWER_SENSORS,
    CONF_ENERGY_SENSOR,
    CONF_KAPASITETSTRINN_CUSTOM,
    CONF_KUTT_STRATEGI,
    CONF_MIN_RISIKO_FOR_KUTT,
    CONF_POWER_SENSOR,
    CONF_RISIKO_HOLDETID_MINUTTER,
    CONF_SAFETY_BUFFER_KW,
    CONF_VVB_POWER_SENSOR,
    DEFAULT_KUTT_STRATEGI,
    DEFAULT_MIN_RISIKO_FOR_KUTT,
    DEFAULT_RISIKO_HOLDETID_MINUTTER,
    DEFAULT_SAFETY_BUFFER_KW,
    DOMAIN,
    EKSTRA_SENSOR_ACTIVE_THRESHOLD_W,
    LEGACY_STRATEGI_MAPPING,
    MAX_POWER_CLAMP_W,
    RISIKO_HIGH,
    RISIKO_LEVELS,
    RISIKO_LOW,
    RISIKO_MEDIUM,
    RISIKO_NONE,
    RISIKO_RANK,
    STORAGE_VERSION,
    STRATEGI_BLIND,
    STRATEGI_VVB_PLUSS_EKSTRA,
    STRATEGI_VVB_STATUS,
    TICK_INTERVAL_BY_RISIKO,
    VALID_ENERGY_UNITS,
    VALID_POWER_UNITS,
    VVB_ACTIVE_THRESHOLD_W,
    WATCHDOG_STALE_THRESHOLD_SECONDS,
)
from .dso import KAPASITETSTRINN_PER_DSO

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Rollene en kuttbar last kan ha. Verdiene går ut i attributtet kutt_kilder,
# så de er en del av kontrakten mot dashboards.
ROLLE_VVB = "vvb"
ROLLE_EKSTRA = "ekstra"

TERSKEL_PER_ROLLE: dict[str, float] = {
    ROLLE_VVB: VVB_ACTIVE_THRESHOLD_W,
    ROLLE_EKSTRA: EKSTRA_SENSOR_ACTIVE_THRESHOLD_W,
}

# Hvilke roller som faktisk teller med i summen, per strategi. blind leser ingen
# sensorer i det hele tatt, og ukjent strategi teller ingenting.
ROLLER_PER_STRATEGI: dict[str, frozenset[str]] = {
    STRATEGI_BLIND: frozenset(),
    STRATEGI_VVB_STATUS: frozenset({ROLLE_VVB}),
    STRATEGI_VVB_PLUSS_EKSTRA: frozenset({ROLLE_VVB, ROLLE_EKSTRA}),
}


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


def read_friendly_name(hass: HomeAssistant, entity_id: str) -> str | None:
    """HA sitt friendly_name for en entitet, None hvis den ikke finnes ennå."""
    state = hass.states.get(entity_id)
    if state is None:
        return None
    navn = (state.attributes or {}).get("friendly_name")
    return navn if isinstance(navn, str) else None


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
      none:   margin > 2 x buffer
      low:    buffer < margin <= 2 x buffer
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


@dataclass(frozen=True)
class KostnadInfo:
    """Kostnadsbildet for kapasitetsleddet denne måneden.

    Feltnavnene er også nøklene coordinatoren eksponerer i data-dicten.
    """

    kostnad_neste_trinn_kr: int
    trinn_na_kr: int
    trinn_na_ovre_grense_kw: float | None
    trinn_neste_kr: int | None
    besparelse_trinn_under_kr: int
    trinn_under_oppnaelig: bool
    kostnad_denne_timen_kr: int
    topp_3_projisert_kw: float
    minste_mulige_topp_3_kw: float
    hoyeste_trinn: bool


KOSTNAD_FELT_NAVN: tuple[str, ...] = tuple(f.name for f in fields(KostnadInfo))


def _trinn_indeks(kw: float, trinn: list[tuple[float, int]]) -> int:
    """Indeks til trinnet en kW-verdi havner i, altså laveste trinn med terskel >= kw.

    Over høyeste terskel returneres øverste trinn.
    """
    for i, (terskel, _) in enumerate(trinn):
        if kw <= terskel:
            return i
    return len(trinn) - 1


def compute_kostnad(
    *,
    trinn: list[tuple[float, int]],
    daily_max_kw: dict[date, float],
    today: date,
    projected_kw: float,
) -> KostnadInfo | None:
    """Hva kapasitetsleddet koster, og hva som står på spill akkurat nå.

    `topp_3_projisert_kw` er topp-3-snittet der dagens dagsmaks erstattes med
    max(dagens maks så langt, projisert time-snitt nå). Det er trinnet måneden
    ligger an til, og `kostnad_neste_trinn_kr` er hoppet derfra til neste trinn.

    `minste_mulige_topp_3_kw` teller bare dagsmaks som alt er låst inn (ferdige
    timer), delt på 3 uansett antall dager. Den inneværende timen holdes utenfor
    nettopp fordi den fortsatt kan kuttes, så tallet er en nedre skranke for hva
    måneden kan ende på. Er den under terskelen til trinnet under, er trinnet
    fortsatt innen rekkevidde.

    `kostnad_denne_timen_kr` er kronene den inneværende timen er i ferd med å
    låse inn: prisen for trinnet vi ligger an til minus prisen for trinnet
    topp-3 gir uten denne timen.

    Tomt trinn-sett (ukjent nettselskap) gir None.
    """
    if not trinn:
        return None

    projiserte_dager = dict(daily_max_kw)
    projiserte_dager[today] = max(daily_max_kw.get(today, 0.0), projected_kw)
    topp_3_projisert = top_n_average(projiserte_dager, n=3) or 0.0
    topp_3_na = top_n_average(daily_max_kw, n=3) or 0.0
    minste_mulige = sum(sorted(daily_max_kw.values(), reverse=True)[:3]) / 3

    idx = _trinn_indeks(topp_3_projisert, trinn)
    ovre_grense_kw, trinn_na_kr = trinn[idx]
    er_hoyeste = idx == len(trinn) - 1

    trinn_neste_kr = None if er_hoyeste else trinn[idx + 1][1]
    kostnad_neste_trinn_kr = 0 if trinn_neste_kr is None else trinn_neste_kr - trinn_na_kr

    if idx > 0:
        under_terskel_kw, under_kr = trinn[idx - 1]
        besparelse_trinn_under_kr = trinn_na_kr - under_kr
        trinn_under_oppnaelig = minste_mulige <= under_terskel_kw
    else:
        besparelse_trinn_under_kr = 0
        trinn_under_oppnaelig = False

    trinn_uten_denne_timen_kr = trinn[_trinn_indeks(topp_3_na, trinn)][1]

    return KostnadInfo(
        kostnad_neste_trinn_kr=kostnad_neste_trinn_kr,
        trinn_na_kr=trinn_na_kr,
        # float("inf") er ugyldig JSON og knekker recorder og websocket
        trinn_na_ovre_grense_kw=None if math.isinf(ovre_grense_kw) else ovre_grense_kw,
        trinn_neste_kr=trinn_neste_kr,
        besparelse_trinn_under_kr=besparelse_trinn_under_kr,
        trinn_under_oppnaelig=trinn_under_oppnaelig,
        kostnad_denne_timen_kr=max(0, trinn_na_kr - trinn_uten_denne_timen_kr),
        topp_3_projisert_kw=round(topp_3_projisert, 3),
        minste_mulige_topp_3_kw=round(minste_mulige, 3),
        hoyeste_trinn=er_hoyeste,
    )


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
        self.risiko_holdetid: timedelta = timedelta(
            minutes=int(entry.data.get(CONF_RISIKO_HOLDETID_MINUTTER, DEFAULT_RISIKO_HOLDETID_MINUTTER))
        )
        self.vvb_power_sensor: str | None = entry.data.get(CONF_VVB_POWER_SENSOR)
        self.ekstra_power_sensors: list[str] = list(entry.data.get(CONF_EKSTRA_POWER_SENSORS) or [])

        # Bakoverkompatibilitet for strategi-navn
        strategi_raw = entry.data.get(CONF_KUTT_STRATEGI, DEFAULT_KUTT_STRATEGI)
        self.kutt_strategi: str = LEGACY_STRATEGI_MAPPING.get(strategi_raw, strategi_raw)

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
        await self._store.async_save(
            {
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
                            if self._hysterese_state.pending_since
                            else None
                        ),
                    },
                }
            }
        )

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
            self._energy_at_hour_start = None

        month_str = now.strftime("%Y-%m")
        if month_str != self._current_month:
            self._handle_month_rollover()
            self._current_month = month_str

        current_kw = read_power_kw(self.hass, self.power_sensor) or 0.0
        energy_now = read_energy_kwh(self.hass, self.energy_sensor)

        avlesninger = self._les_kutt_kilder()
        vvb_power_w = next((a.effekt_w for a in avlesninger if a.rolle == ROLLE_VVB), None)
        ekstra_power_w_list = [a.effekt_w for a in avlesninger if a.rolle == ROLLE_EKSTRA]

        tilgjengelig_kutt_kw = compute_tilgjengelig_kutt_kw(
            strategi=self.kutt_strategi,
            vvb_power_w=vvb_power_w,
            ekstra_power_w=ekstra_power_w_list,
        )
        kutt_kilder = build_kutt_kilder(strategi=self.kutt_strategi, avlesninger=avlesninger)

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

        kostnad = compute_kostnad(
            trinn=self.kapasitetstrinn,
            daily_max_kw=self._daily_max_kw,
            today=now.date(),
            projected_kw=projected_avg,
        )
        # Nøklene er feltnavnene i KostnadInfo. Uten kjente kapasitetstrinn er de alle None.
        kostnad_felter: dict[str, object | None] = (
            asdict(kostnad) if kostnad is not None else dict.fromkeys(KOSTNAD_FELT_NAVN)
        )

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
            "tilgjengelig_kutt_kw": round(tilgjengelig_kutt_kw, 3),
            "vvb_power_w": vvb_power_w,
            "ekstra_power_w_total": sum(p for p in ekstra_power_w_list if p is not None) or None,
            "kutt_strategi": self.kutt_strategi,
            "kutt_kilder": [asdict(k) for k in kutt_kilder],
            **kostnad_felter,
        }

    def _les_kutt_kilder(self) -> list[KildeAvlesning]:
        """Les effekten til hver konfigurerte kuttkilde, VVB først.

        Kilden er med i lista uansett strategi. Om den teller med er et eget
        spørsmål som build_kutt_kilder svarer på.
        """
        konfigurert: list[tuple[str, str]] = []
        if self.vvb_power_sensor:
            konfigurert.append((self.vvb_power_sensor, ROLLE_VVB))
        konfigurert.extend((sensor, ROLLE_EKSTRA) for sensor in self.ekstra_power_sensors)

        avlesninger = []
        for entity_id, rolle in konfigurert:
            kw = read_power_kw(self.hass, entity_id)
            avlesninger.append(
                KildeAvlesning(
                    entity_id=entity_id,
                    navn=read_friendly_name(self.hass, entity_id),
                    effekt_w=None if kw is None else kw * 1000.0,
                    rolle=rolle,
                )
            )
        return avlesninger

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


@dataclass(frozen=True)
class KildeAvlesning:
    """Rå avlesning av en konfigurert kuttkilde, før strategien har sagt sitt.

    `effekt_w` er None når sensoren er unavailable, unknown eller ulesbar. Det
    er noe annet enn 0 W: da vet vi ikke hva lasten trekker.
    """

    entity_id: str
    navn: str | None
    effekt_w: float | None
    rolle: str


@dataclass(frozen=True)
class KuttKilde:
    """En kuttbar last slik den ser ut akkurat nå.

    Feltnavnene er nøklene i attributtet kutt_kilder.
    """

    entity_id: str
    navn: str | None
    effekt_w: float | None
    teller_med: bool
    rolle: str
    terskel_w: float


def teller_med(*, strategi: str, rolle: str, effekt_w: float | None) -> bool:
    """Om en kilde faktisk bidrar til tilgjengelig kutt akkurat nå.

    Tre ting må stemme: strategien må bruke rollen, sensoren må ha en lesbar
    verdi, og verdien må ligge over terskelen for rollen.
    """
    if effekt_w is None:
        return False
    if rolle not in ROLLER_PER_STRATEGI.get(strategi, frozenset()):
        return False
    return effekt_w > TERSKEL_PER_ROLLE[rolle]


def build_kutt_kilder(*, strategi: str, avlesninger: list[KildeAvlesning]) -> list[KuttKilde]:
    """Gjør avlesningene om til kutt_kilder-oppføringer.

    Alle konfigurerte kilder er med, også de strategien ikke bruker. Forskjellen
    mellom "finnes ikke" og "teller ikke nå" er nettopp det som er verdt å se.
    """
    return [
        KuttKilde(
            entity_id=a.entity_id,
            navn=a.navn,
            effekt_w=None if a.effekt_w is None else round(a.effekt_w, 1),
            teller_med=teller_med(strategi=strategi, rolle=a.rolle, effekt_w=a.effekt_w),
            rolle=a.rolle,
            terskel_w=TERSKEL_PER_ROLLE[a.rolle],
        )
        for a in avlesninger
    ]


def compute_tilgjengelig_kutt_kw(
    *,
    strategi: str,
    vvb_power_w: float | None,
    ekstra_power_w: list[float | None] | None = None,
) -> float:
    """Beregn realistisk tilgjengelig kutt i kW basert på valgt strategi.

    blind: antar BLIND_ASSUMED_KUTT_KW
    vvb_status: bruker faktisk VVB-effekt, kun over VVB_ACTIVE_THRESHOLD_W
    vvb_pluss_ekstra: VVB pluss sum av ekstra-sensorer over EKSTRA_SENSOR_ACTIVE_THRESHOLD_W

    Summen går over de samme kildene som får teller_med i kutt_kilder, så de to
    tallene kan ikke drifte fra hverandre. blind er unntaket: der er tilstanden
    en antagelse, ikke en sum av kilder.
    """
    if strategi == STRATEGI_BLIND:
        return BLIND_ASSUMED_KUTT_KW

    total_w = 0.0
    if vvb_power_w is not None and teller_med(strategi=strategi, rolle=ROLLE_VVB, effekt_w=vvb_power_w):
        total_w += vvb_power_w
    for p in ekstra_power_w or []:
        if p is not None and teller_med(strategi=strategi, rolle=ROLLE_EKSTRA, effekt_w=p):
            total_w += p
    return total_w / 1000.0


def is_coordinator_stale(
    *,
    last_successful_update: datetime | None,
    now: datetime,
) -> bool:
    """True hvis siste vellykkede oppdatering er eldre enn watchdog-terskel."""
    if last_successful_update is None:
        return True
    return (now - last_successful_update).total_seconds() > WATCHDOG_STALE_THRESHOLD_SECONDS
