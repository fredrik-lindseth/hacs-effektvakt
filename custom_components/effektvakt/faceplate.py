"""SVG-generator for GEHA-METER-skiven.

Ren modul uten Home Assistant-import, slik at den kan brukes tre steder:
dashboard-kortet (som roterer visere i SVG-en), eksportscriptet for fysisk
trykk, og testene. Geometrien ligger i data-attributter paa rot-elementet
slik at kortet regner ut viservinkler uten aa duplisere skalaen.

Koordinatsystemet er viewBox 0 0 1000 1000 der en enhet er 0,1 mm paa en
100 mm plate, saa filen kan tas rett inn i CAD med kjent skala.
"""

from __future__ import annotations

import math
from typing import Final, Literal
from xml.sax.saxutils import escape

Variant = Literal["card", "print"]

# --- Geometri (data-kontrakt mot kortet) ---------------------------------

VIEWBOX: Final = 1000.0
NAV_X: Final = 500.0
NAV_Y: Final = 900.0
VINKEL_START: Final = -50.0
VINKEL_SVEIP: Final = 100.0
MAKS_KW_STANDARD: Final = 15.0
MAKS_KW_KVANT: Final = 15.0

# --- Geometri (intern tegning) -------------------------------------------
#
# Tre konsentriske lag utenfra og inn, som paa originalen: kr-band, hovedtall,
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

HUB_R: Final = 52.0
RAMME_INNSLAG: Final = 14.0
RIFLE_TOPP: Final = 730.0

DELSTREKER_PER_HOVEDMERKE: Final = 5
HOVEDMERKER: Final = 6

# --- Typografi ------------------------------------------------------------

GROTESK: Final = "'Helvetica Neue', Helvetica, Arial, 'Liberation Sans', sans-serif"
# Originalen har en bred, noektern bokstavform i KW, ikke en antikva med tykke
# seriffer. Slab der den finnes, ellers grotesk med vekt.
SLAB: Final = f"Rockwell, 'Roboto Slab', 'Zilla Slab', {GROTESK}"

TEKST_KR_STORRELSE: Final = 30.0
TEKST_KR_MINSTE: Final = 19.0
TEKST_KR_SPERRING: Final = 2.0

# --- Palett ---------------------------------------------------------------
#
# Rollenavn, ikke fargenavn: kortets shadow-DOM definerer de samme rollene
# som CSS custom properties. Kontrasten mot emalje er maalt (WCAG):
# trykk 12,8:1, viserrod 5,9:1, krom-mork 3,2:1.

PALETT: Final[dict[str, str]] = {
    "emalje": "#ece3d0",
    "emalje-slitt": "#e2d8c2",
    "trykk": "#241f19",
    "viserrod": "#a32026",
    "krom-lys": "#e6e4df",
    "krom-mork": "#7e7c75",
    "skygge": "#b6ae9a",
    "rifle-lys": "#e4dbc8",
    "rifle-mork": "#d6cdb7",
    "deksel-kant": "#8f8878",
    "deksel-glans": "#ffffff",
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


def normaliser_maks_kw(maks_kw: float) -> float:
    """Rund opp til naermeste multiplum av 15 saa hovedtallene forblir hele."""
    if maks_kw <= MAKS_KW_KVANT:
        return MAKS_KW_KVANT
    return math.ceil(maks_kw / MAKS_KW_KVANT) * MAKS_KW_KVANT


def vinkel_for_kw(kw: float, maks_kw: float) -> float:
    """Viservinkel for en effekt. Samme formel som kortet bruker."""
    return VINKEL_START + (kw / maks_kw) * VINKEL_SVEIP


def _hovedtall(maks_kw: float) -> list[float]:
    steg = maks_kw / (HOVEDMERKER - 1)
    return [i * steg for i in range(HOVEDMERKER)]


def _tall_tekst(kw: float) -> str:
    return _n(kw)


def _segmenter(
    kapasitetstrinn: list[tuple[float, int]], maks_kw: float
) -> list[tuple[float, float, int, float | None]]:
    """Band mellom tersklene: (fra_kw, til_kw, kr, terskel_i_skala_eller_None)."""
    segmenter: list[tuple[float, float, int, float | None]] = []
    fra = 0.0
    for terskel, kr in kapasitetstrinn:
        if fra >= maks_kw:
            break
        til = min(terskel, maks_kw) if math.isfinite(terskel) else maks_kw
        if til <= fra:
            continue
        i_skala = terskel if math.isfinite(terskel) and terskel <= maks_kw else None
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


def _farge(rolle: str) -> str:
    return PALETT[rolle]


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
    deler.append(f' fill="{_farge("trykk")}" text-anchor="{anker}"')
    if rotasjon is not None:
        deler.append(f' transform="rotate({_n(rotasjon)} {_n(x)} {_n(y_senter)})"')
    deler.append(f">{escape(innhold)}</text>")
    return "".join(deler)


def _plate(variant: Variant) -> list[str]:
    """Emaljeplate med flat to-tone kromramme."""
    ut = [
        f'<rect x="0" y="0" width="1000" height="1000" rx="18" fill="{_farge("emalje")}"/>',
    ]
    if variant == "card":
        ut.extend(_slitasje())
    innslag = RAMME_INNSLAG
    ut.extend(
        [
            f'<rect x="{_n(innslag)}" y="{_n(innslag)}" width="{_n(1000 - 2 * innslag)}"'
            f' height="{_n(1000 - 2 * innslag)}" rx="12" fill="none"'
            f' stroke="{_farge("krom-lys")}" stroke-width="12"/>',
            f'<rect x="{_n(innslag + 9)}" y="{_n(innslag + 9)}" width="{_n(1000 - 2 * innslag - 18)}"'
            f' height="{_n(1000 - 2 * innslag - 18)}" rx="8" fill="none"'
            f' stroke="{_farge("krom-mork")}" stroke-width="3"/>',
        ]
    )
    return ut


def _slitasje() -> list[str]:
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
    ut = [f'<path d="{d}" fill="{_farge("emalje-slitt")}" opacity="{_n(dekk)}"/>' for d, dekk in flekker]
    skrammer = [
        ("M 214 318 q 96 46 186 34", 2.0, 0.28),
        ("M 660 828 q 74 -32 158 -18", 1.6, 0.22),
        ("M 318 906 q 58 22 122 12", 1.4, 0.2),
        ("M 742 352 q 44 62 58 130", 1.8, 0.24),
    ]
    ut.extend(
        f'<path d="{d}" fill="none" stroke="{_farge("skygge")}" stroke-width="{_n(bredde)}"'
        f' stroke-linecap="round" opacity="{_n(dekk)}"/>'
        for d, bredde, dekk in skrammer
    )
    ut.append(
        '<rect x="0" y="0" width="1000" height="1000" rx="18" fill="none"'
        f' stroke="{_farge("skygge")}" stroke-width="26" opacity="0.18"/>'
    )
    return ut


def _skala(maks_kw: float) -> list[str]:
    """Bue, hovedmerker, delstreker og hovedtall."""
    ut = [
        f'<path d="{_bue(R_SKALA, VINKEL_START, VINKEL_START + VINKEL_SVEIP)}" fill="none"'
        f' stroke="{_farge("trykk")}" stroke-width="5"/>',
    ]

    delsteg = VINKEL_SVEIP / ((HOVEDMERKER - 1) * (DELSTREKER_PER_HOVEDMERKE + 1))
    fine: list[str] = []
    antall_fine = (HOVEDMERKER - 1) * (DELSTREKER_PER_HOVEDMERKE + 1)
    for i in range(antall_fine + 1):
        if i % (DELSTREKER_PER_HOVEDMERKE + 1) == 0:
            continue
        vinkel = VINKEL_START + i * delsteg
        fine.append(_radiell_strek(vinkel, R_SKALA - R_DELMERKE, R_SKALA))
    ut.append(
        f'<path d="{" ".join(fine)}" fill="none" stroke="{_farge("trykk")}" stroke-width="3" stroke-linecap="butt"/>'
    )

    grove = [_radiell_strek(vinkel_for_kw(kw, maks_kw), R_SKALA - R_HOVEDMERKE, R_SKALA) for kw in _hovedtall(maks_kw)]
    ut.append(
        f'<path d="{" ".join(grove)}" fill="none" stroke="{_farge("trykk")}" stroke-width="8" stroke-linecap="butt"/>'
    )

    for kw in _hovedtall(maks_kw):
        vinkel = vinkel_for_kw(kw, maks_kw)
        x, y = _polar(vinkel, R_TALL)
        ut.append(_tekst(x, y, _tall_tekst(kw), storrelse=56, vekt="600"))
    return ut


def _trinnband(kapasitetstrinn: list[tuple[float, int]], maks_kw: float) -> list[str]:
    """Kapasitetstrinn: buesegment per trinn, radielle merker ved tersklene, kr/mnd under."""
    segmenter = _segmenter(kapasitetstrinn, maks_kw)
    if not segmenter:
        return []

    ut = ['<g id="trinnband">']
    terskler: list[float] = []
    for indeks, (fra, til, kr, terskel) in enumerate(segmenter):
        v_fra = vinkel_for_kw(fra, maks_kw)
        v_til = vinkel_for_kw(til, maks_kw)
        ut.append(
            f'<g id="trinn-{indeks}" data-kw-fra="{_n(fra)}" data-kw-til="{_n(til)}" data-kr="{kr}">'
            f'<path class="trinn-bue" d="{_bue(R_TRINN_BUE, v_fra + 0.7, v_til - 0.7)}" fill="none"'
            f' stroke="{_farge("trykk")}" stroke-width="9" stroke-linecap="butt"/>'
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
                )
            )
        ut.append("</g>")
        if terskel is not None:
            terskler.append(terskel)

    if terskler:
        merker = [_radiell_strek(vinkel_for_kw(kw, maks_kw), R_TRINN_INN, R_TRINN_UT) for kw in terskler]
        ut.append(
            f'<path id="trinnmerker" d="{" ".join(merker)}" fill="none"'
            f' stroke="{_farge("trykk")}" stroke-width="6" stroke-linecap="butt"/>'
        )
    ut.append("</g>")
    return ut


def _magnetsymbol() -> list[str]:
    """Dreispolesymbolet: hesteskomagnet med spolen i gapet."""
    x0, y0 = 232.0, 634.0
    return [
        f'<g id="dreispolesymbol" transform="translate({_n(x0)} {_n(y0)})">'
        '<path d="M 0 78 L 0 42 A 42 42 0 0 1 84 42 L 84 78 L 63 78 L 63 42'
        f' A 21 21 0 0 0 21 42 L 21 78 Z" fill="{_farge("trykk")}"/>'
        f'<rect x="36" y="24" width="12" height="58" fill="{_farge("trykk")}"/>'
        "</g>"
    ]


def _trykk_tekst(dso_navn: str | None) -> list[str]:
    ut: list[str] = []
    if dso_navn:
        ut.append(_tekst(500, 92, dso_navn.upper(), storrelse=24, vekt="500", sperring=6))
    ut.extend(
        [
            _tekst(500, 570, "KW", storrelse=86, familie=SLAB, vekt="700", sperring=10),
            _tekst(500, 644, "GEHA-METER", storrelse=34, vekt="600", sperring=8),
            _tekst(768, 684, "KL.1.5", storrelse=32, sperring=2, anker="end"),
        ]
    )
    ut.extend(_magnetsymbol())
    return ut


def _riflet_felt() -> list[str]:
    """Innfelt prismatisk panel over nederste tredjedel, riflet i to toner, med to skruer."""
    topp = RIFLE_TOPP
    venstre = RAMME_INNSLAG + 16.0
    hoyre = 1000.0 - venstre
    bunn = hoyre
    bredde = hoyre - venstre
    hoyde = bunn - topp
    ut = [
        '<g id="riflet-felt">',
        f'<rect x="{_n(venstre)}" y="{_n(topp)}" width="{_n(bredde)}"'
        f' height="{_n(hoyde)}" fill="{_farge("rifle-lys")}"/>',
    ]
    periode = 30.0
    x = venstre
    mork: list[str] = []
    kant: list[str] = []
    while x + periode * 0.5 <= hoyre:
        mork.append(f"M {_n(x)} {_n(topp)} h {_n(periode * 0.5)} v {_n(hoyde)} h {_n(-periode * 0.5)} Z")
        kant.append(f"M {_n(x + periode * 0.5)} {_n(topp)} v {_n(hoyde)}")
        x += periode
    ut.append(f'<path d="{" ".join(mork)}" fill="{_farge("rifle-mork")}"/>')
    ut.append(f'<path d="{" ".join(kant)}" fill="none" stroke="{_farge("skygge")}" stroke-width="1.5" opacity="0.5"/>')
    # Innfelt: skyggekant oeverst, lys kant rett under, tynn omriss rundt hele.
    ut.append(f'<rect x="{_n(venstre)}" y="{_n(topp)}" width="{_n(bredde)}" height="5" fill="{_farge("skygge")}"/>')
    ut.append(
        f'<rect x="{_n(venstre)}" y="{_n(topp + 5)}" width="{_n(bredde)}" height="3" fill="{_farge("krom-lys")}"/>'
    )
    ut.append(
        f'<rect x="{_n(venstre)}" y="{_n(topp)}" width="{_n(bredde)}" height="{_n(hoyde)}" fill="none"'
        f' stroke="{_farge("skygge")}" stroke-width="2" opacity="0.65"/>'
    )
    skrue_y = topp + hoyde * 0.68
    for skrue_x in (NAV_X - 168.0, NAV_X + 168.0):
        ut.append(
            f'<g class="skrue" transform="translate({_n(skrue_x)} {_n(skrue_y)})">'
            f'<circle r="26" fill="{_farge("krom-lys")}" stroke="{_farge("krom-mork")}" stroke-width="4"/>'
            f'<rect x="-17" y="-4" width="34" height="8" fill="{_farge("krom-mork")}"/>'
            "</g>"
        )
    ut.append("</g>")
    return ut


def _hub(variant: Variant) -> list[str]:
    """Navkapsel som flate to-tone-ringer. Trykkvarianten markerer bare akselhullet."""
    if variant == "print":
        return [
            f'<g id="nav" transform="translate({_n(NAV_X)} {_n(NAV_Y)})">'
            f'<circle r="{_n(HUB_R - 30)}" fill="none" stroke="{_farge("trykk")}" stroke-width="4"/>'
            "</g>"
        ]
    return [
        f'<g id="nav" transform="translate({_n(NAV_X)} {_n(NAV_Y)})">'
        f'<circle r="{_n(HUB_R)}" fill="{_farge("krom-mork")}"/>'
        f'<circle r="{_n(HUB_R - 9)}" fill="{_farge("krom-lys")}"/>'
        f'<circle r="{_n(HUB_R - 24)}" fill="{_farge("krom-mork")}"/>'
        f'<circle r="{_n(HUB_R - 33)}" fill="{_farge("trykk")}"/>'
        "</g>"
    ]


def _visere(maks_kw: float) -> list[str]:
    """Visere i hvileposisjon. Kortet roterer dem om navet."""
    hvile = vinkel_for_kw(0.0, maks_kw)
    rot = f'transform="rotate({_n(hvile)} {_n(NAV_X)} {_n(NAV_Y)})"'

    slepe_topp = NAV_Y - R_SLEPE_INN
    slepe_bunn = NAV_Y - R_SLEPE_UT
    slepe = (
        f'<path id="slepemerke" {rot} d="M {_n(NAV_X)} {_n(slepe_topp)}'
        f' L {_n(NAV_X - 16)} {_n(slepe_bunn)} L {_n(NAV_X + 16)} {_n(slepe_bunn)} Z"'
        f' fill="{_farge("trykk")}"/>'
    )

    spiss = NAV_Y - (R_SKALA - 4)
    svart = (
        f'<path id="viser-svart" {rot} d="M {_n(NAV_X)} {_n(spiss)}'
        f" L {_n(NAV_X + 5)} {_n(NAV_Y - 150)} L {_n(NAV_X + 9)} {_n(NAV_Y + 36)}"
        f' L {_n(NAV_X - 9)} {_n(NAV_Y + 36)} L {_n(NAV_X - 5)} {_n(NAV_Y - 150)} Z"'
        f' fill="{_farge("trykk")}"/>'
    )

    rod_spiss = NAV_Y - (R_SKALA - 170)
    rod = (
        f'<path id="viser-rod" {rot} d="M {_n(NAV_X)} {_n(rod_spiss)}'
        f' L {_n(NAV_X + 27)} {_n(NAV_Y - 52)} L {_n(NAV_X - 27)} {_n(NAV_Y - 52)} Z"'
        f' fill="{_farge("viserrod")}"/>'
    )
    return [slepe, rod, svart]


def _deksel() -> list[str]:
    """Gjennomsiktig plastdeksel: avrundet rektangel med tynn synlig kant og korn."""
    return [
        "<defs>"
        '<filter id="korn" x="0" y="0" width="100%" height="100%">'
        '<feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="7" result="stoy"/>'
        '<feColorMatrix in="stoy" type="saturate" values="0"/>'
        "</filter>"
        "</defs>",
        '<rect x="6" y="6" width="988" height="988" rx="22" fill="none"'
        f' stroke="{_farge("deksel-kant")}" stroke-width="3" opacity="0.55"/>',
        '<rect x="12" y="12" width="976" height="976" rx="18" fill="none"'
        f' stroke="{_farge("krom-lys")}" stroke-width="2" opacity="0.7"/>',
        '<rect x="6" y="6" width="988" height="988" rx="22" filter="url(#korn)" opacity="0.07"/>',
        f'<path d="M 108 92 L 372 42" fill="none" stroke="{_farge("deksel-glans")}" stroke-width="3"'
        ' stroke-linecap="round" opacity="0.3"/>',
        f'<path d="M 636 966 L 902 928" fill="none" stroke="{_farge("deksel-glans")}" stroke-width="2"'
        ' stroke-linecap="round" opacity="0.22"/>',
    ]


def generate_faceplate(
    *,
    kapasitetstrinn: list[tuple[float, int]],
    maks_kw: float = MAKS_KW_STANDARD,
    variant: Variant = "card",
    dso_navn: str | None = None,
) -> str:
    """Bygg hele skiven som SVG-streng.

    Args:
        kapasitetstrinn: (kW-terskel, kr/mnd) i stigende rekkefoelge, slik
            dso.py oppgir dem. Oeverste terskel kan vaere float("inf").
        maks_kw: Skalaens toppverdi. Rundes opp til naermeste multiplum av 15.
        variant: "card" gir visere, slitasje og plastdeksel. "print" gir flate
            farger for fysisk trykk, uten deksel og uten visere.
        dso_navn: Nettselskap trykt oeverst paa skiven.

    Returns:
        SVG-dokument som streng.
    """
    if variant not in {"card", "print"}:
        raise ValueError(f"Ukjent variant: {variant!r}")

    maks = normaliser_maks_kw(maks_kw)
    kort = variant == "card"

    tittel = f"GEHA-METER, {_n(maks)} kW"
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
        f' role="img" aria-label="{escape(tittel)}" data-variant="{variant}"'
        f' data-maks-kw="{_n(maks)}" data-nav-x="{_n(NAV_X)}" data-nav-y="{_n(NAV_Y)}"'
        f' data-vinkel-start="{_n(VINKEL_START)}" data-vinkel-sveip="{_n(VINKEL_SVEIP)}">',
        f"<title>{escape(tittel)}</title>",
        f"<desc>{escape(beskrivelse)}</desc>",
    ]
    deler.extend(_plate(variant))
    deler.extend(_skala(maks))
    deler.extend(_trinnband(kapasitetstrinn, maks))
    deler.extend(_trykk_tekst(dso_navn))
    deler.extend(_riflet_felt())
    if kort:
        deler.extend(_visere(maks))
    deler.extend(_hub(variant))
    if kort:
        deler.extend(_deksel())
    deler.append("</svg>")
    return "\n".join(deler)
