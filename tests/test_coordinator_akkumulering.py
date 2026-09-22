"""Tester for at timen akkumuleres riktig også når energimåleren står stille.

Feilen disse dekker: `actual_kwh_this_hour` ble bygget utelukkende av differanser
på energi-sensoren. På et vanlig norsk AMS-oppsett rapporterer HAN-avleseren én
gang i timen, ved timeskiftet, mens effekt-sensoren oppdaterer hvert par
sekunder. Da sto timen på 0,000 hele veien og projeksjonen kollapset mot null
nettopp når timen var i ferd med å låses inn. Den samme timingen slo motsatt vei
også: kWh-en som kom 13 sekunder etter timeskiftet ble lagt på den nye timen.

Testene her kjører coordinatoren tick for tick mot et simulert anlegg, så
måleren rapporterer på sin egen rytme og effekten varierer gjennom timen.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.effektvakt.coordinator import (
    EffektvaktCoordinator,
    Tidsandeler,
    fordel_maalerdelta,
    integrer_effekt,
    tidsandeler,
)
from tests.conftest import make_entry, make_hass_with_states, make_state

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

NOW_PATH = "custom_components.effektvakt.coordinator.dt_util_now"

DAGEN = date(2026, 9, 22)
MAALERSTAND_START = 135862.686


def effektprofil(t: datetime) -> float:
    """Effekten i kW gjennom Fredriks morgen 22. september, time for time.

    Grunnlasten er huset, toppene er varmtvannsbereder og stekeovn. Timene
    summerer seg til 0,93, 1,53 og 3,52 kWh, som er det måleren faktisk
    rapporterte den morgenen.
    """
    minutt = t.minute + t.second / 60
    if t.hour == 6:
        return 0.6 + (1.98 if 10 <= minutt < 20 else 0.0)
    if t.hour == 7:
        return 0.78 + (2.25 if 20 <= minutt < 40 else 0.0)
    if t.hour == 8:
        return 1.04 + (4.96 if 15 <= minutt < 45 else 0.0)
    return 0.7


FASIT_KWH = {6: 0.93, 7: 1.53, 8: 3.52}


class Anlegg:
    """Simulert anlegg: effekt som varierer, og en måler med sin egen rytme.

    Målerstanden regnes ut sekund for sekund fra effektprofilen, så den er den
    samme energien coordinatoren skal komme fram til på egen hånd.
    """

    def __init__(
        self,
        *,
        start: datetime,
        slutt: datetime,
        effekt_kw: Callable[[datetime], float],
        rapporttider: Iterable[datetime] = (),
        maalerstand: float = MAALERSTAND_START,
    ) -> None:
        self.start = start
        self.effekt_kw = effekt_kw
        self._kum = [0.0]
        for i in range(int((slutt - start).total_seconds()) + 1):
            self._kum.append(self._kum[-1] + effekt_kw(start + timedelta(seconds=i)) / 3600)
        self._maalerstand_start = maalerstand
        self._rapporter = sorted(rapporttider)
        self.siste_rapport = start
        self.rapportert_verdi = round(maalerstand, 3)

    def maalerstand(self, t: datetime) -> float:
        return self._maalerstand_start + self._kum[int((t - self.start).total_seconds())]

    def kwh_mellom(self, fra: datetime, til: datetime) -> float:
        return self.maalerstand(til) - self.maalerstand(fra)

    def oppdater(self, t: datetime) -> None:
        """Slipp gjennom rapportene som har falt fram til nå."""
        while self._rapporter and self._rapporter[0] <= t:
            rapport = self._rapporter.pop(0)
            self.siste_rapport = rapport
            self.rapportert_verdi = round(self.maalerstand(rapport), 3)


def timesrapporter(*, fra: datetime, til: datetime, sekund: int = 13) -> list[datetime]:
    """Tidspunktene en AMS-måler som bare rapporterer ved timeskiftet melder seg."""
    tider = []
    t = fra.replace(minute=0, second=sekund, microsecond=0)
    while t <= til:
        if t >= fra:
            tider.append(t)
        t += timedelta(hours=1)
    return tider


def _make_coordinator(now: datetime, *, energy_sensor: str | None = "sensor.energy") -> EffektvaktCoordinator:
    with (
        patch("custom_components.effektvakt.coordinator.Store"),
        patch(NOW_PATH, return_value=now),
    ):
        coord = EffektvaktCoordinator(make_hass_with_states({}), make_entry(energy_sensor=energy_sensor))
    coord._store = MagicMock()
    coord._store.async_load = AsyncMock(return_value=None)
    coord._store.async_save = AsyncMock()
    return coord


async def kjor(
    coord: EffektvaktCoordinator,
    anlegg: Anlegg,
    *,
    fra: datetime,
    til: datetime,
    tick_s: int = 30,
    med_maaler: bool = True,
    observer: Callable[[datetime, dict], None] | None = None,
) -> dict:
    """Kjør coordinatoren tick for tick gjennom perioden og returner siste data."""
    data: dict = {}
    t = fra
    while t <= til:
        anlegg.oppdater(t)
        states: dict[str, object] = {
            "sensor.power": make_state(round(anlegg.effekt_kw(t) * 1000, 1), unit="W"),
        }
        if med_maaler:
            states["sensor.energy"] = make_state(
                anlegg.rapportert_verdi,
                unit="kWh",
                last_changed=anlegg.siste_rapport,
            )
        coord.hass = make_hass_with_states(states)
        with patch(NOW_PATH, return_value=t):
            data = await coord._async_update_data()
        if observer is not None:
            observer(t, data)
        t += timedelta(seconds=tick_s)
    return data


def test_profilen_er_fredriks_morgen():
    """Fasiten testene måles mot er de timene måleren faktisk rapporterte."""
    start = datetime(2026, 9, 22, 6, 0)
    anlegg = Anlegg(start=start, slutt=datetime(2026, 9, 22, 9, 0), effekt_kw=effektprofil)
    for time, fasit in FASIT_KWH.items():
        brukt = anlegg.kwh_mellom(datetime(2026, 9, 22, time, 0), datetime(2026, 9, 22, time + 1, 0))
        assert brukt == pytest.approx(fasit, abs=0.01)


@pytest.mark.asyncio
async def test_projeksjonen_holder_seg_gjennom_timen_med_timesmaaler():
    """Måleren rapporterer bare 08:00:13 og 09:00:13. Projeksjonen skal stå seg likevel.

    Ved minutt 5 går huset på grunnlast, og da er projeksjonen grunnlasten. Ved
    minutt 30 står stekeovnen på, og projeksjonen antar at den blir stående.
    Ved minutt 58 er nesten hele timen målt, og projeksjonen er timen slik den
    faktisk endte. Det er det siste tallet som betyr noe: før fiksen var det
    1,04 x 2/60 = 0,03 kW.
    """
    fra = datetime(2026, 9, 22, 7, 0)
    til = datetime(2026, 9, 22, 8, 59, 30)
    anlegg = Anlegg(
        start=fra,
        slutt=til + timedelta(minutes=1),
        effekt_kw=effektprofil,
        rapporttider=timesrapporter(fra=fra, til=til),
    )
    coord = _make_coordinator(fra)

    maalt: dict[int, dict] = {}

    def observer(t: datetime, data: dict) -> None:
        if t.hour == 8 and t.second == 0 and t.minute in (5, 30, 58):
            maalt[t.minute] = data

    await kjor(coord, anlegg, fra=fra, til=til, observer=observer)

    assert maalt[5]["projected_avg_kw"] == pytest.approx(1.04, abs=0.05)
    assert maalt[30]["projected_avg_kw"] == pytest.approx(1.76 + 6.0 * 0.5, abs=0.1)
    assert maalt[58]["projected_avg_kw"] == pytest.approx(3.52, abs=0.05)

    # Og tallet projeksjonen bygger på følger faktisk forbruk gjennom hele timen.
    assert maalt[5]["actual_kwh_this_hour"] == pytest.approx(1.04 * 5 / 60, abs=0.02)
    assert maalt[30]["actual_kwh_this_hour"] == pytest.approx(1.76, abs=0.05)
    assert maalt[58]["actual_kwh_this_hour"] == pytest.approx(3.485, abs=0.05)


@pytest.mark.asyncio
async def test_kwh_som_kommer_etter_timeskiftet_havner_paa_timen_foer():
    """Måleren melder 09:00:13. De 3,5 kWh hører til timen 08, ikke til timen 09."""
    fra = datetime(2026, 9, 22, 8, 0)
    til = datetime(2026, 9, 22, 9, 1)
    anlegg = Anlegg(
        start=fra,
        slutt=til + timedelta(minutes=1),
        effekt_kw=effektprofil,
        rapporttider=timesrapporter(fra=fra, til=til),
    )
    coord = _make_coordinator(fra)

    data = await kjor(coord, anlegg, fra=fra, til=til)

    assert coord._daily_max_kw[DAGEN] == pytest.approx(FASIT_KWH[8], abs=0.02)
    # Den nye timen har bare det minuttet som faktisk har gått.
    assert data["actual_kwh_this_hour"] == pytest.approx(0.7 / 60, abs=0.02)


@pytest.mark.asyncio
async def test_hele_morgenen_gir_riktig_dagsmaks_med_timesmaaler():
    """Replay av 06 til 09: 0,93, 1,53 og 3,52 kWh. Dagsmaks skal bli den høyeste."""
    fra = datetime(2026, 9, 22, 6, 0)
    til = datetime(2026, 9, 22, 9, 1)
    anlegg = Anlegg(
        start=fra,
        slutt=til + timedelta(minutes=1),
        effekt_kw=effektprofil,
        rapporttider=timesrapporter(fra=fra, til=til),
    )
    coord = _make_coordinator(fra)

    timer: dict[int, float] = {}

    def observer(t: datetime, _data: dict) -> None:
        if coord._ventende_time is not None:
            timer[coord._ventende_time.hour_start.hour] = coord._ventende_time.kwh

    await kjor(coord, anlegg, fra=fra, til=til, observer=observer)

    for time, fasit in FASIT_KWH.items():
        assert timer[time] == pytest.approx(fasit, abs=0.03), f"timen {time}"
    assert coord._daily_max_kw[DAGEN] == pytest.approx(FASIT_KWH[8], abs=0.03)


@pytest.mark.asyncio
async def test_uten_energisensor_folger_timen_effektintegrasjonen():
    """Docs lover et brukbart tall uten energy-sensor. Da er integrasjonen alt vi har."""
    fra = datetime(2026, 9, 22, 8, 0)
    til = datetime(2026, 9, 22, 9, 0, 30)
    anlegg = Anlegg(start=fra, slutt=til + timedelta(minutes=1), effekt_kw=effektprofil)
    coord = _make_coordinator(fra, energy_sensor=None)

    ved_58 = {}

    def observer(t: datetime, data: dict) -> None:
        if t == datetime(2026, 9, 22, 8, 58):
            ved_58.update(data)

    await kjor(coord, anlegg, fra=fra, til=til, med_maaler=False, observer=observer)

    assert ved_58["projected_avg_kw"] == pytest.approx(FASIT_KWH[8], abs=0.05)
    assert coord._daily_max_kw[DAGEN] == pytest.approx(FASIT_KWH[8], rel=0.02)


@pytest.mark.asyncio
async def test_maaler_som_oppdaterer_ofte_blir_ikke_daarligere():
    """Det lykkelige tilfellet: måleren rapporterer hvert tiende sekund.

    Da skal timen være målerens egen differanse, ikke en blanding av måling og
    anslag.
    """
    fra = datetime(2026, 9, 22, 8, 0)
    til = datetime(2026, 9, 22, 8, 59, 30)
    rapporter = [fra + timedelta(seconds=10 * i) for i in range(370)]
    anlegg = Anlegg(
        start=fra,
        slutt=til + timedelta(minutes=1),
        effekt_kw=effektprofil,
        rapporttider=rapporter,
    )
    coord = _make_coordinator(fra)

    data = await kjor(coord, anlegg, fra=fra, til=til)

    # Siste tick er 08:59:30, og måleren rapporterte 08:59:30.
    fasit = anlegg.kwh_mellom(datetime(2026, 9, 22, 8, 0), datetime(2026, 9, 22, 8, 59, 30))
    assert data["actual_kwh_this_hour"] == pytest.approx(fasit, abs=0.005)
    assert data["kwh_maalt_fra_minutt"] == 0


@pytest.mark.asyncio
async def test_oppstart_midt_i_timen_sier_fra_om_at_timen_er_ufullstendig():
    """Vi kan ikke integrere bakover, og skal ikke finne på et tall for det vi ikke så."""
    fra = datetime(2026, 9, 22, 8, 20)
    til = datetime(2026, 9, 22, 8, 25)
    anlegg = Anlegg(
        start=fra,
        slutt=til + timedelta(minutes=1),
        effekt_kw=effektprofil,
        rapporttider=[],
    )
    coord = _make_coordinator(fra)

    data = await kjor(coord, anlegg, fra=fra, til=til)

    assert data["kwh_maalt_fra_minutt"] == 20
    # Bare de fem minuttene vi faktisk har sett er talt opp.
    assert data["actual_kwh_this_hour"] == pytest.approx(6.0 * 5 / 60, abs=0.02)


@pytest.mark.asyncio
async def test_dekningen_utvides_naar_maaleren_dekker_starten_av_timen():
    """Timesmåleren som melder 09:00:13 dekker hele timen 08, også før oppstart."""
    fra = datetime(2026, 9, 22, 8, 20)
    til = datetime(2026, 9, 22, 9, 1)
    anlegg = Anlegg(
        start=fra,
        slutt=til + timedelta(minutes=1),
        effekt_kw=effektprofil,
        rapporttider=timesrapporter(fra=fra, til=til),
    )
    coord = _make_coordinator(fra)

    data = await kjor(coord, anlegg, fra=fra, til=til)

    assert data["kwh_maalt_fra_minutt"] == 0


def test_integrer_effekt_deler_paa_timeskiftet():
    """Energien før timeskiftet hører til timen som ble ferdig."""
    resultat = integrer_effekt(
        forrige_ts=datetime(2026, 9, 22, 8, 59, 50),
        forrige_kw=3.0,
        na=datetime(2026, 9, 22, 9, 0, 10),
        na_kw=3.0,
        timeskifte=datetime(2026, 9, 22, 9, 0),
    )
    assert resultat.foer_timeskiftet_kwh == pytest.approx(3.0 * 10 / 3600)
    assert resultat.etter_timeskiftet_kwh == pytest.approx(3.0 * 10 / 3600)


def test_integrer_effekt_bruker_trapes_mellom_to_avlesninger():
    resultat = integrer_effekt(
        forrige_ts=datetime(2026, 9, 22, 8, 0),
        forrige_kw=1.0,
        na=datetime(2026, 9, 22, 8, 1),
        na_kw=3.0,
        timeskifte=None,
    )
    assert resultat.etter_timeskiftet_kwh == pytest.approx(2.0 / 60)


def test_integrer_effekt_hopper_over_lange_hull():
    """Etter en halvtimes nedetid sier forrige avlesning ingenting om tiden som gikk."""
    resultat = integrer_effekt(
        forrige_ts=datetime(2026, 9, 22, 8, 0),
        forrige_kw=6.0,
        na=datetime(2026, 9, 22, 8, 30),
        na_kw=6.0,
        timeskifte=None,
    )
    assert resultat.etter_timeskiftet_kwh == 0.0


def test_tidsandeler_deler_vinduet_paa_timeskiftet():
    andeler = tidsandeler(
        fra=datetime(2026, 9, 22, 8, 0, 13),
        til=datetime(2026, 9, 22, 9, 0, 13),
        time_start=datetime(2026, 9, 22, 9, 0),
        forrige_time_start=datetime(2026, 9, 22, 8, 0),
    )
    assert andeler.forrige_time == pytest.approx(3587 / 3600)
    assert andeler.denne_timen == pytest.approx(13 / 3600)


def test_fordel_maalerdelta_folger_anslaget_ikke_tiden():
    """Måleren sier hvor mye, integrasjonen sier når. De 13 sekundene er ikke halve timen."""
    fordeling = fordel_maalerdelta(
        delta_kwh=3.517,
        estimat_forrige_time_kwh=3.5,
        estimat_denne_timen_kwh=0.004,
        andeler=Tidsandeler(forrige_time=3587 / 3600, denne_timen=13 / 3600),
    )
    assert fordeling.forrige_time_kwh == pytest.approx(3.513, abs=0.005)
    assert fordeling.denne_timen_kwh == pytest.approx(0.004, abs=0.005)


def test_fordel_maalerdelta_skalerer_ned_naar_vinduet_rekker_lenger_tilbake():
    """Det som hører til timer vi ikke kan rette på skal ikke dyttes inn i timen nå."""
    fordeling = fordel_maalerdelta(
        delta_kwh=9.0,
        estimat_forrige_time_kwh=1.0,
        estimat_denne_timen_kwh=1.0,
        andeler=Tidsandeler(forrige_time=1 / 3, denne_timen=0.0),
    )
    assert fordeling.forrige_time_kwh == pytest.approx(1.5)
    assert fordeling.denne_timen_kwh == pytest.approx(1.5)


def test_tidsandeler_uten_vindu_plasserer_ingenting():
    """Uten en tid å måle avlesningen mot kan ingenting av den plasseres."""
    andeler = tidsandeler(
        fra=None,
        til=datetime(2026, 9, 22, 9, 0),
        time_start=datetime(2026, 9, 22, 9, 0),
        forrige_time_start=datetime(2026, 9, 22, 8, 0),
    )
    assert andeler.forrige_time == 0.0
    assert andeler.denne_timen == 0.0


def test_tidsandeler_uten_varighet_gaar_til_timen_na():
    """Et vindu uten varighet er ikke et ukjent vindu. Da skal ingenting gå tapt."""
    tid = datetime(2026, 9, 22, 9, 30)
    andeler = tidsandeler(
        fra=tid,
        til=tid,
        time_start=datetime(2026, 9, 22, 9, 0),
        forrige_time_start=datetime(2026, 9, 22, 8, 0),
    )
    assert andeler.denne_timen == 1.0
