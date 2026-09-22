"""Minuttoppløste scenarier: hva som skjer tidlig i timen, og hva som ikke skjer.

Replay-fixturene i `test_coordinator_replay.py` er timeoppløste. De ser hele
timer som ferdige tall og kan derfor ikke se det denne filen handler om: at
projeksjonen tidlig i timen nesten bare er den øyeblikkelige effekten, og at en
vannkoker der ser ut som en time langt over terskelen.

Scenariene kjører den ekte coordinatoren minutt for minutt med en falsk klokke,
og leser anbefalingen gjennom den ekte binærsensoren.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given
from hypothesis import strategies as st

from custom_components.effektvakt.binary_sensor import EffektvaktKuttNedAnbefaltBinarySensor
from custom_components.effektvakt.const import KORTVARIG_LAST_KW, RISIKO_LIKE_UNDER
from custom_components.effektvakt.coordinator import EffektvaktCoordinator
from custom_components.effektvakt.modell import (
    beregn_terskel,
    classify_raw_risk,
    kortvarig_paaslag_kw,
    vurder_kuttkriterium,
)
from tests.conftest import make_entry, make_hass_with_states, make_state

# To andre dager på 5,0 kW gir topp-3-skranke 3,33 kW, altså BKK-trinnet med
# terskel 5,0 kW som mål. Dagstaket blir 3 x 5 minus 10, som også er 5,0, så
# timen vi står i måles mot nøyaktig 5,0 kW. Det er tallet i saken.
ANDRE_DAGER = {date(2026, 6, 10): 5.0, date(2026, 6, 11): 5.0}
I_DAG = date(2026, 6, 15)
TAK_KW = 5.0

# Fredriks bereder. Det er denne som må rekke å hente inn en overskridelse når
# kortvarig-fradraget endelig slipper taket.
KUTTBAR_LAST_KW = 2.0


@dataclass(frozen=True)
class Avlesning:
    """Ett tick: tidspunktet, coordinator-dataene og hva binærsensoren sa."""

    tid: datetime
    data: dict
    kutt_anbefalt: bool

    @property
    def minutt(self) -> int:
        return self.tid.minute


class Doegn:
    """Driver coordinatoren minutt for minutt med en effektsensor vi styrer."""

    def __init__(self, **entry_overrides) -> None:
        self._states: dict[str, object] = {"sensor.power": make_state("0", unit="W")}
        # Uten energisensor er timeregnskapet ren trapesintegrasjon av effekten,
        # som er det scenariene handler om.
        entry = make_entry(energy_sensor=None, **entry_overrides)
        with patch("custom_components.effektvakt.coordinator.Store"):
            self.coord = EffektvaktCoordinator(make_hass_with_states(self._states), entry)
        self.coord._store = MagicMock()
        self.coord._store.async_load = AsyncMock(return_value=None)
        self.coord._store.async_save = AsyncMock()
        self.coord._regnskap.daily_max_kw = dict(ANDRE_DAGER)
        self._binaer = EffektvaktKuttNedAnbefaltBinarySensor(self.coord)

    async def kjor(self, *, fra: datetime, minutter: int, effekt_kw) -> list[Avlesning]:
        """Kjør ett tick i minuttet. `effekt_kw` er kW eller en funksjon av tiden."""
        avlesninger = []
        for i in range(minutter):
            na = fra + timedelta(minutes=i)
            kw = effekt_kw(na) if callable(effekt_kw) else effekt_kw
            self._states["sensor.power"] = make_state(str(kw * 1000), unit="W")
            with patch("custom_components.effektvakt.coordinator.dt_util_now", return_value=na):
                data = await self.coord._async_update_data()
            self.coord.data = data
            avlesninger.append(Avlesning(tid=na, data=data, kutt_anbefalt=bool(self._binaer.is_on)))
        return avlesninger


def _forste_kutt(avlesninger: list[Avlesning]) -> Avlesning | None:
    return next((a for a in avlesninger if a.kutt_anbefalt), None)


# --- Selve kriteriet ------------------------------------------------------


def test_fradraget_krymper_mot_null_utover_i_timen():
    assert kortvarig_paaslag_kw(elapsed_h=0.0) == pytest.approx(KORTVARIG_LAST_KW)
    assert kortvarig_paaslag_kw(elapsed_h=0.5) == pytest.approx(KORTVARIG_LAST_KW / 2)
    assert kortvarig_paaslag_kw(elapsed_h=1.0) == pytest.approx(0.0)


def test_fradraget_tar_oss_aldri_under_det_timen_alt_har_brukt():
    """Kilowattimene som er brukt kan ikke kuttes bort igjen.

    Ved minutt 54 med 5,2 kWh på boken er timen over taket uansett hva
    effekten gjør nå, og fradraget skal ikke late som noe annet.
    """
    kriterium = vurder_kuttkriterium(
        trinn=[(2.0, 155), (5.0, 250), (10.0, 415)],
        daily_max_kw=ANDRE_DAGER,
        today=I_DAG,
        projected_kw=5.2,
        actual_kwh_this_hour=5.2,
        elapsed_h=0.9,
    )
    assert kriterium.varig_projeksjon_kw == pytest.approx(5.2)
    assert kriterium.oppfylt is True


BKK = [
    (2.0, 155),
    (5.0, 250),
    (10.0, 415),
    (15.0, 600),
    (20.0, 770),
    (25.0, 940),
    (50.0, 1800),
    (75.0, 2650),
    (100.0, 3500),
    (float("inf"), 6900),
]


@given(
    andre=st.lists(st.floats(min_value=0.0, max_value=25.0, allow_nan=False), min_size=0, max_size=5),
    dagens_maks=st.floats(min_value=0.0, max_value=25.0, allow_nan=False),
    projisert=st.floats(min_value=0.0, max_value=30.0, allow_nan=False),
    brukt_kwh=st.floats(min_value=0.0, max_value=30.0, allow_nan=False),
    elapsed_h=st.floats(min_value=0.0, max_value=0.999, allow_nan=False),
    buffer_kw=st.floats(min_value=0.1, max_value=3.0, allow_nan=False),
)
def test_like_under_terskel_kan_ikke_oppstaa_som_raa_nivaa(
    andre: list[float],
    dagens_maks: float,
    projisert: float,
    brukt_kwh: float,
    elapsed_h: float,
    buffer_kw: float,
):
    """Konsekvensen av at kriteriet gater de to øverste nivåene.

    Kriteriet er oppfylt bare når den varige projeksjonen alt ligger over taket,
    og den er aldri høyere enn projeksjonen selv. Da er marginen negativ, og
    nivået `over_terskel`. Er kriteriet ikke oppfylt, settes nivået ned til
    `naermer_seg_terskel`. `like_under_terskel` blir dermed liggende igjen i
    RISIKO_LEVELS uten å kunne oppstå her.

    Verdien lever videre i sensoren: hysteresen går innom den på vei ned fra
    `over_terskel`, og `min_risiko_for_kutt` kan fortsatt stå på den. Testen
    står så neste endring i kriteriet ikke gjør dette stille om igjen.
    """
    i_dag = date(2026, 6, 20)
    daily = {date(2026, 6, 1 + i): kw for i, kw in enumerate(andre)}
    daily[i_dag] = dagens_maks

    terskel = beregn_terskel(trinn=BKK, daily_max_kw=daily, today=i_dag, projected_kw=projisert)
    kriterium = vurder_kuttkriterium(
        trinn=BKK,
        daily_max_kw=daily,
        today=i_dag,
        projected_kw=projisert,
        actual_kwh_this_hour=min(brukt_kwh, projisert),
        elapsed_h=elapsed_h,
    )
    nivå = classify_raw_risk(
        margin_kw=terskel.margin_kw,
        safety_buffer_kw=buffer_kw,
        timen_flytter_trinnet=kriterium.oppfylt,
    )
    assert nivå != RISIKO_LIKE_UNDER
    if kriterium.oppfylt:
        assert terskel.margin_kw is not None and terskel.margin_kw < 0


def test_ukjent_nettselskap_gir_ingen_kuttgrunn():
    kriterium = vurder_kuttkriterium(
        trinn=[],
        daily_max_kw=ANDRE_DAGER,
        today=I_DAG,
        projected_kw=50.0,
        actual_kwh_this_hour=0.0,
        elapsed_h=0.5,
    )
    assert kriterium.oppfylt is False


# --- Vannkokeren ----------------------------------------------------------


@pytest.mark.asyncio
async def test_vannkoker_tidlig_i_timen_utloser_ikke_kutt():
    """Saken selv: 3,5 kW grunnlast, vannkoker på 2 kW fra minutt 2 til 6.

    Projeksjonen spretter over 5 kW og blir der så lenge kokeren går, men timen
    ender på 3,6 kW. Den skal ikke koste noen last.
    """
    doegn = Doegn()

    def effekt(na: datetime) -> float:
        return 5.5 if 2 <= na.minute < 6 else 3.5

    avlesninger = await doegn.kjor(fra=datetime(2026, 6, 15, 14, 0), minutter=20, effekt_kw=effekt)

    mens_kokeren_gaar = [a for a in avlesninger if 2 <= a.minutt < 6]
    # Uten kriteriet ville dette vært over_terskel og kutt: projeksjonen ligger
    # over taket i hvert eneste av de fire minuttene.
    assert all(a.data["margin_kw"] < 0 for a in mens_kokeren_gaar)

    assert _forste_kutt(avlesninger) is None
    assert not any(a.data["timen_flytter_trinnet"] for a in avlesninger)
    # Og timen endte der den skulle, langt under taket.
    assert avlesninger[-1].data["actual_kwh_this_hour"] < 1.5


# --- Motsatt feil: varselet skal ikke komme for sent ----------------------


@pytest.mark.asyncio
async def test_klar_overlast_kuttes_med_en_gang():
    """7,5 kW fra timestart er ingen vannkoker. Der skal varselet komme straks."""
    doegn = Doegn()
    avlesninger = await doegn.kjor(fra=datetime(2026, 6, 15, 14, 0), minutter=10, effekt_kw=7.5)

    assert avlesninger[0].kutt_anbefalt is True


@pytest.mark.asyncio
async def test_moderat_overlast_kuttes_mens_kuttet_fortsatt_rekker():
    """6,0 kW mot et tak på 5,0 er for lite til å kalles med en gang.

    Poenget er at ventingen er avgrenset: når fradraget slipper taket, er det
    fortsatt nok av timen igjen til at berederen på 2 kW henter inn hele
    overskridelsen.
    """
    doegn = Doegn()
    avlesninger = await doegn.kjor(fra=datetime(2026, 6, 15, 14, 0), minutter=45, effekt_kw=6.0)

    kutt = _forste_kutt(avlesninger)
    assert kutt is not None, "moderat overlast må kuttes før timen er omme"
    assert 15 <= kutt.minutt <= 25

    rest_av_timen = 1 - kutt.minutt / 60
    etter_kutt = kutt.data["projected_avg_kw"] - KUTTBAR_LAST_KW * rest_av_timen
    assert etter_kutt <= TAK_KW


# --- 51ie: yo-yo over timeskiftet ----------------------------------------


@pytest.mark.asyncio
async def test_bereder_som_varmer_opp_igjen_etter_timeskiftet_kuttes_ikke_paa_nytt():
    """Yo-yo-scenariet fra hacs-effektvakt-51ie.

    Grunnlast 3,6 kW. Berederen på 2 kW drar 18-timen mot taket og kuttes.
    Blueprintet slipper den ved timeskiftet, og den begynner å varme igjen
    19:05. Den nye timen ser like dramatisk ut som den forrige, men den ender
    på 4,6 kW og koster ingenting, så den skal ikke kuttes på nytt.
    """
    doegn = Doegn()

    def effekt(na: datetime) -> float:
        if na.hour == 18:
            return 5.6 if na.minute < 40 else 3.6
        return 5.6 if 5 <= na.minute < 35 else 3.6

    time_18 = await doegn.kjor(fra=datetime(2026, 6, 15, 18, 0), minutter=60, effekt_kw=effekt)
    time_19 = await doegn.kjor(fra=datetime(2026, 6, 15, 19, 0), minutter=60, effekt_kw=effekt)

    assert time_18[40].kutt_anbefalt is True, "berederen skal være kuttet 18:40"

    oppvarming = [a for a in time_19 if 5 <= a.minutt < 35]
    # Den nye timen ser like ille ut som den forrige på projeksjonen.
    assert any(a.data["margin_kw"] < 0 for a in oppvarming)
    # Men den koster ingenting, så ingen ny runde av og på.
    assert _forste_kutt(time_19) is None
    assert time_19[-1].data["actual_kwh_this_hour"] < TAK_KW
