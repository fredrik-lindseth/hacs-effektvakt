"""Beskriv maalt last over tid, uten aa love framtidig kuttbar energi.

Innleseren normaliserer enheter til W. Recorder-tilstander gjelder fram til
neste observasjon; en valgfri maksimal holdetid passer kilder med forventede
periodiske rapporter. Ukjent effekt og ugyldige tall er hull, aldri null W.
Aktive perioder ved vindusgrenser og hull er sensurerte, ikke hele sykluser.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Literal


@dataclass(frozen=True)
class Effektpunkt:
    tid: datetime
    watt: float | None


@dataclass(frozen=True)
class Effektintervall:
    start: datetime
    slutt: datetime
    watt: float | None


@dataclass(frozen=True)
class AktivPeriode:
    start: datetime
    slutt: datetime
    venstre_sensurert: bool
    hoyre_sensurert: bool

    @property
    def varighet_s(self) -> float:
        return (self.slutt - self.start).total_seconds()

    @property
    def hel(self) -> bool:
        return not self.venstre_sensurert and not self.hoyre_sensurert


@dataclass(frozen=True)
class Tidsoppsummering:
    """Aktiv andel bruker bare kjent tid; dekningen viser hva som mangler."""

    varighet_s: float
    kjent_s: float
    aktiv_s: float
    kjent_wh: float
    aktiv_wh: float

    @property
    def dekning(self) -> float:
        return self.kjent_s / self.varighet_s

    @property
    def aktiv_andel(self) -> float | None:
        return self.aktiv_s / self.kjent_s if self.kjent_s else None

    @property
    def middel_w(self) -> float | None:
        return self.kjent_wh / (self.kjent_s / 3600) if self.kjent_s else None

    @property
    def middel_aktiv_w(self) -> float | None:
        return self.aktiv_wh / (self.aktiv_s / 3600) if self.aktiv_s else None


@dataclass(frozen=True)
class Lastprofil:
    terskel_w: float
    tidsgrunnlag: Tidsoppsummering
    intervaller: tuple[Effektintervall, ...]
    aktive_perioder: tuple[AktivPeriode, ...]

    @property
    def hele_varigheter_s(self) -> tuple[float, ...]:
        return tuple(p.varighet_s for p in self.aktive_perioder if p.hel)


@dataclass(frozen=True)
class Restvarighet:
    """Empirisk P(T >= a+d | T >= a), bare fra hele observerte sykluser.

    Sensurerte sykluser er utelatt og kan skjevfordele anslaget mot korte
    sykluser. Antall og dekning maa derfor foelge sannsynligheten. Dette er
    beskrivende historikk, ikke en garanti eller en sanntidsmaaling.
    """

    sannsynlighet: float | None
    stoette_antall: int
    minst_saa_lenge_antall: int
    sensurerte_antall: int
    datagrunnlag: Literal["ingen", "lavt", "beskrivende"]


def _utc(tid: datetime) -> datetime:
    if tid.tzinfo is None or tid.utcoffset() is None:
        raise ValueError("Tidsstempel maa ha tidssone")
    return tid.astimezone(UTC)


def _effekt(verdi: float | None) -> float | None:
    if verdi is None or not math.isfinite(verdi) or verdi < 0:
        return None
    return verdi


def _oppsummer(intervaller: list[Effektintervall], *, varighet_s: float, terskel_w: float) -> Tidsoppsummering:
    kjent = aktiv = energi = aktiv_energi = 0.0
    for intervall in intervaller:
        if intervall.watt is None:
            continue
        sekunder = (intervall.slutt - intervall.start).total_seconds()
        wh = intervall.watt * (sekunder / 3600)
        kjent += sekunder
        energi += wh
        if intervall.watt > terskel_w:
            aktiv += sekunder
            aktiv_energi += wh
    return Tidsoppsummering(varighet_s, kjent, aktiv, energi, aktiv_energi)


def _aktive_perioder(intervaller: list[Effektintervall], terskel_w: float) -> tuple[AktivPeriode, ...]:
    perioder = []
    start: datetime | None = None
    venstre = True
    forrige: bool | None = None
    for intervall in intervaller:
        paa = None if intervall.watt is None else intervall.watt > terskel_w
        if paa and start is None:
            start = intervall.start
            venstre = forrige is not False
        elif paa is not True and start is not None:
            perioder.append(AktivPeriode(start, intervall.start, venstre, paa is None))
            start = None
        forrige = paa
    if start is not None:
        perioder.append(AktivPeriode(start, intervaller[-1].slutt, venstre, True))
    return tuple(perioder)


def analyser_lastprofil(
    punkter: list[Effektpunkt],
    *,
    start: datetime,
    slutt: datetime,
    terskel_w: float,
    maks_hold: timedelta | None = None,
    ekskluderte_vinduer: list[tuple[datetime, datetime]] | None = None,
) -> Lastprofil:
    """Tidsvekt observerte tilstander i [start, slutt), aldri antall samples.

    Et punkt foer start kan gi tilstanden ved start, men gir ikke en hel
    paaperiode. Foerste tilstand etter start fyller heller ikke tidligere
    maalehull. Listen maa vaere strengt kronologisk; like tidspunkter avvises.
    Styrte kutt kan ekskluderes som ukjent tid, slik at de ikke blir laert
    som naturlig korte paasykluser. Dette bryter og sensurerer syklusene.
    """
    start, slutt = _utc(start), _utc(slutt)
    if slutt <= start:
        raise ValueError("Analyseintervallet maa ha positiv varighet")
    if not math.isfinite(terskel_w) or terskel_w < 0:
        raise ValueError("Aktiv terskel maa vaere endelig og ikke-negativ")
    if maks_hold is not None and maks_hold <= timedelta(0):
        raise ValueError("Maksimal holdetid maa vaere positiv")
    observasjoner = [Effektpunkt(_utc(p.tid), _effekt(p.watt)) for p in punkter]
    if any(a.tid >= b.tid for a, b in pairwise(observasjoner)):
        raise ValueError("Observasjoner maa vaere strengt kronologiske")
    intervaller: list[Effektintervall] = []
    cursor = start
    for i, punkt in enumerate(observasjoner):
        neste = observasjoner[i + 1].tid if i + 1 < len(observasjoner) else slutt
        fra, til = max(start, punkt.tid), min(slutt, neste)
        if til <= fra:
            continue
        if fra > cursor:
            intervaller.append(Effektintervall(cursor, fra, None))
        kjent_til = til if maks_hold is None else min(til, max(fra, punkt.tid + maks_hold))
        if kjent_til > fra:
            intervaller.append(Effektintervall(fra, kjent_til, punkt.watt))
        if kjent_til < til:
            intervaller.append(Effektintervall(kjent_til, til, None))
        cursor = til
    if cursor < slutt:
        intervaller.append(Effektintervall(cursor, slutt, None))
    for fra, til in ekskluderte_vinduer or []:
        fra, til = _utc(fra), _utc(til)
        if til <= fra:
            raise ValueError("Ekskluderte vinduer maa ha positiv varighet")
        beholdte = []
        for intervall in intervaller:
            if intervall.slutt <= fra or intervall.start >= til:
                beholdte.append(intervall)
                continue
            if intervall.start < fra:
                beholdte.append(Effektintervall(intervall.start, fra, intervall.watt))
            beholdte.append(Effektintervall(max(fra, intervall.start), min(til, intervall.slutt), None))
            if intervall.slutt > til:
                beholdte.append(Effektintervall(til, intervall.slutt, intervall.watt))
        intervaller = beholdte
    return Lastprofil(
        terskel_w,
        _oppsummer(intervaller, varighet_s=(slutt - start).total_seconds(), terskel_w=terskel_w),
        tuple(intervaller),
        _aktive_perioder(intervaller, terskel_w),
    )


def anslaa_restvarighet(
    profil: Lastprofil,
    *,
    allerede_paa_s: float,
    minst_videre_s: float,
    minste_stoette: int = 20,
) -> Restvarighet:
    """Andel hele sykluser som fortsatte lenge nok, gitt allerede observert tid.

    Terskelen for lite stoette er en rapporteringsregel, ikke en statistisk
    sikkerhetsgrense. Selv et stort utvalg er kun historikk for denne lasten.
    """
    if any(not math.isfinite(v) or v < 0 for v in (allerede_paa_s, minst_videre_s)):
        raise ValueError("Varigheter maa vaere endelige og ikke-negative")
    if not isinstance(minste_stoette, int) or isinstance(minste_stoette, bool) or minste_stoette <= 0:
        raise ValueError("Minste stoette maa vaere et positivt heltall")
    utvalg = [v for v in profil.hele_varigheter_s if v >= allerede_paa_s]
    antall = len(utvalg)
    treff = sum(v >= allerede_paa_s + minst_videre_s for v in utvalg)
    sensurerte = sum(not p.hel for p in profil.aktive_perioder)
    kvalitet: Literal["ingen", "lavt", "beskrivende"] = "ingen"
    if antall:
        kvalitet = "beskrivende"
        if antall < minste_stoette or profil.tidsgrunnlag.dekning < 0.9 or sensurerte > len(profil.hele_varigheter_s):
            kvalitet = "lavt"
    return Restvarighet(treff / antall if antall else None, antall, treff, sensurerte, kvalitet)


def oppsummer_vinduer(profil: Lastprofil, vinduer: list[tuple[datetime, datetime]]) -> Tidsoppsummering:
    """Maalt overlapp med f.eks. topptimer; ukjent tid teller i dekningen.

    Vinduer kan ligge utenfor profilens maaleperiode, men den tiden er ukjent.
    Overlappende vinduer avvises slik at sekunder og energi ikke telles dobbelt.
    """
    normaliserte = sorted((_utc(start), _utc(slutt)) for start, slutt in vinduer)
    if not normaliserte or any(slutt <= start for start, slutt in normaliserte):
        raise ValueError("Minst ett vindu med positiv varighet kreves")
    if any(a[1] > b[0] for a, b in pairwise(normaliserte)):
        raise ValueError("Vinduer kan ikke overlappe")
    utsnitt = []
    for start, slutt in normaliserte:
        for intervall in profil.intervaller:
            fra, til = max(start, intervall.start), min(slutt, intervall.slutt)
            if til > fra:
                utsnitt.append(Effektintervall(fra, til, intervall.watt))
    return _oppsummer(
        utsnitt,
        varighet_s=sum((slutt - start).total_seconds() for start, slutt in normaliserte),
        terskel_w=profil.terskel_w,
    )
