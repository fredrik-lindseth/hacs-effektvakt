"""Kausal lastmodell for scenarioer, ikke bevis paa styring i Home Assistant.

Hver maalt time antas aa ha jevn effekt. En antatt fleksibel lastgruppe kan
utsette forbruk, og har egen ekstra effekt til aa ta det igjen etter slipp.
Dette er ikke en termostatmodell: tilgjengelighet og tilbakefoering er
forutsetninger som maa oppgis sammen med resultatet. Ingen energi slettes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from .modell import Trinn, vurder_kuttkriterium

Strategi = Literal["reaktiv", "maal"]
EPSILON = 1e-9


@dataclass(frozen=True)
class Simuleringstime:
    """En fysisk time; lokalt tidsstempel bestemmer kalenderdag og maaned."""

    start: datetime
    kwh: float | None


@dataclass(frozen=True)
class Simuleringsvalg:
    """Eksplisitte antakelser for en fleksibel lastgruppe."""

    kutt_kw: float
    tilbakefoering_kw: float
    maal_kw: float = 5.0
    maks_av_minutter: int = 60
    minste_paa_minutter: int = 5
    komfortfrist_minutter: int = 120
    tick_minutter: int = 1

    def __post_init__(self) -> None:
        for verdi in (self.kutt_kw, self.tilbakefoering_kw, self.maal_kw):
            if not math.isfinite(verdi) or verdi <= 0:
                raise ValueError("Effekt og maal maa vaere endelige positive tall")
        for minutter in (
            self.maks_av_minutter,
            self.minste_paa_minutter,
            self.komfortfrist_minutter,
            self.tick_minutter,
        ):
            if not isinstance(minutter, int) or isinstance(minutter, bool) or minutter <= 0:
                raise ValueError("Varigheter maa vaere positive hele minutter")
        if 60 % self.tick_minutter:
            raise ValueError("Tick maa dele en time i like deler")
        if any(
            minutter % self.tick_minutter
            for minutter in (self.maks_av_minutter, self.minste_paa_minutter, self.komfortfrist_minutter)
        ):
            raise ValueError("Varigheter maa kunne overholdes med valgt tick")


@dataclass(frozen=True)
class SimulertTime:
    """Utfall med gjeld, slik at forskjoevet forbruk ikke blir spart energi."""

    start: datetime
    opprinnelig_kwh: float | None
    styrt_kwh: float | None
    utsatt_kwh: float
    tilbakefoert_kwh: float
    gjeld_kwh: float
    kutt_minutter: int


@dataclass
class Simuleringsresultat:
    timer: list[SimulertTime] = field(default_factory=list)
    ugyldige_maaneder: set[str] = field(default_factory=set)
    fristbrudd: int = 0

    @property
    def restgjeld_kwh(self) -> float:
        return self.timer[-1].gjeld_kwh if self.timer else 0.0


def _maaned(tid: datetime) -> str:
    return tid.strftime("%Y-%m")


def _vil_kutte(
    *,
    strategi: Strategi,
    trinn: Trinn,
    dager: dict[date, float],
    dag: date,
    brukt: float,
    effekt: float,
    forloep: float,
    valg: Simuleringsvalg,
) -> bool:
    projisert = brukt + effekt * (1 - forloep)
    return vurder_kuttkriterium(
        trinn=trinn,
        daily_max_kw=dager,
        today=dag,
        projected_kw=projisert,
        actual_kwh_this_hour=brukt,
        elapsed_h=forloep,
        tilgjengelig_kutt_kw=min(valg.kutt_kw, effekt),
        valgt_maal_kw=valg.maal_kw if strategi == "maal" else None,
    ).oppfylt


def simuler(
    timer: list[Simuleringstime], *, trinn: Trinn, strategi: Strategi, valg: Simuleringsvalg
) -> Simuleringsresultat:
    """Foer styrt historikk videre, med timeslipp og kausal tilbakefoering.

    Etter slipp tilbakefoeres gjelden straks med begrenset ekstra effekt.
    Nye kutt venter til gjelden er betalt og minste paatid har gaatt.
    Komfortfristen kan forkorte kuttet for aa gi plass til tilbakefoeringen.
    Hull gir ingen antatt avlesning eller tilbakefoering. Gjeld overlever hull
    og maanedsskifte; restgjeld ved slutten gjoer berorte maaneder ufullstendige.
    """
    if strategi not in ("reaktiv", "maal"):
        raise ValueError("Ukjent strategi")
    if not trinn or valg.maal_kw not in [grense for grense, _ in trinn]:
        raise ValueError("Maalet maa vaere en terskel i den valgte trinntabellen")
    resultat = Simuleringsresultat()
    dager: dict[date, float] = {}
    maaned = ""
    gjeld = 0.0
    gjeldsmaaneder: set[str] = set()
    komfortfrist: datetime | None = None
    av_frist: datetime | None = None
    tidligst_kutt: datetime | None = None
    forrige_slutt: datetime | None = None
    brudd_registrert = False
    dt = valg.tick_minutter / 60

    for time in timer:
        if time.start.tzinfo is None:
            raise ValueError("Timer maa ha tidssone")
        if time.start.minute or time.start.second or time.start.microsecond:
            raise ValueError("Timer maa starte ved timeskiftet")
        start = time.start.astimezone(UTC)
        slutt = start + timedelta(hours=1)
        if forrige_slutt is not None and start != forrige_slutt:
            raise ValueError("Timer maa vaere kronologiske og sammenhengende; bruk None for hull")
        forrige_slutt = slutt
        if time.kwh is not None and (not math.isfinite(time.kwh) or time.kwh < 0):
            raise ValueError("Energi maa vaere endelig og ikke-negativ, eller None")
        if _maaned(time.start) != maaned:
            maaned = _maaned(time.start)
            dager = {}
        if av_frist is not None:
            av_frist = None
            tidligst_kutt = start + timedelta(minutes=valg.minste_paa_minutter)
        if time.kwh is None:
            resultat.ugyldige_maaneder.add(maaned)
            resultat.ugyldige_maaneder.update(gjeldsmaaneder)
            resultat.timer.append(SimulertTime(time.start, None, None, 0, 0, gjeld, 0))
            continue

        brukt = utsatt = tilbake = 0.0
        kutt_minutter = 0
        for minutt in range(0, 60, valg.tick_minutter):
            naa = start + timedelta(minutes=minutt)
            neste = naa + timedelta(minutes=valg.tick_minutter)
            effekt = time.kwh  # Jevn effekt er en forutsetning, ikke intra-time-maaledata.
            kutt = min(valg.kutt_kw, effekt)
            if komfortfrist is not None and gjeld > EPSILON and naa >= komfortfrist and not brudd_registrert:
                resultat.fristbrudd += 1
                resultat.ugyldige_maaneder.update(gjeldsmaaneder | {maaned})
                brudd_registrert = True
            if av_frist is not None:
                tid_til_betaling = gjeld / valg.tilbakefoering_kw
                tid_igjen = (komfortfrist - naa).total_seconds() / 3600 if komfortfrist else 0
                if naa >= av_frist or tid_til_betaling + dt * (1 + kutt / valg.tilbakefoering_kw) > tid_igjen + EPSILON:
                    av_frist = None
                    tidligst_kutt = naa + timedelta(minutes=valg.minste_paa_minutter)
            if (
                av_frist is None
                and gjeld <= EPSILON
                and (tidligst_kutt is None or naa >= tidligst_kutt)
                and dt * (1 + kutt / valg.tilbakefoering_kw) <= valg.komfortfrist_minutter / 60
                and _vil_kutte(
                    strategi=strategi,
                    trinn=trinn,
                    dager=dager,
                    dag=time.start.date(),
                    brukt=brukt,
                    effekt=effekt,
                    forloep=minutt / 60,
                    valg=valg,
                )
            ):
                av_frist = min(slutt, naa + timedelta(minutes=valg.maks_av_minutter))
                komfortfrist = naa + timedelta(minutes=valg.komfortfrist_minutter)
                brudd_registrert = False
            if av_frist is not None:
                energi = kutt * dt
                gjeld += energi
                utsatt += energi
                gjeldsmaaneder.add(maaned)
                brukt += (effekt - kutt) * dt
                kutt_minutter += valg.tick_minutter
            else:
                energi = min(gjeld, valg.tilbakefoering_kw * dt)
                gjeld = max(0.0, gjeld - energi)
                tilbake += energi
                brukt += effekt * dt + energi
                if gjeld <= EPSILON:
                    gjeld = 0.0
                    gjeldsmaaneder.clear()
                    komfortfrist = None
            if neste == slutt and av_frist is not None:
                av_frist = None
                tidligst_kutt = slutt + timedelta(minutes=valg.minste_paa_minutter)
        dager[time.start.date()] = max(dager.get(time.start.date(), 0.0), brukt)
        resultat.timer.append(SimulertTime(time.start, time.kwh, brukt, utsatt, tilbake, gjeld, kutt_minutter))
    if gjeld > EPSILON:
        resultat.ugyldige_maaneder.update(gjeldsmaaneder)
        if maaned:
            resultat.ugyldige_maaneder.add(maaned)
    return resultat
