"""SVG-generator for skiven paa effektmaaleren.

Ren modul uten Home Assistant-import, slik at den kan brukes tre steder:
dashboard-kortet (som roterer visere i SVG-en), eksportscriptet for fysisk
trykk, og testene. Geometrien ligger i data-attributter paa rot-elementet
slik at kortet regner ut viservinkler uten aa duplisere skalaen.

Koordinatsystemet er viewBox 0 0 1000 1000 der en enhet er 0,1 mm paa en
100 mm plate, saa filen kan tas rett inn i CAD med kjent skala.

Skivene ligger i STILER. En stil er en oppfoering med skalaform, hovedtall-
regel, tekstblokk, bunnfelt, palett og kabinettdetaljer, saa en ny skive er
en ny oppfoering og ikke en ny gren gjennom filen.
"""

from __future__ import annotations

import itertools
import logging
import math
from typing import Final, Literal, NamedTuple
from xml.sax.saxutils import escape

_LOGGER = logging.getLogger(__name__)

Variant = Literal["card", "print"]

# --- Geometri (data-kontrakt mot kortet) ---------------------------------

VIEWBOX: Final = 1000.0
NAV_X: Final = 500.0
NAV_Y: Final = 790.0
VINKEL_START: Final = -50.0
VINKEL_SVEIP: Final = 100.0
MAKS_KW_STANDARD: Final = 15.0

# --- Geometri (intern tegning) -------------------------------------------
#
# Tre konsentriske lag utenfra og inn, som paa originalene: kr-band, hovedtall,
# delstreker. Tallene ligger altsaa utenfor buen, ikke inni den.

R_SKALA: Final = 440.0  # buen viserspissen naar
R_HOVEDMERKE: Final = 44.0  # lengde innover fra buen
R_DELMERKE: Final = 19.0
R_SLEPE_INN: Final = R_SKALA + 6.0
R_SLEPE_UT: Final = R_SKALA + 28.0
R_TALL: Final = R_SKALA + 60.0
R_TRINN_INN: Final = R_SKALA + 96.0
R_TRINN_UT: Final = R_SKALA + 120.0
R_TRINN_BUE: Final = R_SKALA + 108.0
R_TRINN_TEKST: Final = R_SKALA + 148.0
# Viserspissene maa naa skalaen for at avlesningen skal vaere mulig: den svarte
# krysser buen, den roede kilen stopper i innkanten av delstrek-baandet.
R_VISER_SVART: Final = R_SKALA + 2.0
R_VISER_ROD: Final = R_SKALA - R_DELMERKE + 2.0

HUB_R: Final = 40.0
RAMME_INNSLAG: Final = 14.0

# Kabinettet er ikke et rett kvadrat: overkanten buer svakt oppover og alle
# hjoerner er kurvede.
KABINETT_TOPP: Final = 44.0
KABINETT_HJORNE: Final = 36.0
KABINETT_BUE: Final = 34.0

# Bunnfeltet dekker nedre del av kabinettet og begynner rett under
# produsentlinjen. Navet ligger like ved overkanten av feltet, slik
# originalene er bygget, og da er det plass til to stablede skruer under det
# i loddaksen, der viseren aldri kommer. Alt som skal leses ligger over det. Paa originalene ligger
# navet og viserroettene bak feltet, saa card-varianten legger det over dem med
# delvis gjennomsikt. Trykkvarianten har det som flat bunnflate.
FELT_INNSLAG: Final = 32.0
FELT_BUNN: Final = 26.0
FELT_DEKK: Final = 0.34

DELSTREKER_PER_HOVEDMERKE: Final = 5

# Skalatopper som gir hele hovedtall, med steget mellom dem: (topp, steg).
# Hovedtallene utledes av toppen, ikke omvendt, saa 10 kW gir 0 2 4 6 8 10 slik
# GEHA-originalen har det, og 15 kW gir fortsatt 0 3 6 9 12 15.
SKALATOPPER_SMAA: Final = ((3.0, 1.0), (4.0, 1.0), (5.0, 1.0), (6.0, 2.0), (8.0, 2.0))
# Fra 10 og opp gjentar trappen seg per dekade, saa 100 kW faar samme form som
# 10 kW. Alle stegene her gaar opp i hele tall naar de ganges med en tierpotens.
SKALATOPPER: Final = (
    (10.0, 2.0),
    (12.0, 3.0),
    (15.0, 3.0),
    (20.0, 4.0),
    (25.0, 5.0),
    (30.0, 6.0),
    (40.0, 8.0),
    (50.0, 10.0),
    (60.0, 12.0),
    (80.0, 16.0),
)
MAKS_KW_TAK: Final = 8.0e5  # oeverste trinn i trappen etter fem dekader

# Hovedtall-stigen for komprimerte skalaer: runde tall som blir glissnere der
# skalaen trykkes sammen, slik instrumentmakerne gjorde det.
TALLSTIGE: Final = (
    1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0,
    10.0, 12.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0, 60.0, 80.0,
    100.0, 120.0, 150.0, 200.0, 250.0, 300.0, 400.0, 500.0,
)  # fmt: skip
MIN_TALLAVSTAND_GRADER: Final = 7.5
# Vinkelavstand er ikke nok alene: "12" er tre ganger saa bredt som "3", og paa
# en lav skalatopp havner de brede merkelappene naer hverandre. Luften er maalt
# i samme enheter som resten av tegningen, langs R_TALL.
TALL_LUFT: Final = 6.0
DELSTREKSTIGE: Final = (0.1, 0.2, 0.25, 0.5, 1.0, 2.0, 5.0)
MIN_DELSTREK_GRADER: Final = 1.6

# --- Typografi ------------------------------------------------------------

GROTESK: Final = "'Helvetica Neue', Helvetica, Arial, 'Liberation Sans', sans-serif"
# Originalene har en bred, noektern bokstavform i kW, ikke en antikva med tykke
# seriffer. Slab der den finnes, ellers grotesk med vekt.
SLAB: Final = f"Rockwell, 'Roboto Slab', 'Zilla Slab', {GROTESK}"

HOVEDTALL_STORRELSE: Final = 56.0
TEKST_KR_STORRELSE: Final = 30.0
TEKST_KR_MINSTE: Final = 19.0
TEKST_KR_SPERRING: Final = 2.0

# --- Palett ---------------------------------------------------------------
#
# Rollenavn, ikke fargenavn: kortets shadow-DOM definerer de samme rollene
# som CSS custom properties. Kontrasten mot emalje er maalt (WCAG):
# trykk 12,8:1, viserrod 5,9:1, krom-mork 3,2:1. Stiler overstyrer enkeltroller
# i sin egen palett.

PALETT: Final[dict[str, str]] = {
    "emalje": "#ece3d0",
    "emalje-slitt": "#e2d8c2",
    "trykk": "#241f19",
    "viserrod": "#a32026",
    "krom-lys": "#e6e4df",
    "krom-mork": "#7e7c75",
    "skygge": "#b6ae9a",
    "prisme-lys": "#d7d9d5",
    "prisme-mork": "#a7aaa5",
    "prisme-glans": "#eef0ec",
    "deksel-kant": "#8f8878",
    "deksel-glans": "#ffffff",
    "deksel-gulning": "#d9c27f",
}

PALETT_GOSSEN: Final[dict[str, str]] = {
    # Kaldere hvit skive; gulningen ligger i plasten, ikke i trykket.
    "emalje": "#f0f1ed",
    "emalje-slitt": "#e5e6e2",
    "prisme-lys": "#d2d5d2",
    "prisme-mork": "#a2a6a3",
}


def _n(verdi: float) -> str:
    """Kompakt, deterministisk tallformat for SVG-attributter."""
    tekst = f"{verdi:.2f}".rstrip("0").rstrip(".")
    return "0" if tekst in {"", "-0"} else tekst


def _polar(vinkel: float, radius: float) -> tuple[float, float]:
    """Punkt paa skalaen. Vinkel i grader fra loddlinjen, positivt med klokken."""
    rad = math.radians(vinkel)
    return NAV_X + radius * math.sin(rad), NAV_Y - radius * math.cos(rad)


def _bue(radius: float, fra: float, til: float) -> str:
    x1, y1 = _polar(fra, radius)
    x2, y2 = _polar(til, radius)
    stor = 1 if abs(til - fra) > 180 else 0
    med_klokken = 1 if til >= fra else 0
    return f"M {_n(x1)} {_n(y1)} A {_n(radius)} {_n(radius)} 0 {stor} {med_klokken} {_n(x2)} {_n(y2)}"


def _radiell_strek(vinkel: float, r_indre: float, r_ytre: float) -> str:
    x1, y1 = _polar(vinkel, r_indre)
    x2, y2 = _polar(vinkel, r_ytre)
    return f"M {_n(x1)} {_n(y1)} L {_n(x2)} {_n(y2)}"


def _fra_trappen(maks_kw: float) -> tuple[float, float]:
    """Laveste trinn i trappen som rommer verdien. Over hoeyeste trinn blir det taket."""
    for topp, steg in SKALATOPPER_SMAA:
        if maks_kw <= topp:
            return topp, steg
    faktor = 1.0
    while True:
        for topp, steg in SKALATOPPER:
            if maks_kw <= topp * faktor:
                return topp * faktor, steg * faktor
        if faktor * SKALATOPPER[-1][0] >= MAKS_KW_TAK:
            return SKALATOPPER[-1][0] * faktor, SKALATOPPER[-1][1] * faktor
        faktor *= 10


def skalatopp(maks_kw: float) -> tuple[float, float]:
    """Skalatoppen som rommer verdien, og steget mellom hovedtallene.

    Trappen velges oppover og aldri nedover: en topp under den oppgitte verdien
    ville gjort brukerens egen toppeffekt uleselig. Treffer verdien en topp i
    trappen, brukes den som den er. Ellers sier loggen fra, for en stille
    endring av oppsettet er verre enn en beskjed.
    """
    if not math.isfinite(maks_kw) or maks_kw <= 0:
        _LOGGER.warning("maks_kw %s duger ikke; skiven tegnes med %g kW", maks_kw, MAKS_KW_STANDARD)
        maks_kw = MAKS_KW_STANDARD
    valgt = _fra_trappen(maks_kw)
    if valgt[0] != maks_kw:
        _LOGGER.warning(
            "maks_kw %g kW er ingen lesbar skalatopp; skiven tegnes med %g kW og hovedtall hvert %g kW",
            maks_kw,
            valgt[0],
            valgt[1],
        )
    return valgt


def normaliser_maks_kw(maks_kw: float) -> float:
    """Skalatoppen som brukes for en oppgitt maks_kw. Se skalatopp()."""
    return skalatopp(maks_kw)[0]


def vinkel_for_kw(
    kw: float,
    maks_kw: float,
    *,
    min_kw: float = 0.0,
    eksponent: float = 1.0,
    sokkel_kw: float = 0.0,
    sokkel_andel: float = 0.0,
) -> float:
    """Viservinkel for en effekt. Samme formel som kortet bruker.

    Kortet leser min_kw, eksponent, sokkel_kw og sokkel_andel av data-
    attributtene paa rot-elementet og regner det samme uttrykket, saa lineaere
    og komprimerte skalaer havner paa samme sted i kort, trykk og test.

    eksponent 1 uten sokkel gir en lineaer skala. Sokkelen er et sammentrykt
    stykke nederst: alt under sokkel_kw deler paa sokkel_andel av sveipet, og
    resten av skalaen foelger potensformen over. Dreiejernskivene bruker den
    slik at de laveste kapasitetstrinnene blir med uten at formen ryker.
    """
    if maks_kw <= min_kw:
        raise ValueError(f"maks_kw {maks_kw} maa vaere stoerre enn min_kw {min_kw}")
    klemt = max(kw, min_kw)
    # math.pow framfor ** saa typen blir float og ikke Any.
    if sokkel_kw > min_kw and sokkel_andel > 0:
        if klemt <= sokkel_kw:
            andel = sokkel_andel * (klemt - min_kw) / (sokkel_kw - min_kw)
        else:
            nedre = math.pow(sokkel_kw, eksponent)
            spenn = math.pow(maks_kw, eksponent) - nedre
            andel = sokkel_andel + (1 - sokkel_andel) * (math.pow(klemt, eksponent) - nedre) / spenn
    else:
        spenn = math.pow(maks_kw, eksponent) - math.pow(min_kw, eksponent)
        andel = (math.pow(klemt, eksponent) - math.pow(min_kw, eksponent)) / spenn
    return VINKEL_START + andel * VINKEL_SVEIP


class Skala(NamedTuple):
    """Utledet skala for en konkret skive."""

    min_kw: float
    maks_kw: float
    eksponent: float
    hovedtall: tuple[float, ...]
    sokkel_kw: float = 0.0
    sokkel_andel: float = 0.0

    def vinkel(self, kw: float) -> float:
        return vinkel_for_kw(
            kw,
            self.maks_kw,
            min_kw=self.min_kw,
            eksponent=self.eksponent,
            sokkel_kw=self.sokkel_kw,
            sokkel_andel=self.sokkel_andel,
        )


class Tekstlinje(NamedTuple):
    """En linje i tekstblokken. {dso}, {min} og {maks} fylles inn ved tegning."""

    x: float
    y: float
    mal: str
    storrelse: float
    familie: str = GROTESK
    vekt: str | None = None
    sperring: float | None = None
    anker: str = "middle"


class Symbol(NamedTuple):
    """Et merke i ikonrekken. Se _symbolbane for hva hvert av dem betyr."""

    art: Literal["maaleverk", "veksel", "loddrett", "stjerne"]
    x: float
    y: float
    verdi: str = ""


class Bunnfelt(NamedTuple):
    """Feltet nederst paa kabinettet."""

    moenster: Literal["kryss", "riller"]
    topp: float
    skruer: tuple[float, ...]  # y-posisjoner i loddaksen
    skrue_r: float


class Stil(NamedTuple):
    """En skivevariant. Ny skive er en ny oppfoering her, ikke en ny gren i koden."""

    navn: str
    maaleverk: Literal["dreispole", "dreiejern"]
    eksponent: float
    sokkel_andel: float
    hovedtall_regel: Literal["jevn", "stige"]
    delstrek_regel: Literal["antall", "steg"]
    bunnfelt: Bunnfelt
    symboler: tuple[Symbol, ...]
    tekst: tuple[Tekstlinje, ...]
    palett: dict[str, str]
    slitasje: bool
    gulning: float


STILER: Final[dict[str, Stil]] = {
    "geha": Stil(
        navn="GEHA-METER",
        maaleverk="dreispole",
        eksponent=1.0,
        sokkel_andel=0.0,
        hovedtall_regel="jevn",
        delstrek_regel="antall",
        bunnfelt=Bunnfelt(moenster="kryss", topp=760.0, skruer=(872.0, 930.0), skrue_r=22.0),
        # GEHA-skiven har dreiejernsymbolet og klassemerket. Originalfotoet har
        # noe gulaktig rett ved KL.1.5 som kan vaere en proevespenningsstjerne,
        # men det er ikke lesbart nok til aa slaa fast, saa den er utelatt.
        symboler=(Symbol("maaleverk", 124.0, 690.0),),
        tekst=(
            Tekstlinje(500, 92, "{dso}", 24, vekt="500", sperring=6),
            Tekstlinje(500, 570, "KW", 86, familie=SLAB, vekt="700", sperring=10),
            Tekstlinje(500, 644, "GEHA-METER", 34, vekt="600", sperring=8),
            Tekstlinje(898, 698, "KL.1,5", 30, sperring=2, anker="end"),
        ),
        palett={},
        slitasje=True,
        gulning=0.0,
    ),
    "gossen": Stil(
        navn="GOSSEN",
        maaleverk="dreiejern",
        # Dreiejernskalaen paa originalen er trykket sammen mot toppen og
        # starter ved foerste brukbare verdi, ikke ved null.
        eksponent=0.5,
        # Originalen starter paa 2 fordi dreiejernet ikke leser lavere. Vi har
        # ikke den begrensningen, saa i stedet klemmes alt under foerste terskel
        # inn i en tiendedel av sveipet. Da er alle kapasitetstrinn med, og
        # formen er fortsatt Gossens: sammentrykt mot toppen.
        sokkel_andel=0.1,
        hovedtall_regel="stige",
        delstrek_regel="steg",
        bunnfelt=Bunnfelt(moenster="riller", topp=760.0, skruer=(872.0, 930.0), skrue_r=22.0),
        # Ikonrekken er delt i to fordi midten av skiven sveipes av viseren:
        # maaleverk, stroemart og bruksstilling til venstre, klasse og
        # proevespenning til hoeyre.
        symboler=(
            Symbol("maaleverk", 90.0, 690.0),
            Symbol("veksel", 164.0, 690.0),
            Symbol("loddrett", 216.0, 690.0),
            Symbol("stjerne", 886.0, 690.0, verdi="2"),
        ),
        tekst=(
            Tekstlinje(500, 556, "kW", 84, familie=SLAB, vekt="700", sperring=4),
            Tekstlinje(500, 622, "100 mA", 34, vekt="500", sperring=4),
            Tekstlinje(790, 690, "1,5", 28, sperring=2),
            Tekstlinje(880, 738, "{dso}", 28, vekt="600", sperring=4, anker="end"),
        ),
        palett=PALETT_GOSSEN,
        slitasje=False,
        gulning=0.16,
    ),
}


def _valider_stil(navn: str, stil: Stil) -> None:
    """Maaleverk og skalaform hoerer parvis sammen, og maa ikke kunne sprike.

    Dreispole er lineaert, dreiejern er ikke det. Har en stil dreispolesymbol og
    komprimert skala, eller omvendt, er skiven selvmotsigende. Det var nettopp
    den feilen GEHA-skiven hadde foer den ble rettet, saa den fanges her.
    """
    lineaer = stil.eksponent == 1.0 and stil.sokkel_andel == 0.0
    if stil.maaleverk == "dreispole" and not lineaer:
        raise ValueError(f"{navn}: dreispole er lineaert, men skalaen er komprimert")
    if stil.maaleverk == "dreiejern" and lineaer:
        raise ValueError(f"{navn}: dreiejern er ikke-lineaert, men skalaen er lineaer")


for _navn, _stil in STILER.items():
    _valider_stil(_navn, _stil)

STILNAVN: Final = tuple(STILER)


def tilgjengelige_stiler() -> dict[str, str]:
    """Stil-id mot visningsnavn, for export-scriptet og kortets konfigurasjon."""
    return {nokkel: stil.navn for nokkel, stil in STILER.items()}


def _farge(rolle: str, stil: Stil | None = None) -> str:
    if stil is not None and rolle in stil.palett:
        return stil.palett[rolle]
    return PALETT[rolle]


def _forste_terskel(kapasitetstrinn: list[tuple[float, int]], maks_kw: float) -> float:
    for terskel, _ in kapasitetstrinn:
        if math.isfinite(terskel) and 0 < terskel < maks_kw:
            return terskel
    return 0.0


def _jevne_hovedtall(min_kw: float, maks_kw: float, steg: float) -> tuple[float, ...]:
    """Hovedtall med fast avstand fra bunnen til toppen av skalaen."""
    antall = round((maks_kw - min_kw) / steg)
    return tuple(min_kw + i * steg for i in range(antall + 1))


def _merkelappbredde(kw: float) -> float:
    """Bredden merkelappen legger beslag paa langs skalaen, med luft paa hver side."""
    return _tekstbredde(_tall_tekst(kw), HOVEDTALL_STORRELSE, 0.0) + TALL_LUFT


def _stigehovedtall(
    min_kw: float, maks_kw: float, eksponent: float, sokkel: tuple[float, float] = (0.0, 0.0)
) -> tuple[float, ...]:
    """Runde tall fra stigen, med nok vinkelavstand til at de ikke kolliderer."""

    def vinkel(kw: float) -> float:
        return vinkel_for_kw(
            kw, maks_kw, min_kw=min_kw, eksponent=eksponent, sokkel_kw=sokkel[0], sokkel_andel=sokkel[1]
        )

    def har_plass(forrige: float, kandidat: float) -> bool:
        krav = math.degrees((_merkelappbredde(forrige) + _merkelappbredde(kandidat)) / 2 / R_TALL)
        return vinkel(kandidat) - vinkel(forrige) >= max(MIN_TALLAVSTAND_GRADER, krav)

    # Sokkelen er et sammentrykt stykke, ikke et omraade med egne runde tall:
    # den faar bare start og terskelen den ender paa, ellers hadde stigen lagt
    # 1,5 og 2,5 inn der 2 og 3 hoerer hjemme.
    nedre = max(min_kw, sokkel[0])
    valgt = [min_kw] if nedre == min_kw else [min_kw, nedre]
    for kandidat in TALLSTIGE:
        if kandidat <= nedre or kandidat >= maks_kw:
            continue
        if har_plass(valgt[-1], kandidat):
            valgt.append(kandidat)
    while len(valgt) > 1 and not har_plass(valgt[-1], maks_kw):
        valgt.pop()
    valgt.append(maks_kw)
    return tuple(valgt)


def lag_skala(stil: Stil, kapasitetstrinn: list[tuple[float, int]], maks_kw: float) -> Skala:
    """Utled skalaen av stilen og brukerens kapasitetstrinn."""
    maks, steg = skalatopp(maks_kw)
    sokkel_kw = 0.0
    sokkel_andel = 0.0
    if stil.sokkel_andel > 0:
        # Sokkelen ender paa foerste terskel, men aldri saa hoeyt at den spiser
        # skalaen: en femtedel av toppverdien er taket.
        sokkel_kw = min(_forste_terskel(kapasitetstrinn, maks), maks / 5)
        sokkel_andel = stil.sokkel_andel if sokkel_kw > 0 else 0.0
    if stil.hovedtall_regel == "jevn":
        hovedtall = _jevne_hovedtall(0.0, maks, steg)
    else:
        hovedtall = _stigehovedtall(0.0, maks, stil.eksponent, (sokkel_kw, sokkel_andel))
    return Skala(
        min_kw=0.0,
        maks_kw=maks,
        eksponent=stil.eksponent,
        hovedtall=hovedtall,
        sokkel_kw=sokkel_kw,
        sokkel_andel=sokkel_andel,
    )


def _delstreker(skala: Skala, regel: str) -> list[float]:
    """kW-verdiene delstrekene skal staa paa.

    "antall" deler hvert hovedintervall i like mange biter, som paa en lineaer
    skala gir jevn avstand. "steg" velger minste steg fra stigen som fortsatt
    gir lesbar avstand, saa strekene blir tette der skalaen er trukket ut og
    glissne der den er trykket sammen.
    """
    verdier: list[float] = []
    for fra, til in itertools.pairwise(skala.hovedtall):
        spenn_grader = skala.vinkel(til) - skala.vinkel(fra)
        if regel == "antall":
            antall = DELSTREKER_PER_HOVEDMERKE + 1
        else:
            antall = 0
            for steg in DELSTREKSTIGE:
                kandidat = round((til - fra) / steg)
                if kandidat < 2:
                    continue
                if spenn_grader / kandidat >= MIN_DELSTREK_GRADER:
                    antall = kandidat
                    break
            if antall == 0:
                continue
        for i in range(1, antall):
            verdier.append(fra + (til - fra) * i / antall)
    return verdier


def _segmenter(kapasitetstrinn: list[tuple[float, int]], skala: Skala) -> list[tuple[float, float, int, float | None]]:
    """Band mellom tersklene: (fra_kw, til_kw, kr, terskel_i_skala_eller_None).

    Naar skalaen starter over null (komprimerte stiler) faller trinnene under
    startverdien utenfor skiven. Det er aerlig: skiven kan ikke vise dem.
    """
    segmenter: list[tuple[float, float, int, float | None]] = []
    fra = skala.min_kw
    for terskel, kr in kapasitetstrinn:
        if fra >= skala.maks_kw:
            break
        til = min(terskel, skala.maks_kw) if math.isfinite(terskel) else skala.maks_kw
        if til <= fra:
            continue
        i_skala = terskel if math.isfinite(terskel) and terskel <= skala.maks_kw else None
        segmenter.append((fra, til, kr, i_skala))
        fra = til
    return segmenter


def _tekstbredde(tekst: str, storrelse: float, sperring: float) -> float:
    """Grov bredde for grotesk i versaler. Brukes bare til aa tilpasse merkelapper."""
    return len(tekst) * storrelse * 0.62 + max(len(tekst) - 1, 0) * sperring


def _tilpasset_storrelse(tekst: str, plass: float) -> float | None:
    """Stoerste skriftstoerrelse som holder seg innenfor plassen, eller None om den blir for smaa."""
    storrelse = TEKST_KR_STORRELSE
    while storrelse >= TEKST_KR_MINSTE:
        if _tekstbredde(tekst, storrelse, TEKST_KR_SPERRING) <= plass:
            return storrelse
        storrelse -= 1.0
    return None


# Versalhoeyden er om lag 0,7 em; halve den loefter grunnlinjen slik at y blir
# den optiske midten. dominant-baseline er ikke brukt, for librsvg og nettlesere
# behandler den ulikt, og da ville kortet og trykket sprike.
VERSAL_SENTER: Final = 0.35


def _tekst(
    x: float,
    y_senter: float,
    innhold: str,
    *,
    storrelse: float,
    familie: str = GROTESK,
    vekt: str | None = None,
    sperring: float | None = None,
    anker: str = "middle",
    rotasjon: float | None = None,
    stil: Stil | None = None,
) -> str:
    """Tekst plassert etter optisk midte, ikke grunnlinje."""
    deler = [
        f'<text x="{_n(x)}" y="{_n(y_senter + storrelse * VERSAL_SENTER)}"',
        f' font-family="{familie}" font-size="{_n(storrelse)}"',
    ]
    if vekt:
        deler.append(f' font-weight="{vekt}"')
    if sperring:
        deler.append(f' letter-spacing="{_n(sperring)}"')
    deler.append(f' fill="{_farge("trykk", stil)}" text-anchor="{anker}"')
    if rotasjon is not None:
        deler.append(f' transform="rotate({_n(rotasjon)} {_n(x)} {_n(y_senter)})"')
    deler.append(f">{escape(innhold)}</text>")
    return "".join(deler)


def kabinettbane(innslag: float = 0.0) -> str:
    """Omrisset av kabinettet: svakt buet overkant og kurvede hjoerner, ikke et rett kvadrat."""
    v = innslag
    h = VIEWBOX - innslag
    b = VIEWBOX - innslag
    topp = KABINETT_TOPP + innslag
    hj = KABINETT_HJORNE
    return (
        f"M {_n(v)} {_n(topp + hj)}"
        f" Q {_n(v)} {_n(topp)} {_n(v + hj)} {_n(topp)}"
        f" Q {_n(VIEWBOX / 2)} {_n(topp - 2 * KABINETT_BUE)} {_n(h - hj)} {_n(topp)}"
        f" Q {_n(h)} {_n(topp)} {_n(h)} {_n(topp + hj)}"
        f" L {_n(h)} {_n(b - hj)}"
        f" Q {_n(h)} {_n(b)} {_n(h - hj)} {_n(b)}"
        f" L {_n(v + hj)} {_n(b)}"
        f" Q {_n(v)} {_n(b)} {_n(v)} {_n(b - hj)} Z"
    )


def _plate(variant: Variant, stil: Stil) -> list[str]:
    """Skiveflaten i kabinettform med flat to-tone kromramme."""
    ut = [
        f'<path id="kabinett" d="{kabinettbane()}" fill="{_farge("emalje", stil)}"/>',
    ]
    if variant == "card" and stil.slitasje:
        ut.extend(_slitasje(stil))
    ut.extend(
        [
            f'<path d="{kabinettbane(RAMME_INNSLAG)}" fill="none"'
            f' stroke="{_farge("krom-lys", stil)}" stroke-width="12"/>',
            f'<path d="{kabinettbane(RAMME_INNSLAG + 9)}" fill="none"'
            f' stroke="{_farge("krom-mork", stil)}" stroke-width="3"/>',
        ]
    )
    return ut


def _slitasje(stil: Stil) -> list[str]:
    """Haandplasserte slitasjeflekker i slitt emalje. Ingen tilfeldighet, samme fil hver gang."""
    flekker = [
        (
            "M 58 142 q 62 -40 118 -28 q 74 14 96 -2 q 32 -22 46 14 q 14 38 -72 44 q -98 8 -156 22 q -50 12 -32 -50 Z",
            0.3,
        ),
        (
            "M 786 188 q 58 -34 118 -20 q 52 12 66 -6 q 18 -22 22 12 q 4 34 -78 38 q -84 4 -118 14 q -32 8 -10 -38 Z",
            0.24,
        ),
        ("M 604 452 q 84 -30 118 -6 q 26 18 -18 32 q -54 18 -96 4 q -30 -10 -4 -30 Z", 0.2),
    ]
    ut = [f'<path d="{d}" fill="{_farge("emalje-slitt", stil)}" opacity="{_n(dekk)}"/>' for d, dekk in flekker]
    skrammer = [
        ("M 214 318 q 96 46 186 34", 2.0, 0.28),
        ("M 660 828 q 74 -32 158 -18", 1.6, 0.22),
        ("M 318 906 q 58 22 122 12", 1.4, 0.2),
        ("M 742 352 q 44 62 58 130", 1.8, 0.24),
    ]
    ut.extend(
        f'<path d="{d}" fill="none" stroke="{_farge("skygge", stil)}" stroke-width="{_n(bredde)}"'
        f' stroke-linecap="round" opacity="{_n(dekk)}"/>'
        for d, bredde, dekk in skrammer
    )
    ut.append(
        f'<path d="{kabinettbane(13)}" fill="none" stroke="{_farge("skygge", stil)}" stroke-width="26" opacity="0.18"/>'
    )
    return ut


def _tall_tekst(kw: float) -> str:
    return _n(kw).replace(".", ",")


def _skala_tegning(skala: Skala, stil: Stil) -> list[str]:
    """Bue, hovedmerker, delstreker og hovedtall."""
    ut = [
        f'<path d="{_bue(R_SKALA, VINKEL_START, VINKEL_START + VINKEL_SVEIP)}" fill="none"'
        f' stroke="{_farge("trykk", stil)}" stroke-width="5"/>',
    ]

    fine = [
        _radiell_strek(skala.vinkel(kw), R_SKALA - R_DELMERKE, R_SKALA)
        for kw in _delstreker(skala, stil.delstrek_regel)
    ]
    if fine:
        ut.append(
            f'<path id="delstreker" d="{" ".join(fine)}" fill="none" stroke="{_farge("trykk", stil)}"'
            ' stroke-width="3" stroke-linecap="butt"/>'
        )

    grove = [_radiell_strek(skala.vinkel(kw), R_SKALA - R_HOVEDMERKE, R_SKALA) for kw in skala.hovedtall]
    ut.append(
        f'<path id="hovedmerker" d="{" ".join(grove)}" fill="none" stroke="{_farge("trykk", stil)}"'
        ' stroke-width="8" stroke-linecap="butt"/>'
    )

    for kw in skala.hovedtall:
        x, y = _polar(skala.vinkel(kw), R_TALL)
        ut.append(_tekst(x, y, _tall_tekst(kw), storrelse=HOVEDTALL_STORRELSE, vekt="600", stil=stil))
    return ut


def _trinnband(kapasitetstrinn: list[tuple[float, int]], skala: Skala, stil: Stil) -> list[str]:
    """Kapasitetstrinn: buesegment per trinn, radielle merker ved tersklene, kr/mnd utenfor."""
    segmenter = _segmenter(kapasitetstrinn, skala)
    if not segmenter:
        return []

    ut = ['<g id="trinnband">']
    terskler: list[float] = []
    for indeks, (fra, til, kr, terskel) in enumerate(segmenter):
        v_fra = skala.vinkel(fra)
        v_til = skala.vinkel(til)
        ut.append(
            f'<g id="trinn-{indeks}" data-kw-fra="{_n(fra)}" data-kw-til="{_n(til)}" data-kr="{kr}">'
            f'<path class="trinn-bue" d="{_bue(R_TRINN_BUE, v_fra + 0.7, v_til - 0.7)}" fill="none"'
            f' stroke="{_farge("trykk", stil)}" stroke-width="9" stroke-linecap="butt"/>'
        )
        tekst = f"{kr} KR"
        buelengde = math.radians(v_til - v_fra) * R_TRINN_TEKST
        storrelse = _tilpasset_storrelse(tekst, buelengde - 14)
        if storrelse is not None:
            v_midt = (v_fra + v_til) / 2
            x, y = _polar(v_midt, R_TRINN_TEKST)
            ut.append(
                _tekst(
                    x,
                    y,
                    tekst,
                    storrelse=storrelse,
                    vekt="600",
                    sperring=TEKST_KR_SPERRING,
                    rotasjon=v_midt,
                    stil=stil,
                )
            )
        ut.append("</g>")
        if terskel is not None:
            terskler.append(terskel)

    if terskler:
        merker = [_radiell_strek(skala.vinkel(kw), R_TRINN_INN, R_TRINN_UT) for kw in terskler]
        ut.append(
            f'<path id="trinnmerker" d="{" ".join(merker)}" fill="none"'
            f' stroke="{_farge("trykk", stil)}" stroke-width="6" stroke-linecap="butt"/>'
        )
    ut.append("</g>")
    return ut


def _stjernebane(ytre: float) -> str:
    """Femtakket stjerne, spiss opp."""
    indre = ytre * 0.42
    punkter: list[str] = []
    for i in range(10):
        radius = ytre if i % 2 == 0 else indre
        vinkel = math.radians(-90 + i * 36)
        punkter.append(f"{_n(radius * math.cos(vinkel))} {_n(radius * math.sin(vinkel))}")
    return "M " + " L ".join(punkter) + " Z"


def _symbolbane(symbol: Symbol, stil: Stil) -> str:
    """Ett merke fra ikonrekken.

    Betydningene er fra Fredrik og en kollega som kjenner instrumentene. IEC
    60051 ligger bak betalingsmur, saa dette lar seg ikke slaa opp fritt, og da
    maa det staa her:

    maaleverk: opp-ned U, og streken avgjoer hvilket verk det er. Strek under
        buen er dreispole (permanentmagnet, dreiespole), strek inni buen er
        dreiejern. De to hoerer parvis sammen med skalaformen: dreispole er
        lineaert, dreiejern er det ikke. GEHA har jevn skala og dreispole,
        Gossen har sammentrykt skala og dreiejern, og _valider_stil passer paa
        at en ny stil ikke kan faa symbol og skalaform som motsier hverandre.
        Det fysiske bygget vaart bruker dreispoleverk, siden det er det som lar
        seg drive fra DC, saa GEHA-skiva baerer riktig symbol for verket den
        sitter paa. En Gossen-skive paa samme verk ville ikke gjort det.
    veksel: tilde, altsaa vekselstroem.
    loddrett: ⊥, instrumentet skal henge loddrett.
    stjerne: isolasjonsproevespenning, og tallet inni er antall kV.
    """
    blekk = _farge("trykk", stil)
    if symbol.art == "maaleverk":
        bue = (
            '<path d="M -36 32 L -36 -6 A 36 36 0 0 1 36 -6 L 36 32" fill="none"'
            f' stroke="{blekk}" stroke-width="11" stroke-linecap="butt"/>'
        )
        if stil.maaleverk == "dreispole":
            return bue + f'<rect x="-30" y="42" width="60" height="11" fill="{blekk}"/>'
        return bue + f'<rect x="-6" y="-14" width="12" height="46" fill="{blekk}"/>'

    if symbol.art == "veksel":
        return (
            '<path d="M -24 6 C -16 -16 -8 -16 0 0 C 8 16 16 16 24 -6" fill="none"'
            f' stroke="{blekk}" stroke-width="6" stroke-linecap="round"/>'
        )
    if symbol.art == "loddrett":
        return f'<path d="M 0 -24 V 20 M -20 20 H 20" fill="none" stroke="{blekk}" stroke-width="6"/>'
    tall = _tekst(0, 2, symbol.verdi, storrelse=26, vekt="600", stil=stil)
    return f'<path d="{_stjernebane(30)}" fill="none" stroke="{blekk}" stroke-width="5" stroke-linejoin="round"/>{tall}'


def _symboler(stil: Stil) -> list[str]:
    return [
        f'<g id="symbol-{stil.maaleverk if symbol.art == "maaleverk" else symbol.art}"'
        f' transform="translate({_n(symbol.x)} {_n(symbol.y)})">'
        f"{_symbolbane(symbol, stil)}</g>"
        for symbol in stil.symboler
    ]


def _trykk_tekst(stil: Stil, skala: Skala, dso_navn: str | None) -> list[str]:
    """Tekstblokken fra stilregisteret.

    Klassemerket (KL.1,5 paa GEHA, 1,5 i ikonrekken paa Gossen) er
    noeyaktighetsklassen: inntil 1,5 prosent feil paa fullt utslag. Gossen-skiven har i tillegg
    stroemmerkingen fra originalen ("100 mA"), som hoerer til maaleverket den
    satt paa; bytt den om det fysiske bygget faar et annet verk.

    Originalinstrumentene maaler stroem, ikke effekt. Skalaen er trykket i kW
    under en antatt spenning, derav "230V" og "43.4B/0.1A" paa originalskiven.
    Den visningen glipper saa snart spenningen avviker eller effektfaktoren ikke
    er 1. Vaare skiver ser like ut, men tallene bak er ekte kW fra Home
    Assistant, saa vi arver ikke den feilkilden.

    Symbolet og klassemerket staar i lommene mellom vifta, viserens
    ytterstillinger og bunnfeltet, saa de er lesbare i alle viserstillinger.
    """
    felter = {"dso": (dso_navn or "").upper(), "min": _tall_tekst(skala.min_kw), "maks": _tall_tekst(skala.maks_kw)}
    ut: list[str] = []
    for linje in stil.tekst:
        innhold = linje.mal.format(**felter)
        if not innhold.strip():
            continue
        ut.append(
            _tekst(
                linje.x,
                linje.y,
                innhold,
                storrelse=linje.storrelse,
                familie=linje.familie,
                vekt=linje.vekt,
                sperring=linje.sperring,
                anker=linje.anker,
                stil=stil,
            )
        )
    ut.extend(_symboler(stil))
    return ut


def _diagonaler(x0: float, y0: float, x1: float, y1: float, avstand: float, stigning: int) -> str:
    """Parallelle 45-graders linjer klippet mot rektangelet, uten clipPath."""
    steg = avstand * math.sqrt(2)
    linjer: list[str] = []
    if stigning > 0:  # y = x + c
        c = y0 - x1
        while c <= y1 - x0:
            xa, xb = max(x0, y0 - c), min(x1, y1 - c)
            if xb > xa:
                linjer.append(f"M {_n(xa)} {_n(xa + c)} L {_n(xb)} {_n(xb + c)}")
            c += steg
    else:  # y = -x + c
        c = x0 + y0
        while c <= x1 + y1:
            xa, xb = max(x0, c - y1), min(x1, c - y0)
            if xb > xa:
                linjer.append(f"M {_n(xa)} {_n(c - xa)} L {_n(xb)} {_n(c - xb)}")
            c += steg
    return " ".join(linjer)


def _krysset(venstre: float, topp: float, hoyre: float, bunn: float, stil: Stil, moenster: float) -> list[str]:
    """Kryssrutet prisme, som paa GEHA."""
    avstand = 26.0
    return [
        # Lyset faller skraatt, saa den ene diagonalen staar sterkere enn den andre.
        f'<path d="{_diagonaler(venstre, topp, hoyre, bunn, avstand, 1)}" fill="none"'
        f' stroke="{_farge("prisme-mork", stil)}" stroke-width="3" opacity="{_n(0.75 * moenster)}"/>',
        f'<path d="{_diagonaler(venstre, topp, hoyre, bunn, avstand, -1)}" fill="none"'
        f' stroke="{_farge("prisme-mork", stil)}" stroke-width="2" opacity="{_n(0.45 * moenster)}"/>',
        f'<path d="{_diagonaler(venstre + avstand / 2, topp, hoyre, bunn, avstand, 1)}" fill="none"'
        f' stroke="{_farge("prisme-glans", stil)}" stroke-width="1.5" opacity="{_n(0.6 * moenster)}"/>',
    ]


def _riller(venstre: float, topp: float, hoyre: float, bunn: float, stil: Stil, moenster: float) -> list[str]:
    """Tette loddrette riller, som paa Gossen-dekselet."""
    periode = 22.0
    hoyde = bunn - topp
    mork: list[str] = []
    glans: list[str] = []
    x = venstre
    while x + periode * 0.5 <= hoyre:
        mork.append(f"M {_n(x)} {_n(topp)} h {_n(periode * 0.5)} v {_n(hoyde)} h {_n(-periode * 0.5)} Z")
        glans.append(f"M {_n(x + periode * 0.62)} {_n(topp)} v {_n(hoyde)}")
        x += periode
    return [
        f'<path d="{" ".join(mork)}" fill="{_farge("prisme-mork", stil)}" opacity="{_n(0.55 * moenster)}"/>',
        f'<path d="{" ".join(glans)}" fill="none" stroke="{_farge("prisme-glans", stil)}"'
        f' stroke-width="2" opacity="{_n(0.7 * moenster)}"/>',
    ]


def _bunnfelt(stil: Stil, variant: Variant) -> list[str]:
    """Feltet nederst: kryssrutet prisme eller loddrette riller, med skruer i loddaksen.

    Card-varianten er delvis gjennomskinnelig og tegnes etter visere og nav, slik
    at navkapselen og viserroettene skimtes bak plasten som paa originalene.
    Trykkvarianten er flat og ugjennomsiktig og ligger under trykket.
    """
    felt = stil.bunnfelt
    topp = felt.topp
    venstre = FELT_INNSLAG
    hoyre = VIEWBOX - FELT_INNSLAG
    bunn = VIEWBOX - FELT_BUNN
    bredde = hoyre - venstre
    hoyde = bunn - topp

    # Plasten slipper gjennom det som ligger bak, men moensteret skal fortsatt
    # sees. Derfor daemper card-varianten flaten mer enn selve moensteret.
    kort = variant == "card"
    flate = FELT_DEKK if kort else 1.0
    moenster = 0.8 if kort else 1.0
    ut = [
        '<g id="riflet-felt">',
        f'<rect x="{_n(venstre)}" y="{_n(topp)}" width="{_n(bredde)}"'
        f' height="{_n(hoyde)}" fill="{_farge("prisme-lys", stil)}" opacity="{_n(flate)}"/>',
    ]
    tegner = _krysset if felt.moenster == "kryss" else _riller
    ut.extend(tegner(venstre, topp, hoyre, bunn, stil, moenster))

    # Innfelt: skyggekant oeverst, lys kant rett under, tynn omriss rundt hele.
    ut.append(
        f'<rect x="{_n(venstre)}" y="{_n(topp)}" width="{_n(bredde)}" height="5" fill="{_farge("skygge", stil)}"/>'
    )
    ut.append(
        f'<rect x="{_n(venstre)}" y="{_n(topp + 5)}" width="{_n(bredde)}" height="3"'
        f' fill="{_farge("prisme-glans", stil)}"/>'
    )
    ut.append(
        f'<rect x="{_n(venstre)}" y="{_n(topp)}" width="{_n(bredde)}" height="{_n(hoyde)}" fill="none"'
        f' stroke="{_farge("krom-mork", stil)}" stroke-width="2" opacity="0.65"/>'
    )
    # Skruene staar stablet i feltets loddrette midtakse, paa en litt moerkere
    # innfelt firkant som bryter moensteret, slik originalene har det.
    if felt.skruer:
        plate_topp = min(felt.skruer) - felt.skrue_r - 12
        plate_bunn = max(felt.skruer) + felt.skrue_r + 12
        plate_bredde = (plate_bunn - plate_topp) * 0.86
        ut.append(
            f'<rect x="{_n(NAV_X - plate_bredde / 2)}" y="{_n(plate_topp)}" width="{_n(plate_bredde)}"'
            f' height="{_n(plate_bunn - plate_topp)}" fill="{_farge("prisme-mork", stil)}"'
            f' opacity="{_n(0.55 * moenster)}" stroke="{_farge("krom-mork", stil)}"'
            ' stroke-width="2" stroke-opacity="0.5"/>'
        )
    for skrue_y in felt.skruer:
        r = felt.skrue_r
        ut.append(
            f'<g class="skrue" transform="translate({_n(NAV_X)} {_n(skrue_y)})">'
            f'<circle r="{_n(r)}" fill="{_farge("krom-lys", stil)}"'
            f' stroke="{_farge("krom-mork", stil)}" stroke-width="3"/>'
            f'<rect x="{_n(-r + 3)}" y="-3" width="{_n(2 * r - 6)}" height="6"'
            f' fill="{_farge("krom-mork", stil)}"/>'
            "</g>"
        )
    ut.append("</g>")
    return ut


def _hub(variant: Variant, stil: Stil) -> list[str]:
    """Navkapsel som flate to-tone-ringer. Trykkvarianten markerer bare akselhullet."""
    if variant == "print":
        return [
            f'<g id="nav" transform="translate({_n(NAV_X)} {_n(NAV_Y)})">'
            f'<circle r="{_n(HUB_R - 22)}" fill="none" stroke="{_farge("trykk", stil)}" stroke-width="4"/>'
            "</g>"
        ]
    return [
        f'<g id="nav" transform="translate({_n(NAV_X)} {_n(NAV_Y)})">'
        f'<circle r="{_n(HUB_R)}" fill="{_farge("krom-mork", stil)}"/>'
        f'<circle r="{_n(HUB_R - 7)}" fill="{_farge("krom-lys", stil)}"/>'
        f'<circle r="{_n(HUB_R - 18)}" fill="{_farge("krom-mork", stil)}"/>'
        f'<circle r="{_n(HUB_R - 25)}" fill="{_farge("trykk", stil)}"/>'
        "</g>"
    ]


def _visere(skala: Skala, stil: Stil) -> list[str]:
    """Visere i hvileposisjon. Kortet roterer dem om navet."""
    hvile = skala.vinkel(skala.min_kw)
    rot = f'transform="rotate({_n(hvile)} {_n(NAV_X)} {_n(NAV_Y)})"'

    slepe_topp = NAV_Y - R_SLEPE_INN
    slepe_bunn = NAV_Y - R_SLEPE_UT
    slepe = (
        f'<path id="slepemerke" {rot} d="M {_n(NAV_X)} {_n(slepe_topp)}'
        f' L {_n(NAV_X - 16)} {_n(slepe_bunn)} L {_n(NAV_X + 16)} {_n(slepe_bunn)} Z"'
        f' fill="{_farge("trykk", stil)}"/>'
    )

    spiss = NAV_Y - R_VISER_SVART
    svart = (
        f'<path id="viser-svart" {rot} d="M {_n(NAV_X)} {_n(spiss)}'
        f" L {_n(NAV_X + 5)} {_n(NAV_Y - 150)} L {_n(NAV_X + 9)} {_n(NAV_Y + 36)}"
        f' L {_n(NAV_X - 9)} {_n(NAV_Y + 36)} L {_n(NAV_X - 5)} {_n(NAV_Y - 150)} Z"'
        f' fill="{_farge("trykk", stil)}"/>'
    )

    # Kile: bredest rett over navet, spiss tupp som naar inn i delstrek-baandet.
    rod_spiss = NAV_Y - R_VISER_ROD
    rod = (
        f'<path id="viser-rod" {rot} d="M {_n(NAV_X)} {_n(rod_spiss)}'
        f" L {_n(NAV_X + 30)} {_n(NAV_Y - 96)} L {_n(NAV_X + 15)} {_n(NAV_Y + 34)}"
        f' L {_n(NAV_X - 15)} {_n(NAV_Y + 34)} L {_n(NAV_X - 30)} {_n(NAV_Y - 96)} Z"'
        f' fill="{_farge("viserrod", stil)}"/>'
    )
    return [slepe, rod, svart]


def _deksel(stil: Stil) -> list[str]:
    """Gjennomsiktig plastdeksel i kabinettform, med tynn synlig kant og korn."""
    ut = [
        "<defs>"
        '<filter id="korn" x="0" y="0" width="100%" height="100%">'
        '<feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="7" result="stoy"/>'
        '<feColorMatrix in="stoy" type="saturate" values="0" result="graa"/>'
        # Uten denne fyller stoeyen hele filterrektangelet og legger seg utenfor kabinettet.
        '<feComposite in="graa" in2="SourceGraphic" operator="in"/>'
        "</filter>"
        "</defs>",
    ]
    if stil.gulning:
        # Gulnet klar plast: gulningen ligger i dekselet, ikke i skiven.
        ut.append(f'<path d="{kabinettbane(6)}" fill="{_farge("deksel-gulning", stil)}" opacity="{_n(stil.gulning)}"/>')
    ut.extend(
        [
            f'<path d="{kabinettbane(6)}" fill="none"'
            f' stroke="{_farge("deksel-kant", stil)}" stroke-width="{"5" if stil.gulning else "3"}"'
            f' opacity="{"0.7" if stil.gulning else "0.55"}"/>',
            f'<path d="{kabinettbane(12)}" fill="none"'
            f' stroke="{_farge("krom-lys", stil)}" stroke-width="2" opacity="0.7"/>',
            f'<path d="{kabinettbane(6)}" fill="{_farge("trykk", stil)}" filter="url(#korn)" opacity="0.07"/>',
            f'<path d="M 128 116 L 380 72" fill="none" stroke="{_farge("deksel-glans", stil)}" stroke-width="3"'
            ' stroke-linecap="round" opacity="0.3"/>',
            f'<path d="M 636 952 L 892 916" fill="none" stroke="{_farge("deksel-glans", stil)}" stroke-width="2"'
            ' stroke-linecap="round" opacity="0.22"/>',
        ]
    )
    return ut


def generate_faceplate(
    *,
    kapasitetstrinn: list[tuple[float, int]],
    maks_kw: float = MAKS_KW_STANDARD,
    variant: Variant = "card",
    dso_navn: str | None = None,
    stil: str = "geha",
) -> str:
    """Bygg hele skiven som SVG-streng.

    Args:
        kapasitetstrinn: (kW-terskel, kr/mnd) i stigende rekkefoelge, slik
            dso.py oppgir dem. Oeverste terskel kan vaere float("inf").
        maks_kw: Skalaens toppverdi. Loeftes til naermeste skalatopp som gir
            hele hovedtall, se skalatopp(). data-maks-kw paa rot-elementet
            baerer verdien som faktisk ble brukt.
        variant: "card" gir visere, slitasje og plastdeksel. "print" gir flate
            farger for fysisk trykk, uten deksel og uten visere.
        dso_navn: Nettselskap trykt paa skiven.
        stil: Nokkel i STILER. Se tilgjengelige_stiler().

    Returns:
        SVG-dokument som streng.
    """
    if variant not in {"card", "print"}:
        raise ValueError(f"Ukjent variant: {variant!r}")
    if stil not in STILER:
        raise ValueError(f"Ukjent stil: {stil!r}. Velg mellom {', '.join(STILER)}")

    valgt = STILER[stil]
    skala = lag_skala(valgt, kapasitetstrinn, maks_kw)
    kort = variant == "card"

    tittel = f"{valgt.navn}, {_tall_tekst(skala.min_kw)}-{_tall_tekst(skala.maks_kw)} kW"
    if dso_navn:
        tittel = f"{tittel}, {dso_navn}"
    beskrivelse = (
        "Skive med kapasitetstrinn og visere for effekt naa, projisert time-snitt og topp-3-snitt."
        if kort
        else "Skive med kapasitetstrinn for fysisk trykk, uten visere."
    )

    deler: list[str] = [
        '<svg xmlns="http://www.w3.org/2000/svg" version="1.1"'
        f' viewBox="0 0 {_n(VIEWBOX)} {_n(VIEWBOX)}" width="{_n(VIEWBOX)}" height="{_n(VIEWBOX)}"'
        f' role="img" aria-label="{escape(tittel)}" data-variant="{variant}" data-stil="{stil}"'
        f' data-maks-kw="{_n(skala.maks_kw)}" data-nav-x="{_n(NAV_X)}" data-nav-y="{_n(NAV_Y)}"'
        f' data-vinkel-start="{_n(VINKEL_START)}" data-vinkel-sveip="{_n(VINKEL_SVEIP)}"'
        f' data-skala-min-kw="{_n(skala.min_kw)}" data-skala-eksponent="{_n(skala.eksponent)}"'
        f' data-skala-sokkel-kw="{_n(skala.sokkel_kw)}" data-skala-sokkel-andel="{_n(skala.sokkel_andel)}">',
        f"<title>{escape(tittel)}</title>",
        f"<desc>{escape(beskrivelse)}</desc>",
    ]
    deler.extend(_plate(variant, valgt))
    if not kort:
        deler.extend(_bunnfelt(valgt, variant))
    deler.extend(_skala_tegning(skala, valgt))
    deler.extend(_trinnband(kapasitetstrinn, skala, valgt))
    deler.extend(_trykk_tekst(valgt, skala, dso_navn))
    if kort:
        deler.extend(_visere(skala, valgt))
    deler.extend(_hub(variant, valgt))
    if kort:
        deler.extend(_bunnfelt(valgt, variant))
        deler.extend(_deksel(valgt))
    deler.append("</svg>")
    return "\n".join(deler)
