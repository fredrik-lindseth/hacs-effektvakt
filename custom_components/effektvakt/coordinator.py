"""Coordinator for Effektvakt."""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util_module

from .avlesning import read_energy_kwh, read_friendly_name, read_power_kw, read_state_timestamp
from .const import (
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
    DEFAULT_AUTOMATIKK_AKTIV,
    DEFAULT_KUTT_STRATEGI,
    DEFAULT_MIN_RISIKO_FOR_KUTT,
    DEFAULT_RISIKO_HOLDETID_MINUTTER,
    DEFAULT_SAFETY_BUFFER_KW,
    DOMAIN,
    LEGACY_RISIKO_MAPPING,
    LEGACY_STRATEGI_MAPPING,
    RISIKO_GOD_MARGIN,
    RISIKO_LEVELS,
    STORAGE_VERSION,
    TICK_INTERVAL_BY_RISIKO,
    WATCHDOG_STALE_THRESHOLD_SECONDS,
)
from .dso import KAPASITETSTRINN_PER_DSO
from .hysterese import HystereseState, apply_hysteresis
from .laster import (
    ROLLE_EKSTRA,
    ROLLE_VVB,
    KildeAvlesning,
    build_kutt_kilder,
    compute_tilgjengelig_kutt_kw,
)
from .modell import (
    KOSTNAD_FELT_NAVN,
    beregn_resten_av_timen,
    beregn_terskel,
    beregn_topp_3_oversikt,
    classify_raw_risk,
    compute_elapsed_h,
    compute_kostnad,
    compute_projected_avg,
    vurder_kuttkriterium,
)
from .timeregnskap import Timeregnskap

if TYPE_CHECKING:
    from datetime import date

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def dt_util_now() -> datetime:
    """Wrapper for monkeypatch-vennlig now()."""
    na: datetime = dt_util_module.now()
    return na


def rund(verdi: float | None, *, desimaler: int = 3) -> float | None:
    """Avrund et kW-tall for data-dicten, og la None passere som None.

    None betyr «vet ikke» eller «finnes ikke» og skal ut som null i JSON, ikke
    som et tall noen kan regne videre på.
    """
    return None if verdi is None else round(verdi, desimaler)


class EffektvaktCoordinator(DataUpdateCoordinator):
    """Coordinator for Effektvakt."""

    # DataUpdateCoordinator eier feltet, men uten Home Assistant installert ser
    # ikke mypy basen, og et tildelt felt uten kjent type gjør oppslaget under
    # sirkulært. Annoteringen sier hva HA faktisk holder der.
    update_interval: timedelta | None

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=TICK_INTERVAL_BY_RISIKO[RISIKO_GOD_MARGIN]),
        )
        self.entry = entry
        self.power_sensor: str | None = entry.data.get(CONF_POWER_SENSOR)
        self.energy_sensor: str | None = entry.data.get(CONF_ENERGY_SENSOR)
        self.safety_buffer_kw: float = float(entry.data.get(CONF_SAFETY_BUFFER_KW, DEFAULT_SAFETY_BUFFER_KW))
        # Bakoverkompatibilitet for risiko-verdier: en config entry fra før
        # omdøpingen har "medium" lagret, og det er ikke lenger et nivå.
        min_risiko_raw = entry.data.get(CONF_MIN_RISIKO_FOR_KUTT, DEFAULT_MIN_RISIKO_FOR_KUTT)
        self.min_risiko_for_kutt: str = LEGACY_RISIKO_MAPPING.get(min_risiko_raw, min_risiko_raw)
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
        # Hovedbryteren eier denne, ikke beregningen. Den styrer bare om
        # automasjoner faar lov til aa kutte: sensorene regner videre uansett,
        # saa projeksjon, risiko og kostnad er like sanne med vakten av.
        self.automatikk_aktiv: bool = DEFAULT_AUTOMATIKK_AKTIV
        self._regnskap = Timeregnskap(current_month=dt_util_now().strftime("%Y-%m"))
        self._hysterese_state = HystereseState(nivå=RISIKO_GOD_MARGIN)
        self._last_successful_update: datetime | None = None
        self._store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}")
        self._store_loaded = False

    @property
    def _daily_max_kw(self) -> dict[date, float]:
        """Dagsmaksene, der reset-topp-3-tjenesten i __init__.py skriver dem tomme.

        Den siste delegasjonen til timeregnskapet. Resten av pakken går på
        `_regnskap` direkte; denne står til tjenesten får en egen metode å
        kalle framfor å sette et felt utenfra.
        """
        return self._regnskap.daily_max_kw

    @_daily_max_kw.setter
    def _daily_max_kw(self, verdi: dict[date, float]) -> None:
        self._regnskap.daily_max_kw = verdi

    # --- Store-I/O --------------------------------------------------------

    async def _load_stored_data(self) -> None:
        """Les regnskapet og hysteresen tilbake fra disk, én gang per oppstart."""
        if self._store_loaded:
            return
        stored = await self._store.async_load()
        self._store_loaded = True
        if not stored:
            return
        data = stored.get("data", {})
        self._regnskap = Timeregnskap.fra_lagring(data, now=dt_util_now())
        self._les_hysterese(data.get("hysterese_state", {}))

    def _les_hysterese(self, rå: object) -> None:
        """Sett hysterese-nivået fra lagring. Ukjente nivåer lar det ferske stå."""
        if not isinstance(rå, dict):
            return
        lagret_nivå = str(rå.get("nivå", ""))
        lagret_nivå = LEGACY_RISIKO_MAPPING.get(lagret_nivå, lagret_nivå)
        if lagret_nivå in RISIKO_LEVELS:
            self._hysterese_state.nivå = lagret_nivå

    async def _persist(self) -> None:
        """Skriv regnskapet og hysteresen til disk."""
        pending_since = self._hysterese_state.pending_since
        await self._store.async_save(
            {
                "data": {
                    **self._regnskap.til_lagring(),
                    "hysterese_state": {
                        "nivå": self._hysterese_state.nivå,
                        "pending_nivå": self._hysterese_state.pending_nivå,
                        "pending_since": None if pending_since is None else pending_since.isoformat(),
                    },
                }
            }
        )

    # --- ticket -----------------------------------------------------------

    async def _async_update_data(self) -> dict:
        await self._load_stored_data()
        now = dt_util_now()

        power_kw = read_power_kw(self.hass, self.power_sensor)
        current_kw = power_kw or 0.0
        energy_now = read_energy_kwh(self.hass, self.energy_sensor)

        self._regnskap.akkumuler(now=now, power_kw=power_kw)
        if energy_now is not None:
            self._regnskap.avstem_mot_maaler(
                energy_now=energy_now,
                now=now,
                maaler_ts_raa=read_state_timestamp(self.hass, self.energy_sensor, now=now),
            )
        # Månedsrulleringen kommer etter avstemmingen med vilje: en avlesning som
        # retter den siste timen i måneden skal telle med i topp-3-en som
        # arkiveres, ikke lande i den ferske måneden.
        self._regnskap.handle_month_rollover(now=now)

        avlesninger = self._les_kutt_kilder()
        vvb_power_w = next((a.effekt_w for a in avlesninger if a.rolle == ROLLE_VVB), None)
        ekstra_power_w_list = [a.effekt_w for a in avlesninger if a.rolle == ROLLE_EKSTRA]

        tilgjengelig_kutt_kw = compute_tilgjengelig_kutt_kw(
            strategi=self.kutt_strategi,
            vvb_power_w=vvb_power_w,
            ekstra_power_w=ekstra_power_w_list,
        )
        kutt_kilder = build_kutt_kilder(strategi=self.kutt_strategi, avlesninger=avlesninger)

        elapsed_h = compute_elapsed_h(now)
        projected_avg = compute_projected_avg(
            actual_kwh_this_hour=self._regnskap.current_hour_kwh,
            current_kw=current_kw,
            elapsed_h=elapsed_h,
        )

        terskel = beregn_terskel(
            trinn=self.kapasitetstrinn,
            daily_max_kw=self._regnskap.daily_max_kw,
            today=now.date(),
            projected_kw=projected_avg,
        )
        kriterium = vurder_kuttkriterium(
            trinn=self.kapasitetstrinn,
            daily_max_kw=self._regnskap.daily_max_kw,
            today=now.date(),
            projected_kw=projected_avg,
            actual_kwh_this_hour=self._regnskap.current_hour_kwh,
            elapsed_h=elapsed_h,
        )
        resten_av_timen = beregn_resten_av_timen(margin_kw=terskel.margin_kw, elapsed_h=elapsed_h)
        topp_3 = beregn_topp_3_oversikt(self._regnskap.daily_max_kw, today=now.date())
        rå = classify_raw_risk(
            margin_kw=terskel.margin_kw,
            safety_buffer_kw=self.safety_buffer_kw,
            timen_flytter_trinnet=kriterium.oppfylt,
        )
        apply_hysteresis(self._hysterese_state, rå_nivå=rå, now=now, holdetid=self.risiko_holdetid)

        new_interval = timedelta(seconds=TICK_INTERVAL_BY_RISIKO[self._hysterese_state.nivå])
        if self.update_interval != new_interval:
            self.update_interval = new_interval

        self._last_successful_update = now

        kostnad = compute_kostnad(
            trinn=self.kapasitetstrinn,
            daily_max_kw=self._regnskap.daily_max_kw,
            today=now.date(),
            projected_kw=projected_avg,
            forrige_maaned_topp_3_kw=self._regnskap.previous_month_top_3_snitt_kw,
        )
        # Nøklene er feltnavnene i KostnadInfo. Uten kjente kapasitetstrinn er de alle None.
        kostnad_felter: dict[str, object | None] = (
            asdict(kostnad) if kostnad is not None else dict.fromkeys(KOSTNAD_FELT_NAVN)
        )

        await self._persist()

        return {
            "projected_avg_kw": round(projected_avg, 3),
            "current_kw": round(current_kw, 3),
            "actual_kwh_this_hour": round(self._regnskap.current_hour_kwh, 3),
            "kwh_maalt_fra_minutt": self._regnskap.maalt_fra_minutt(),
            "elapsed_minutes_in_hour": int(elapsed_h * 60),
            "minutter_igjen_av_timen": resten_av_timen.minutter_igjen,
            "margin_kw": rund(terskel.margin_kw),
            "time_tak_kw": rund(terskel.time_tak_kw),
            "dagstak_kw": rund(terskel.dagstak_kw),
            "maal_terskel_kw": terskel.maal_terskel_kw,
            "maal_trinn_kr": terskel.maal_trinn_kr,
            "dagens_maks_kw": rund(terskel.dagens_maks_kw),
            "topp_2_andre_dager_kw": rund(terskel.topp_2_andre_dager_kw),
            "topp_3_snitt_denne_maned_kw": rund(terskel.minste_mulige_topp_3_kw),
            "kutt_anbefalt_kw": rund(terskel.kutt_anbefalt_kw),
            "kan_legge_paa_kw": rund(terskel.kan_legge_paa_kw),
            "kan_legge_paa_resten_av_timen_kw": rund(resten_av_timen.kan_legge_paa_resten_av_timen_kw),
            "topp_3_dager": [asdict(dag) for dag in topp_3.dager],
            "topp_3_inkluderer_i_dag": topp_3.i_dag_teller_med,
            "dag_som_ryker": None if topp_3.dag_som_ryker is None else asdict(topp_3.dag_som_ryker),
            "risiko_niva": self._hysterese_state.nivå,
            "raw_risiko_niva": rå,
            "timen_flytter_trinnet": kriterium.oppfylt,
            "varig_projeksjon_kw": round(kriterium.varig_projeksjon_kw, 3),
            "kortvarig_paaslag_kw": round(kriterium.kortvarig_paaslag_kw, 3),
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


def is_coordinator_stale(
    *,
    last_successful_update: datetime | None,
    now: datetime,
) -> bool:
    """True hvis siste vellykkede oppdatering er eldre enn watchdog-terskel."""
    if last_successful_update is None:
        return True
    return (now - last_successful_update).total_seconds() > WATCHDOG_STALE_THRESHOLD_SECONDS
