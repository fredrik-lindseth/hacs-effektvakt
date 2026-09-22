"""Terskelmodellen: ett tak som risiko, margin, kostnad og «kan legge på» regner fra.

Ren modul uten Home Assistant-import, så modellen kan regnes og testes uten
stubber. `coordinator.py` kaller hit og gjør ingen terskelaritmetikk selv.

Nettselskapet fakturerer snittet av de tre høyeste time-snittene fra tre ulike
dager i måneden. Spørsmålet «hvor høy kan timen vi står i bli» har derfor tre
ledd:

1. Hvilket trinn kan måneden fortsatt ende på? Det billigste som er igjen, gitt
   dagsmaksene som alt er låst inn. Terskelen til det trinnet er T.
2. Hvor høy kan dagen i dag bli uten å dra snittet over T? Snittet av de tre
   høyeste er `(a + b + x) / 3`, der `a` og `b` er de to høyeste ANDRE dagene,
   så `x <= 3T - (a + b)`. Jo høyere de andre dagene er, jo mindre tåler dagen
   i dag. Dette er motsatt vei av det integrasjonen regnet fram til september
   2026, og feilen var størst i nettopp den måneden vakten finnes for.
3. Kappet ved T. En dag godt over T holder seg innenfor bare ved å låne av
   resten av måneden, og en vakt som tillater det melder god margin helt til
   måneden er tapt.

Til slutt: en time under dagens eget dagsmaks flytter ingenting, for dagen
teller bare med sin høyeste time. Taket for timen vi står i er derfor
`max(dagens maks, x*)`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields
from typing import TYPE_CHECKING

from .const import (
    KORTVARIG_LAST_KW,
    MAX_POWER_CLAMP_W,
    RISIKO_GOD_MARGIN,
    RISIKO_LIKE_UNDER,
    RISIKO_NAERMER_SEG,
    RISIKO_OVER_TERSKEL,
    RISIKO_RANK,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from datetime import date, datetime

# Kapasitetstrinn slik dso.py leverer dem: (øvre terskel i kW, månedspris i kr),
# sortert stigende. Øverste trinn har float("inf") som terskel.
Trinn = list[tuple[float, int]]


def topp_n_sum(verdier: Iterable[float], *, n: int) -> float:
    """Sum av de n høyeste verdiene. Finnes det færre, teller resten som null."""
    return sum(sorted(verdier, reverse=True)[:n])


def top_n_average(daily_max_kw: Mapping[date, float], *, n: int) -> float | None:
    """Snitt av de n høyeste dagsmaksene, delt på antallet som faktisk finnes.

    Brukes bare til å arkivere en måned som er gjort opp. Der er antall dager
    et faktum og ikke en antakelse, så delingen på antallet er riktig. Alt som
    ser framover bruker `snitt_av_topp_3`, som alltid deler på tre.

    Returnerer None for en tom måned.
    """
    if not daily_max_kw:
        return None
    take = sorted(daily_max_kw.values(), reverse=True)[:n]
    return sum(take) / len(take)


def snitt_av_topp_3(daily_max_kw: Mapping[date, float]) -> float:
    """Topp-3-snittet slik regningen regner det: sum av inntil tre, alltid delt på tre.

    Dager som ikke finnes ennå teller som null. Tallet er dermed monotont
    gjennom måneden: det kan bare stige, aldri falle fordi en rolig dag ble
    lagt til. Det er samtidig en nedre skranke for hva måneden kan ende på, for
    dagene som er låst inn kan ikke kuttes i ettertid.
    """
    return topp_n_sum(daily_max_kw.values(), n=3) / 3


def topp_2_andre_dager(daily_max_kw: Mapping[date, float], *, today: date) -> float:
    """Sum av de to høyeste dagsmaksene fra andre dager enn i dag.

    Det er disse to dagen i dag må dele topp-3-snittet med, og de bestemmer hvor
    mye den har igjen å gå på.
    """
    return topp_n_sum((kw for dag, kw in daily_max_kw.items() if dag != today), n=2)


def trinn_indeks(kw: float, trinn: Trinn) -> int:
    """Indeks til trinnet en kW-verdi havner i: laveste trinn med terskel >= kw.

    Over høyeste terskel returneres øverste trinn. Tomt trinn-sett er ikke
    lovlig her; kallerne sjekker det først.
    """
    for i, (terskel, _) in enumerate(trinn):
        if kw <= terskel:
            return i
    return len(trinn) - 1


def dagstak(*, maal_terskel_kw: float, topp_2_andre_kw: float) -> float:
    """x*: høyeste dagsmaks i dag som holder topp-3-snittet på eller under T.

    `3T - (a + b)` er inversen av `(a + b + x) / 3 <= T`. Kappet ved T fordi en
    dag langt over T bare holder seg innenfor ved å låne av resten av måneden.
    Bunnen på null er en sikring: kallerne velger T slik at `a + b <= 3T`, så
    den slår aldri til med tall modellen har regnet ut selv.
    """
    return max(0.0, min(maal_terskel_kw, 3 * maal_terskel_kw - topp_2_andre_kw))


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


# Taket paa «kan legge paa resten av timen». Formelen deler paa resten av timen
# og gaar mot uendelig de siste sekundene, og et tall som spretter til 3600
# knekker baade grafen og tilliten. Samme absoluttgrense som effektavlesningen
# klampes mot, for ingen bolig trekker mer.
MAKS_PAASLAG_KW: float = MAX_POWER_CLAMP_W / 1000


@dataclass(frozen=True)
class RestenAvTimen:
    """Hva som er igjen av timen, og hvor mye last det er plass til i den.

    `margin_kw` sier hvor mye time-snittet taaler aa stige, og det er ikke det
    samme som hvor mye man kan slaa paa. En last som staar paa i ti av seksti
    minutter flytter time-snittet med en sjettedel av effekten sin, saa
    marginen blir mer tillatende jo naermere timeslutt man kommer: kl. 18:50
    med 1 kW margin er det 6 kW som kan legges paa, ikke 1. Det er nettopp den
    innsikten en effektvakt skal gi, og «margin 1,00 kW» gir den aldri.
    """

    minutter_igjen: int
    kan_legge_paa_resten_av_timen_kw: float | None


def beregn_resten_av_timen(*, margin_kw: float | None, elapsed_h: float) -> RestenAvTimen:
    """Minutter igjen av timen, og kW som kan legges paa uten aa passere taket.

    Utledningen: en last paa P kW som staar resten av timen loefter det
    projiserte snittet med `P * (1 - elapsed_h)`, saa `P <= margin / (1 -
    elapsed_h)`. Det er den samme marginen sensoren viser, bare oversatt til
    noe man kan slaa paa.

    Minuttene teller ned slik `elapsed_minutes_in_hour` teller opp, saa de to
    alltid summerer til 60.
    """
    minutter_igjen = max(0, 60 - int(elapsed_h * 60))
    rest_h = max(0.0, 1.0 - elapsed_h)
    if margin_kw is None:
        return RestenAvTimen(minutter_igjen=minutter_igjen, kan_legge_paa_resten_av_timen_kw=None)
    if margin_kw <= 0:
        return RestenAvTimen(minutter_igjen=minutter_igjen, kan_legge_paa_resten_av_timen_kw=0.0)
    if rest_h <= 0:
        return RestenAvTimen(minutter_igjen=minutter_igjen, kan_legge_paa_resten_av_timen_kw=MAKS_PAASLAG_KW)
    return RestenAvTimen(
        minutter_igjen=minutter_igjen,
        kan_legge_paa_resten_av_timen_kw=min(MAKS_PAASLAG_KW, margin_kw / rest_h),
    )


@dataclass(frozen=True)
class Topp3Dag:
    """En av dagene topp-3-snittet er bygget av. Datoen er ISO-tekst for JSON."""

    dato: str
    kw: float


@dataclass(frozen=True)
class Topp3Oversikt:
    """Hvilke dager som teller, og hva en hoeyere time i dag ville gjort med dem."""

    dager: list[Topp3Dag]
    i_dag_teller_med: bool
    dag_som_ryker: Topp3Dag | None


def beregn_topp_3_oversikt(daily_max_kw: Mapping[date, float], *, today: date) -> Topp3Oversikt:
    """De tre dagene regningen faktisk bygger paa, hoeyest foerst.

    Brukeren ser ellers bare snittet, aldri hva det bestaar av, og det er
    sammensetningen som avgjoer om timen man staar i betyr noe. Teller dagens
    maks alt med, koster en ny time paa samme nivaa ingenting: den bytter bare
    ut sin egen plass. Gjoer den det ikke, er `dag_som_ryker` den laveste av de
    tre, altsaa dagen en hoeyere dagsmaks i dag ville skjoevet ut av regningen.

    Sorteringen er stabil paa dato naar to dager er like hoeye, saa listen ikke
    bytter rekkefoelge mellom to tick.
    """
    sortert = sorted(daily_max_kw.items(), key=lambda par: (-par[1], par[0]))[:3]
    dager = [Topp3Dag(dato=dag.isoformat(), kw=round(kw, 3)) for dag, kw in sortert]
    i_dag_teller_med = any(dag == today for dag, _ in sortert)
    ryker = None if i_dag_teller_med or len(dager) < 3 else dager[-1]
    return Topp3Oversikt(dager=dager, i_dag_teller_med=i_dag_teller_med, dag_som_ryker=ryker)


@dataclass(frozen=True)
class Terskel:
    """Taket timen vi står i måles mot, og tallene det er bygget av.

    Alle kW-feltene er time-snitt, samme enhet som projeksjonen.

    Er `maal_terskel_kw` None, finnes det ikke noe dyrere trinn å unngå: enten
    er nettselskapet ukjent, eller så ligger måneden alt på øverste trinn. Da er
    det ingenting å måle mot, og margin og tak er None framfor uendelig.
    """

    maal_terskel_kw: float | None
    maal_trinn_kr: int | None
    dagstak_kw: float | None
    time_tak_kw: float | None
    margin_kw: float | None
    kutt_anbefalt_kw: float
    kan_legge_paa_kw: float | None
    dagens_maks_kw: float
    topp_2_andre_dager_kw: float
    minste_mulige_topp_3_kw: float


def beregn_terskel(
    *,
    trinn: Trinn,
    daily_max_kw: Mapping[date, float],
    today: date,
    projected_kw: float,
) -> Terskel:
    """Regn ut taket for timen vi står i, og marginen opp til det.

    Måltrinnet er det billigste måneden fortsatt kan ende på, altså trinnet
    `minste_mulige_topp_3_kw` havner i. Det følger ikke projeksjonen, så
    referansen flytter seg ikke under føttene på brukeren i det en enkelt time
    spretter opp: hadde den gjort det, ville varselet forsvunnet i samme
    øyeblikk som terskelen ble passert.
    """
    dagens_maks = daily_max_kw.get(today, 0.0)
    topp_2_andre = topp_2_andre_dager(daily_max_kw, today=today)
    minste_mulige = snitt_av_topp_3(daily_max_kw)

    uten_tak = Terskel(
        maal_terskel_kw=None,
        maal_trinn_kr=None,
        dagstak_kw=None,
        time_tak_kw=None,
        margin_kw=None,
        kutt_anbefalt_kw=0.0,
        kan_legge_paa_kw=None,
        dagens_maks_kw=dagens_maks,
        topp_2_andre_dager_kw=topp_2_andre,
        minste_mulige_topp_3_kw=minste_mulige,
    )
    if not trinn:
        return uten_tak

    idx = trinn_indeks(minste_mulige, trinn)
    if idx == len(trinn) - 1:
        # Øverste trinn. Det finnes ikke noe dyrere å unngå, så en høy time
        # koster ikke mer enn en lav.
        return uten_tak

    maal_terskel_kw, maal_trinn_kr = trinn[idx]
    x = dagstak(maal_terskel_kw=maal_terskel_kw, topp_2_andre_kw=topp_2_andre)
    time_tak = max(dagens_maks, x)
    margin = time_tak - projected_kw

    return Terskel(
        maal_terskel_kw=maal_terskel_kw,
        maal_trinn_kr=maal_trinn_kr,
        dagstak_kw=x,
        time_tak_kw=time_tak,
        margin_kw=margin,
        kutt_anbefalt_kw=max(0.0, -margin),
        kan_legge_paa_kw=max(0.0, margin),
        dagens_maks_kw=dagens_maks,
        topp_2_andre_dager_kw=topp_2_andre,
        minste_mulige_topp_3_kw=minste_mulige,
    )


def classify_raw_risk(
    *,
    margin_kw: float | None,
    safety_buffer_kw: float,
    timen_flytter_trinnet: bool,
) -> str:
    """Klassifiser rå risiko ut fra margin, safety_buffer og om timen koster noe.

    Returnerer en av RISIKO_LEVELS. Marginen gir posisjonen:
      god_margin:          margin > 2 x buffer
      naermer_seg_terskel: buffer < margin <= 2 x buffer
      like_under_terskel:  0 < margin <= buffer
      over_terskel:        margin <= 0

    `timen_flytter_trinnet` er vetoet over den tabellen. De to øverste nivåene
    er forbeholdt timer som faktisk koster penger, altså der
    `vurder_kuttkriterium` finner kroner å spare. Gjør timen ikke det, settes
    nivået ned til `naermer_seg_terskel` uansett hvor høyt projeksjonen står.
    Uten vetoet melder en vannkoker ved minutt to kutt på en time som ender
    langt under, fordi projeksjonen der er nesten bare den øyeblikkelige
    effekten.

    Margin None betyr at det ikke finnes noe dyrere trinn å unngå. Da er det
    ingenting å advare mot, og nivået er god_margin.
    """
    if margin_kw is None:
        return RISIKO_GOD_MARGIN
    if margin_kw <= 0:
        nivå = RISIKO_OVER_TERSKEL
    elif margin_kw <= safety_buffer_kw:
        nivå = RISIKO_LIKE_UNDER
    elif margin_kw <= 2 * safety_buffer_kw:
        nivå = RISIKO_NAERMER_SEG
    else:
        nivå = RISIKO_GOD_MARGIN

    if not timen_flytter_trinnet and RISIKO_RANK[nivå] > RISIKO_RANK[RISIKO_NAERMER_SEG]:
        return RISIKO_NAERMER_SEG
    return nivå


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
    trinn_under_terskel_kw: float | None
    trinn_under_oppnaelig: bool
    trinn_under_realistisk: bool
    kostnad_denne_timen_kr: int
    topp_3_projisert_kw: float
    minste_mulige_topp_3_kw: float
    hoyeste_trinn: bool


KOSTNAD_FELT_NAVN: tuple[str, ...] = tuple(f.name for f in fields(KostnadInfo))


def trinn_under_realistisk(
    *,
    under_terskel_kw: float,
    daily_max_kw: Mapping[date, float],
    forrige_maaned_topp_3_kw: float | None,
) -> bool:
    """Er trinnet under noe denne boligen kunne siktet paa i det hele tatt?

    `trinn_under_oppnaelig` svarer paa om trinnet under er innen rekkevidde
    denne maaneden. Det er et annet spoersmaal enn om det noen gang er det:
    under BKKs 2 til 5 kW ligger 0 til 2 kW, og ingen bolig lander der. En
    melding om at trinnet under er tapt ville staatt permanent hele aaret, og
    en melding som alltid staar er ikke informasjon.

    Belegget er husets eget forbruk. Enten landet forrige maaned paa eller
    under terskelen, eller saa gjoer snittet av de tre roligste dagene saa
    langt denne maaneden det: en maaned bygget av dagene huset faktisk har,
    kunne da havnet der. Uten dager aa maale paa svarer vi nei, for en
    nedslaaende melding uten dekning er verre enn ingen melding.
    """
    if forrige_maaned_topp_3_kw is not None and forrige_maaned_topp_3_kw <= under_terskel_kw:
        return True
    roligste = sorted(daily_max_kw.values())[:3]
    if not roligste:
        return False
    return sum(roligste) / len(roligste) <= under_terskel_kw


def compute_kostnad(
    *,
    trinn: Trinn,
    daily_max_kw: Mapping[date, float],
    today: date,
    projected_kw: float,
    forrige_maaned_topp_3_kw: float | None = None,
) -> KostnadInfo | None:
    """Hva kapasitetsleddet koster, og hva som står på spill akkurat nå.

    `topp_3_projisert_kw` er topp-3-snittet der dagens dagsmaks erstattes med
    `max(dagens maks så langt, projisert time-snitt nå)`. Det er trinnet måneden
    ligger an til, og `kostnad_neste_trinn_kr` er hoppet derfra til neste trinn.

    `minste_mulige_topp_3_kw` teller bare dagsmaks som alt er låst inn. Den
    inneværende timen holdes utenfor nettopp fordi den fortsatt kan kuttes, så
    tallet er en nedre skranke for hva måneden kan ende på. Er den under
    terskelen til trinnet under, er trinnet fortsatt innen rekkevidde.

    Begge deler alltid på tre, så de er sammenlignbare og monotone. Da er
    `topp_3_projisert_kw` aldri lavere enn skranken, og `kostnad_denne_timen_kr`
    er kronene den inneværende timen er i ferd med å låse inn: prisen for
    trinnet vi ligger an til minus prisen for trinnet dagene alene gir.

    Tomt trinn-sett (ukjent nettselskap) gir None.
    """
    if not trinn:
        return None

    projiserte_dager = dict(daily_max_kw)
    projiserte_dager[today] = max(daily_max_kw.get(today, 0.0), projected_kw)
    topp_3_projisert = snitt_av_topp_3(projiserte_dager)
    minste_mulige = snitt_av_topp_3(daily_max_kw)

    idx = trinn_indeks(topp_3_projisert, trinn)
    ovre_grense_kw, trinn_na_kr = trinn[idx]
    er_hoyeste = idx == len(trinn) - 1

    trinn_neste_kr = None if er_hoyeste else trinn[idx + 1][1]
    kostnad_neste_trinn_kr = 0 if trinn_neste_kr is None else trinn_neste_kr - trinn_na_kr

    under_terskel_kw: float | None = None
    if idx > 0:
        under_terskel_kw, under_kr = trinn[idx - 1]
        besparelse_trinn_under_kr = trinn_na_kr - under_kr
        trinn_under_oppnaelig = minste_mulige <= under_terskel_kw
        er_realistisk = trinn_under_realistisk(
            under_terskel_kw=under_terskel_kw,
            daily_max_kw=daily_max_kw,
            forrige_maaned_topp_3_kw=forrige_maaned_topp_3_kw,
        )
    else:
        besparelse_trinn_under_kr = 0
        trinn_under_oppnaelig = False
        er_realistisk = False

    trinn_uten_denne_timen_kr = trinn[trinn_indeks(minste_mulige, trinn)][1]

    return KostnadInfo(
        kostnad_neste_trinn_kr=kostnad_neste_trinn_kr,
        trinn_na_kr=trinn_na_kr,
        # float("inf") er ugyldig JSON og knekker recorder og websocket
        trinn_na_ovre_grense_kw=None if math.isinf(ovre_grense_kw) else ovre_grense_kw,
        trinn_neste_kr=trinn_neste_kr,
        besparelse_trinn_under_kr=besparelse_trinn_under_kr,
        trinn_under_terskel_kw=under_terskel_kw,
        trinn_under_oppnaelig=trinn_under_oppnaelig,
        trinn_under_realistisk=er_realistisk,
        # Klemmen mot null er en sikring mot egendefinerte trinn-tabeller der
        # prisen ikke stiger med terskelen. Med en sortert tabell er differansen
        # aldri negativ, for det projiserte snittet ligger aldri under skranken.
        kostnad_denne_timen_kr=max(0, trinn_na_kr - trinn_uten_denne_timen_kr),
        topp_3_projisert_kw=round(topp_3_projisert, 3),
        minste_mulige_topp_3_kw=round(minste_mulige, 3),
        hoyeste_trinn=er_hoyeste,
    )


def kortvarig_paaslag_kw(*, elapsed_h: float) -> float:
    """Hvor mye av projeksjonen som kan være en last som ikke varer timen ut.

    En last på P kW som slås på ved `e0` løfter projeksjonen med `P * (1 - e0)`
    og holder den der så lenge den går, mens den ekte virkningen på time-snittet
    bare er `P * varigheten`. Ved minutt to er de to nesten like store, ved
    minutt femti er framskrivningen en sjettedel. Fradraget følger derfor samme
    form: `KORTVARIG_LAST_KW * (1 - elapsed_h)`, altså akkurat det en last på
    den størrelsen ville lagt på om den ble slått på nå, og null når timen er
    omme og projeksjonen er målt faktum.

    At fradraget krymper i takt med resten av timen er også det som gjør at
    varselet kommer tidsnok: et kutt på `KORTVARIG_LAST_KW` eller mer rekker
    alltid å hente inn overskridelsen når fradraget endelig slipper taket, for
    begge skalerer med `1 - elapsed_h`. Avveiningen står i docs/beregninger.md.
    """
    return KORTVARIG_LAST_KW * max(0.0, 1.0 - elapsed_h)


@dataclass(frozen=True)
class Kuttkriterium:
    """Svaret på «koster denne timen noe når vi ikke tror på en kortvarig topp».

    `oppfylt` er det eneste som gater kutt. De to andre feltene er
    mellomregningen, eksponert så et kutt kan forklares i ettertid.
    """

    oppfylt: bool
    varig_projeksjon_kw: float
    kortvarig_paaslag_kw: float


def vurder_kuttkriterium(
    *,
    trinn: Trinn,
    daily_max_kw: Mapping[date, float],
    today: date,
    projected_kw: float,
    actual_kwh_this_hour: float,
    elapsed_h: float,
) -> Kuttkriterium:
    """Flytter denne timen kapasitetstrinnet, også uten en kortvarig topp?

    Kriteriet for å kutte er kroner, ikke geometri: `kostnad_denne_timen_kr` er
    prisen timen er i ferd med å låse inn, og er den null, er timen gratis
    uansett hvor dramatisk projeksjonen ser ut. Topp-3-regelen gjør at de fleste
    timer er nettopp det.

    Prisen regnes av `varig_projeksjon_kw`, som er projeksjonen minus
    `kortvarig_paaslag_kw`. Gulvet er kilowattimene timen alt har brukt: de kan
    ikke kuttes bort igjen, så fradraget skal aldri ta oss under dem.
    """
    paaslag = kortvarig_paaslag_kw(elapsed_h=elapsed_h)
    varig = max(actual_kwh_this_hour, projected_kw - paaslag)
    kostnad = compute_kostnad(
        trinn=trinn,
        daily_max_kw=daily_max_kw,
        today=today,
        projected_kw=varig,
    )
    return Kuttkriterium(
        oppfylt=kostnad is not None and kostnad.kostnad_denne_timen_kr > 0,
        varig_projeksjon_kw=varig,
        kortvarig_paaslag_kw=paaslag,
    )
