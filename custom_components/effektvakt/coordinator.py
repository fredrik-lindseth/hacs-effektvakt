"""Coordinator for Effektvakt."""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
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
    MAX_ENERGY_DELTA_KWH,
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
    beregn_terskel,
    classify_raw_risk,
    compute_elapsed_h,
    compute_kostnad,
    compute_projected_avg,
    top_n_average,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Trapesintegrasjonen antar at effekten mellom to tick lå et sted mellom de to
# avlesningene. Går det lenger enn dette, har HA vært nede eller stått fast, og
# den forrige avlesningen sier ingenting om tiden som gikk. Da er et hull i
# målingen et ærligere svar enn et anslag, og energimåleren fyller det ved neste
# avlesning. Ticket er 15 til 60 sekunder, så normal drift kommer aldri hit.
MAX_INTEGRATION_GAP_H = 5 / 60


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


def iso_eller_none(tid: datetime | None) -> str | None:
    """ISO-tekst for lagring, None når tiden mangler."""
    return None if tid is None else tid.isoformat()


def parse_stored_datetime(raw: object) -> datetime | None:
    """Les en lagret ISO-tid. None hvis den mangler eller ikke lar seg lese."""
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def hour_state_is_current(*, hour_start: datetime | None, now: datetime) -> bool:
    """Om en time-akkumulator som starter i hour_start hører til timen vi står i nå.

    Fire ting må stemme: timen må finnes, den kan ikke ligge i framtida, den kan
    ikke være en time eller mer gammel, og både klokketimen og utc-offseten må
    være de samme. Offseten skiller de to gangene klokka er 02 natta den settes
    tilbake, og aldersgrensen fanger nedetid på et helt antall døgn der
    klokketimen tilfeldigvis stemmer igjen.
    """
    if hour_start is None:
        return False
    if (hour_start.tzinfo is None) != (now.tzinfo is None):
        return False
    if not timedelta(0) <= now - hour_start < timedelta(hours=1):
        return False
    return (hour_start.hour, hour_start.utcoffset()) == (now.hour, now.utcoffset())


def timer_mellom(fra: datetime | None, til: datetime) -> float | None:
    """Timer fra `fra` til `til`, None når de to ikke lar seg sammenligne.

    En lagret tid uten tidssone kan ikke trekkes fra en tid med, og det skal
    ikke kaste midt i et tick.
    """
    if fra is None or (fra.tzinfo is None) != (til.tzinfo is None):
        return None
    return (til - fra).total_seconds() / 3600


@dataclass(frozen=True)
class IntegrertEnergi:
    """Energien mellom to tick, delt på timeskiftet hvis et ligger imellom."""

    foer_timeskiftet_kwh: float
    etter_timeskiftet_kwh: float


def er_maalehull(*, forrige_ts: datetime | None, na: datetime) -> bool:
    """Om det gikk for lang tid siden forrige tick til at effekten kan integreres over det."""
    timer = timer_mellom(forrige_ts, na)
    return timer is None or timer < 0 or timer > MAX_INTEGRATION_GAP_H


def integrer_effekt(
    *,
    forrige_ts: datetime | None,
    forrige_kw: float,
    na: datetime,
    na_kw: float,
    timeskifte: datetime | None,
) -> IntegrertEnergi:
    """Trapesintegrer effekten mellom forrige tick og dette.

    Tiden hentes fra tidsstemplene, ikke fra et antatt tickintervall, for ticket
    hopper over når HA har det travelt. Trapesregelen framfor å holde den forrige
    avlesningen: en last som slås av og på treffer like ofte før som etter
    avlesningen, og da er midtverdien uten systematisk slagside.

    Ligger `timeskifte` inni intervallet, interpoleres effekten ved skiftet og
    energien deles i to. Den delen som lå før skiftet hører til timen som nettopp
    ble ferdig, ikke til den nye.
    """
    timer = timer_mellom(forrige_ts, na)
    if forrige_ts is None or timer is None or timer <= 0 or timer > MAX_INTEGRATION_GAP_H:
        return IntegrertEnergi(foer_timeskiftet_kwh=0.0, etter_timeskiftet_kwh=0.0)
    if timeskifte is None or not forrige_ts < timeskifte <= na:
        return IntegrertEnergi(
            foer_timeskiftet_kwh=0.0,
            etter_timeskiftet_kwh=(forrige_kw + na_kw) / 2 * timer,
        )
    andel_foer = (timeskifte - forrige_ts).total_seconds() / (na - forrige_ts).total_seconds()
    kw_ved_skiftet = forrige_kw + (na_kw - forrige_kw) * andel_foer
    return IntegrertEnergi(
        foer_timeskiftet_kwh=(forrige_kw + kw_ved_skiftet) / 2 * timer * andel_foer,
        etter_timeskiftet_kwh=(kw_ved_skiftet + na_kw) / 2 * timer * (1 - andel_foer),
    )


def maalerdelta(*, energy_now: float, forrige_avlesning: float | None) -> float | None:
    """kWh siden forrige avlesning, None når måleren ikke kan leses som en fortsettelse.

    En total_increasing-måler kan ikke gå ned uten å ha blitt nullstilt eller
    byttet, og hopper den mer enn MAX_ENERGY_DELTA_KWH er avlesningen ikke til å
    stole på uansett. Begge deler betyr at kalleren må sette nytt anker framfor å
    tro på differansen.
    """
    if forrige_avlesning is None:
        return None
    delta = energy_now - forrige_avlesning
    if delta < 0 or delta > MAX_ENERGY_DELTA_KWH:
        return None
    return delta


@dataclass(frozen=True)
class Tidsandeler:
    """Hvor stor del av et måler-vindu som ligger i forrige og i denne timen.

    Summen kan være under 1. Da rekker vinduet lenger tilbake enn de to timene vi
    kan rette på, og resten hører til timer som alt er låst inn.
    """

    forrige_time: float
    denne_timen: float


def tidsandeler(
    *,
    fra: datetime | None,
    til: datetime,
    time_start: datetime,
    forrige_time_start: datetime | None,
) -> Tidsandeler:
    """Del vinduet mellom to måleravlesninger på timeskiftet i `time_start`.

    Uten et brukbart `fra` vet vi ikke hvilken tid avlesningen dekker, og da kan
    ingenting av den plasseres. Å legge alt på timen vi står i ville gjort tre
    døgn med nedetid om til en falsk topp i den timen HA kom opp igjen.

    Et vindu uten varighet er noe annet: der vet vi når, det gikk bare ingen tid,
    og da hører alt til timen `til` ligger i.
    """
    if fra is None or (fra.tzinfo is None) != (til.tzinfo is None):
        return Tidsandeler(forrige_time=0.0, denne_timen=0.0)
    if til <= fra:
        return Tidsandeler(forrige_time=0.0, denne_timen=1.0)
    total = (til - fra).total_seconds()
    denne = max(0.0, (til - max(fra, time_start)).total_seconds())
    forrige = 0.0
    if forrige_time_start is not None:
        # Den ventende timen varer én time. Har HA vært nede i dagevis, ligger
        # den langt bak time_start, og alt imellom hører til timer vi ikke kan
        # rette på.
        slutt = min(til, forrige_time_start + timedelta(hours=1))
        forrige = max(0.0, (slutt - max(fra, forrige_time_start)).total_seconds())
    return Tidsandeler(forrige_time=forrige / total, denne_timen=denne / total)


@dataclass(frozen=True)
class MaalerFordeling:
    """Hvordan en måleravlesning fordeler seg på timen før og timen nå."""

    forrige_time_kwh: float
    denne_timen_kwh: float


def fordel_maalerdelta(
    *,
    delta_kwh: float,
    estimat_forrige_time_kwh: float,
    estimat_denne_timen_kwh: float,
    andeler: Tidsandeler,
) -> MaalerFordeling:
    """Fordel en måleravlesning på de to timene vinduet dekker.

    Måleren sier hvor mye som gikk med, men ikke når. Det vet effektintegrasjonen,
    så kWh-en fordeles i samme forhold som anslaget mellom de to timene. Står
    anslaget på null, altså ingen effektsensor eller null forbruk, deles det
    heller på tid.

    Rekker vinduet lenger tilbake enn de to timene, skaleres kWh-en ned til den
    andelen av tiden vi faktisk kan plassere. Resten hører til timer som er låst,
    og å legge den på timen vi står i ville bygget en falsk topp.
    """
    i_vinduet = min(1.0, max(0.0, andeler.forrige_time + andeler.denne_timen))
    estimat_sum = estimat_forrige_time_kwh + estimat_denne_timen_kwh
    if estimat_sum > 0:
        plasserbar = delta_kwh * i_vinduet
        return MaalerFordeling(
            forrige_time_kwh=plasserbar * estimat_forrige_time_kwh / estimat_sum,
            denne_timen_kwh=plasserbar * estimat_denne_timen_kwh / estimat_sum,
        )
    return MaalerFordeling(
        forrige_time_kwh=delta_kwh * andeler.forrige_time,
        denne_timen_kwh=delta_kwh * andeler.denne_timen,
    )


def vektet_estimat(
    *,
    estimat_kwh: float,
    vindu_fra: datetime,
    vindu_til: datetime,
    estimat_til: datetime,
    dekket_fra: datetime | None,
) -> float:
    """Hvor tungt en time veier når en måleravlesning skal fordeles.

    Anslaget og måler-vinduet dekker sjelden nøyaktig den samme tiden: måleren
    rapporterte 10:00:13, mens integrasjonen har talt fram til ticket vårt et
    halvt minutt senere, og var HA nede i starten av timen mangler anslaget den
    biten helt. Vekten er derfor snitteffekten vi faktisk så, ganget med den
    tiden av vinduet som ligger i timen.

    Hva som skjedde i hullet vet vi ikke, men snitteffekten er det beste vi har å
    veie med, og totalen er det måleren som bestemmer uansett. Dette avgjør bare
    fordelingen mellom to timer.
    """
    if len({t.tzinfo is None for t in (vindu_fra, vindu_til, estimat_til)}) > 1:
        return estimat_kwh
    vindu = (vindu_til - vindu_fra).total_seconds()
    if vindu <= 0:
        return 0.0
    # Anslaget begynner der målingen begynte, ikke der vinduet begynte.
    start = vindu_fra
    if dekket_fra is not None and (dekket_fra.tzinfo is None) == (vindu_fra.tzinfo is None):
        start = max(vindu_fra, dekket_fra)
    spenn = (estimat_til - start).total_seconds()
    if spenn <= 0:
        return estimat_kwh
    return estimat_kwh * vindu / spenn


@dataclass
class VentendeTime:
    """En time som er låst inn, men som fortsatt kan rettes når måleren melder seg.

    `estimat_kwh` er den delen av `kwh` som er integrert effekt og ikke bekreftet
    av måleren. Kommer avlesningen som dekker timen, byttes nettopp den delen ut.
    `dekket_fra` sier hvor i timen anslaget begynner å gjelde, så en time som
    bare er delvis målt ikke veier for lett når avlesningen skal fordeles.
    `dagsmaks_foer` er dagsverdien slik den sto før timen ble lagt inn, så en
    retting nedover ikke blir stående og ligne på dagens topp.
    """

    hour_start: datetime
    kwh: float
    estimat_kwh: float
    dagsmaks_foer: float
    dekket_fra: datetime | None = None


def stored_float(rå: object, standard: float = 0.0) -> float:
    """Les et tall fra Store. Ugyldig innhold gir standardverdien framfor et kræsj."""
    try:
        verdi = float(rå)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return standard
    return verdi if math.isfinite(verdi) else standard


def les_ventende_time(rå: object) -> VentendeTime | None:
    """Les en ventende time tilbake fra Store. None hvis den ikke gir mening."""
    if not isinstance(rå, dict):
        return None
    hour_start = parse_stored_datetime(rå.get("hour_start"))
    if hour_start is None:
        return None
    return VentendeTime(
        hour_start=hour_start,
        kwh=stored_float(rå.get("kwh")),
        estimat_kwh=stored_float(rå.get("estimat_kwh")),
        dagsmaks_foer=stored_float(rå.get("dagsmaks_foer")),
        dekket_fra=parse_stored_datetime(rå.get("dekket_fra")),
    )


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
        self._daily_max_kw: dict[date, float] = {}
        self._current_month: str = dt_util_now().strftime("%Y-%m")
        self._current_hour_kwh: float = 0.0
        self._current_hour_start: datetime | None = None
        # Den delen av _current_hour_kwh som er integrert effekt og ikke bekreftet
        # av måleren. Neste avlesning bytter den ut, så de to aldri legges oppå
        # hverandre.
        self._estimert_siden_maaler_kwh: float = 0.0
        self._siste_maaler_kwh: float | None = None
        self._siste_maaler_ts: datetime | None = None
        self._siste_effekt_kw: float = 0.0
        self._siste_effekt_ts: datetime | None = None
        # Tidligste punktet i timen vi har sammenhengende data fra. Er den senere
        # enn timestart, mangler det måling i starten av timen, og da er
        # actual_kwh_this_hour et ufullstendig tall.
        self._dekket_fra: datetime | None = None
        self._ventende_time: VentendeTime | None = None
        self._previous_month_top_3_snitt_kw: float | None = None
        self._previous_month_name: str | None = None
        self._hysterese_state = HystereseState(nivå=RISIKO_GOD_MARGIN)
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
        self._current_month = str(data.get("current_month") or self._current_month)
        self._current_hour_kwh = stored_float(data.get("current_hour_kwh"))
        # Uten timen den hører til er kWh-en ubrukelig. Da lar vi den stå, og
        # første tick forkaster den fordi timen ikke stemmer.
        self._current_hour_start = parse_stored_datetime(data.get("current_hour_start"))
        self._estimert_siden_maaler_kwh = stored_float(data.get("estimert_siden_maaler_kwh"))
        self._siste_maaler_kwh = self._les_siste_maalerstand(data)
        self._siste_maaler_ts = parse_stored_datetime(data.get("siste_maaler_ts"))
        if self._siste_maaler_ts is None and "siste_maaler_kwh" not in data:
            # Lagring fra før avstemmingen har ingen tid å måle standen mot.
            # Den hørte til timen som var i gang, så timestart er det nærmeste
            # vi kommer, og bedre enn å kaste den første avlesningen etter
            # oppgraderingen.
            self._siste_maaler_ts = self._current_hour_start
        self._siste_effekt_kw = stored_float(data.get("siste_effekt_kw"))
        self._siste_effekt_ts = parse_stored_datetime(data.get("siste_effekt_ts"))
        self._dekket_fra = parse_stored_datetime(data.get("dekket_fra"))
        self._ventende_time = les_ventende_time(data.get("ventende_time"))
        self._previous_month_top_3_snitt_kw = data.get("previous_month_top_3_snitt_kw")
        self._previous_month_name = data.get("previous_month_name")
        hyst = data.get("hysterese_state", {})
        lagret_nivå = str(hyst.get("nivå", ""))
        lagret_nivå = LEGACY_RISIKO_MAPPING.get(lagret_nivå, lagret_nivå)
        if lagret_nivå in RISIKO_LEVELS:
            self._hysterese_state.nivå = lagret_nivå

    def _les_siste_maalerstand(self, data: dict) -> float | None:
        """Siste godtatte målerstand fra Store.

        Lagring fra før avstemmingen kjente bare `energy_at_hour_start`, altså
        målerstanden timen startet på. Den pluss det timen hadde talt opp er den
        samme avlesningen, så en oppgradering midt i en time mister ingenting.
        """
        if "siste_maaler_kwh" in data:
            rå = data.get("siste_maaler_kwh")
            return None if rå is None else stored_float(rå)
        gammel = data.get("energy_at_hour_start")
        if gammel is None:
            return None
        return stored_float(gammel) + self._current_hour_kwh

    async def _persist(self) -> None:
        hour_start = self._current_hour_start
        ventende = self._ventende_time
        await self._store.async_save(
            {
                "data": {
                    "current_month": self._current_month,
                    "daily_max_kw": {d.isoformat(): kw for d, kw in self._daily_max_kw.items()},
                    "current_hour_kwh": self._current_hour_kwh,
                    "current_hour_start": hour_start.isoformat() if hour_start else None,
                    "estimert_siden_maaler_kwh": self._estimert_siden_maaler_kwh,
                    "siste_maaler_kwh": self._siste_maaler_kwh,
                    "siste_maaler_ts": iso_eller_none(self._siste_maaler_ts),
                    "siste_effekt_kw": self._siste_effekt_kw,
                    "siste_effekt_ts": iso_eller_none(self._siste_effekt_ts),
                    "dekket_fra": iso_eller_none(self._dekket_fra),
                    "ventende_time": (
                        None
                        if ventende is None
                        else {
                            "hour_start": ventende.hour_start.isoformat(),
                            "kwh": ventende.kwh,
                            "estimat_kwh": ventende.estimat_kwh,
                            "dagsmaks_foer": ventende.dagsmaks_foer,
                            "dekket_fra": iso_eller_none(ventende.dekket_fra),
                        }
                    ),
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

        power_kw = read_power_kw(self.hass, self.power_sensor)
        current_kw = power_kw or 0.0
        energy_now = read_energy_kwh(self.hass, self.energy_sensor)

        self._akkumuler_time(now=now, power_kw=power_kw)
        if energy_now is not None:
            self._avstem_mot_maaler(energy_now=energy_now, now=now)

        # Månedsrulleringen kommer etter avstemmingen med vilje: en avlesning som
        # retter den siste timen i måneden skal telle med i topp-3-en som
        # arkiveres, ikke lande i den ferske måneden.
        month_str = now.strftime("%Y-%m")
        if month_str != self._current_month:
            self._handle_month_rollover()
            self._current_month = month_str

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
            actual_kwh_this_hour=self._current_hour_kwh,
            current_kw=current_kw,
            elapsed_h=elapsed_h,
        )

        terskel = beregn_terskel(
            trinn=self.kapasitetstrinn,
            daily_max_kw=self._daily_max_kw,
            today=now.date(),
            projected_kw=projected_avg,
        )
        rå = classify_raw_risk(margin_kw=terskel.margin_kw, safety_buffer_kw=self.safety_buffer_kw)
        apply_hysteresis(self._hysterese_state, rå_nivå=rå, now=now, holdetid=self.risiko_holdetid)

        new_interval = timedelta(seconds=TICK_INTERVAL_BY_RISIKO[self._hysterese_state.nivå])
        if self.update_interval != new_interval:
            self.update_interval = new_interval

        self._last_successful_update = now

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
            "kwh_maalt_fra_minutt": self._maalt_fra_minutt(),
            "elapsed_minutes_in_hour": int(elapsed_h * 60),
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

    def _akkumuler_time(self, *, now: datetime, power_kw: float | None) -> None:
        """Flytt time-akkumulatoren fram til nå, og lås inn timen hvis et timeskifte er passert.

        Energien mellom to tick kommer fra effektintegrasjonen. Det er den som
        gjør at `actual_kwh_this_hour` følger forbruket også mens en AMS-måler
        som bare rapporterer hver time står stille, og `_avstem_mot_maaler`
        bytter anslaget ut med måleren når den melder seg.

        Tilstanden kan komme rett fra disk, og da er dette første tick etter en
        omstart. Hører den til timen vi står i, fortsetter vi der forrige tick
        slapp. Ellers låses den gamle timen inn før vi begynner på en ny, og den
        delen av tiden som lå før timeskiftet følger med over til den gamle.
        """
        time_start = now.replace(minute=0, second=0, microsecond=0)
        ny_time = not hour_state_is_current(hour_start=self._current_hour_start, now=now)
        hull = power_kw is None or er_maalehull(forrige_ts=self._siste_effekt_ts, na=now)

        integrert = IntegrertEnergi(foer_timeskiftet_kwh=0.0, etter_timeskiftet_kwh=0.0)
        if power_kw is not None:
            integrert = integrer_effekt(
                forrige_ts=self._siste_effekt_ts,
                forrige_kw=self._siste_effekt_kw,
                na=now,
                na_kw=power_kw,
                timeskifte=time_start if ny_time else None,
            )

        if ny_time:
            self._current_hour_kwh += integrert.foer_timeskiftet_kwh
            self._estimert_siden_maaler_kwh += integrert.foer_timeskiftet_kwh
            self._finalize_hour()
            self._current_hour_start = time_start
            self._current_hour_kwh = integrert.etter_timeskiftet_kwh
            self._estimert_siden_maaler_kwh = integrert.etter_timeskiftet_kwh
            self._dekket_fra = now if hull else time_start
        else:
            self._current_hour_kwh += integrert.etter_timeskiftet_kwh
            self._estimert_siden_maaler_kwh += integrert.etter_timeskiftet_kwh
            if hull or self._dekket_fra is None:
                self._dekket_fra = now

        if power_kw is None:
            # Uten en lesbar effekt vet vi ikke hva som skjedde, og et anker
            # herfra ville latt neste tick integrere over et hull vi ikke så.
            self._siste_effekt_ts = None
        else:
            self._siste_effekt_ts = now
            self._siste_effekt_kw = power_kw

    def _avstem_mot_maaler(self, *, energy_now: float, now: datetime) -> None:
        """La energimåleren overstyre det integrerte anslaget for tiden den dekker.

        Måleren er den nøyaktige kilden, så den skal vinne. Den legges likevel
        ikke oppå anslaget: kWh-en siden forrige avlesning erstatter nettopp den
        delen av timen som var estimert, og telles derfor aldri to ganger.

        Står måleren stille, er det ingenting å avstemme og anslaget får stå.
        Det er dette som skiller en måler som har null forbruk fra en som bare
        ikke har rapportert ennå, og vi kan ikke se forskjell på dem.
        """
        time_start = self._current_hour_start
        if time_start is None:
            return
        maaler_ts = self._maaler_tidspunkt(now=now)
        delta = maalerdelta(energy_now=energy_now, forrige_avlesning=self._siste_maaler_kwh)
        vindu_fra = self._siste_maaler_ts
        if delta is None or vindu_fra is None or timer_mellom(vindu_fra, now) is None:
            # Første avlesning, nullstilt eller byttet måler, eller en stand uten
            # et tidspunkt å måle den mot. Det som alt er målt denne timen
            # beholdes, og tellingen fortsetter fra den nye standen.
            self._siste_maaler_kwh = energy_now
            self._siste_maaler_ts = maaler_ts
            self._estimert_siden_maaler_kwh = 0.0
            if self._ventende_time is not None:
                self._ventende_time.estimat_kwh = 0.0
            return
        if delta == 0:
            return

        ventende = self._ventende_time
        fordeling = fordel_maalerdelta(
            delta_kwh=delta,
            estimat_forrige_time_kwh=self._vekt_forrige_time(vindu_fra=vindu_fra, vindu_til=maaler_ts),
            estimat_denne_timen_kwh=vektet_estimat(
                estimat_kwh=self._estimert_siden_maaler_kwh,
                vindu_fra=max(vindu_fra, time_start),
                vindu_til=maaler_ts,
                estimat_til=now,
                dekket_fra=self._dekket_fra,
            ),
            andeler=tidsandeler(
                fra=vindu_fra,
                til=maaler_ts,
                time_start=time_start,
                forrige_time_start=ventende.hour_start if ventende else None,
            ),
        )
        self._current_hour_kwh = max(
            0.0,
            self._current_hour_kwh - self._estimert_siden_maaler_kwh + fordeling.denne_timen_kwh,
        )
        if ventende is not None:
            ventende.kwh = max(0.0, ventende.kwh - ventende.estimat_kwh + fordeling.forrige_time_kwh)
            ventende.estimat_kwh = 0.0
            self._laas_inn_time(ventende)
            # Måleren har nå bekreftet tiden forbi timeskiftet, så timen før er
            # gjort opp og kan ikke ta imot mer.
            self._ventende_time = None

        self._utvid_dekning(fra=vindu_fra, time_start=time_start)
        self._estimert_siden_maaler_kwh = 0.0
        self._siste_maaler_kwh = energy_now
        self._siste_maaler_ts = maaler_ts

    def _vekt_forrige_time(self, *, vindu_fra: datetime, vindu_til: datetime) -> float:
        """Hvor tungt den ventende timen veier når måleravlesningen skal fordeles.

        Bare den delen av vinduet som ligger inni den timen teller, og anslaget
        skaleres opp hvis vi bare målte en del av den.
        """
        ventende = self._ventende_time
        if ventende is None:
            return 0.0
        time_slutt = ventende.hour_start + timedelta(hours=1)
        return vektet_estimat(
            estimat_kwh=ventende.estimat_kwh,
            vindu_fra=max(vindu_fra, ventende.hour_start),
            vindu_til=min(vindu_til, time_slutt),
            estimat_til=time_slutt,
            dekket_fra=ventende.dekket_fra,
        )

    def _maaler_tidspunkt(self, *, now: datetime) -> datetime:
        """Når måleren sist meldte en ny verdi, klemt inn i vinduet vi kan bruke.

        Er tidsstempelet ubrukelig, altså borte, i framtida eller eldre enn den
        forrige avlesningen vår, faller vi tilbake på tidspunktet for ticket.
        """
        ts = read_state_timestamp(self.hass, self.energy_sensor, now=now)
        if ts is None or ts > now:
            return now
        if self._siste_maaler_ts is not None:
            forrige = self._siste_maaler_ts
            if (forrige.tzinfo is None) != (ts.tzinfo is None) or ts < forrige:
                return now
        return ts

    def _utvid_dekning(self, *, fra: datetime | None, time_start: datetime) -> None:
        """En måleravlesning dekker tiden helt tilbake til forrige avlesning.

        Hull som lå i det vinduet er dermed fylt igjen, så lenge vinduet henger
        sammen med den dekningen vi alt har.
        """
        if fra is None or self._dekket_fra is None:
            return
        if (fra.tzinfo is None) != (self._dekket_fra.tzinfo is None):
            return
        if fra <= self._dekket_fra:
            self._dekket_fra = max(time_start, fra)

    def _maalt_fra_minutt(self) -> int:
        """Hvilket minutt av timen vi har sammenhengende måling fra.

        Null i normal drift. Over null betyr at `actual_kwh_this_hour` mangler
        starten av timen og at projeksjonen er for lav, typisk fordi
        integrasjonen ble satt opp midt i en time eller fordi HA var nede uten at
        energimåleren har rapportert siden.
        """
        if self._dekket_fra is None or self._current_hour_start is None:
            return 0
        timer = timer_mellom(self._current_hour_start, self._dekket_fra)
        if timer is None:
            return 0
        return max(0, round(timer * 60))

    def _finalize_hour(self) -> None:
        """Lås timen som er ferdig inn i daily_max_kw og nullstill akkumulatoren.

        Timen legges inn med det vi vet nå, men den holdes samtidig åpen for
        retting. En AMS-måler rapporterer gjerne 10:00:13, altså etter at timen
        er over, og den kWh-en hører til timen før. Kommer den avlesningen,
        bytter `_avstem_mot_maaler` ut den estimerte delen av timen og låser den
        inn på nytt.

        Dagsverdien settes med max mot det dagen alt hadde, så en omstart som
        kjører denne på nytt for en time som alt er låst inn kan ikke telle
        dobbelt. Mangler _current_hour_start, vet vi ikke hvilken dag kWh-en
        hører til, og da forkastes den framfor å havne på feil dag.
        """
        hour_start = self._current_hour_start
        if hour_start is None:
            self._ventende_time = None
        else:
            self._ventende_time = VentendeTime(
                hour_start=hour_start,
                kwh=self._current_hour_kwh,
                estimat_kwh=self._estimert_siden_maaler_kwh,
                dagsmaks_foer=self._daily_max_kw.get(hour_start.date(), 0.0),
                dekket_fra=self._dekket_fra,
            )
            self._laas_inn_time(self._ventende_time)
        self._current_hour_kwh = 0.0
        self._estimert_siden_maaler_kwh = 0.0

    def _laas_inn_time(self, time: VentendeTime) -> None:
        """Skriv timen inn som dagsmaks hvis den er høyere enn det dagen alt hadde."""
        hoyeste = max(time.dagsmaks_foer, round(time.kwh, 3))
        if hoyeste > 0:
            self._daily_max_kw[time.hour_start.date()] = hoyeste

    def _handle_month_rollover(self) -> None:
        topp_3 = top_n_average(self._daily_max_kw, n=3)
        if topp_3 is not None:
            self._previous_month_top_3_snitt_kw = round(topp_3, 3)
            self._previous_month_name = self._current_month
        self._daily_max_kw = {}
        # Dagsverdiene er arkivert. En retting av den siste timen i forrige måned
        # ville bare lagt dagen tilbake i en måned som er gjort opp.
        self._ventende_time = None


def is_coordinator_stale(
    *,
    last_successful_update: datetime | None,
    now: datetime,
) -> bool:
    """True hvis siste vellykkede oppdatering er eldre enn watchdog-terskel."""
    if last_successful_update is None:
        return True
    return (now - last_successful_update).total_seconds() > WATCHDOG_STALE_THRESHOLD_SECONDS
