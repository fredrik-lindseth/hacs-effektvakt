"""Tester for SVG-generatoren til skivene."""

from __future__ import annotations

import logging
import math
import re
import xml.etree.ElementTree as ET

import pytest

from custom_components.effektvakt.dso import KAPASITETSTRINN_PER_DSO
from custom_components.effektvakt.faceplate import (
    HUB_R,
    MAKS_KW_STANDARD,
    NAV_X,
    NAV_Y,
    PALETT,
    R_HOVEDMERKE,
    R_SKALA,
    R_VISER_SVART,
    SKALATOPPER,
    SKALATOPPER_SMAA,
    STILER,
    VERSAL_SENTER,
    VINKEL_START,
    VINKEL_SVEIP,
    Skala,
    _delstreker,
    _n,
    _stigehovedtall,
    _tekstbredde,
    _valider_stil,
    generate_faceplate,
    lag_skala,
    normaliser_maks_kw,
    rod_viser_halvbredde,
    skalatopp,
    tilgjengelige_stiler,
    vinkel_for_kw,
)

SVG_NS = "{http://www.w3.org/2000/svg}"

BKK = KAPASITETSTRINN_PER_DSO["bkk"]["kapasitetstrinn"]


def _rot(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def _med_id(rot: ET.Element, ident: str) -> ET.Element | None:
    for element in rot.iter():
        if element.get("id") == ident:
            return element
    return None


def _tekster(rot: ET.Element) -> list[str]:
    return [(element.text or "").strip() for element in rot.iter(f"{SVG_NS}text")]


def _kontrast(hex_a: str, hex_b: str) -> float:
    def luminans(farge: str) -> float:
        kanaler = [int(farge.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4)]
        lineaer = [k / 12.92 if k <= 0.04045 else ((k + 0.055) / 1.055) ** 2.4 for k in kanaler]
        return 0.2126 * lineaer[0] + 0.7152 * lineaer[1] + 0.0722 * lineaer[2]

    lys, morkt = sorted((luminans(hex_a), luminans(hex_b)), reverse=True)
    return (lys + 0.05) / (morkt + 0.05)


def test_alle_dso_gir_gyldig_xml():
    assert len(KAPASITETSTRINN_PER_DSO) >= 60, "Forventer at hele DSO-tabellen er lastet"
    for dso_id, info in KAPASITETSTRINN_PER_DSO.items():
        for stil in STILER:
            for variant in ("card", "print"):
                svg = generate_faceplate(
                    kapasitetstrinn=info["kapasitetstrinn"],
                    variant=variant,
                    dso_navn=info["navn"],
                    stil=stil,
                )
                rot = _rot(svg)
                assert rot.tag == f"{SVG_NS}svg", f"{dso_id}/{stil}/{variant}: feil rot-element"


def test_rot_har_geometrikontrakten():
    rot = _rot(generate_faceplate(kapasitetstrinn=BKK))
    assert rot.get("data-maks-kw") == "15"
    assert rot.get("data-nav-x") == str(int(NAV_X))
    assert rot.get("data-nav-y") == str(int(NAV_Y)), "navet ligger ved overkanten av bunnfeltet"
    assert rot.get("data-vinkel-start") == "-50"
    assert rot.get("data-vinkel-sveip") == "100"
    assert rot.get("viewBox") == "0 0 1000 1000"


def test_bkk_har_hovedtallene():
    rot = _rot(generate_faceplate(kapasitetstrinn=BKK, maks_kw=15))
    tekster = _tekster(rot)
    for tall in ("0", "3", "6", "9", "12", "15"):
        assert tall in tekster, f"mangler hovedtall {tall}"


def test_bkk_har_trinnmerker_med_kr_tekst():
    rot = _rot(generate_faceplate(kapasitetstrinn=BKK, maks_kw=15))
    forventet = [("2", "155 KR"), ("5", "250 KR"), ("10", "415 KR"), ("15", "600 KR")]
    for indeks, (terskel, kr_tekst) in enumerate(forventet):
        gruppe = _med_id(rot, f"trinn-{indeks}")
        assert gruppe is not None, f"mangler trinn-{indeks}"
        assert gruppe.get("data-kw-til") == terskel
        assert kr_tekst in _tekster(gruppe), f"trinn-{indeks} mangler {kr_tekst}"


def test_card_har_id_ene_kortet_styrer():
    rot = _rot(generate_faceplate(kapasitetstrinn=BKK, variant="card"))
    for ident in ("viser-rod", "viser-svart", "slepemerke", "trinn-0"):
        assert _med_id(rot, ident) is not None, f"mangler #{ident}"


def test_print_uten_filter_visere_og_gradient():
    svg = generate_faceplate(kapasitetstrinn=BKK, variant="print")
    assert "<filter" not in svg
    assert "viser-" not in svg
    assert "Gradient" not in svg


def test_ingen_gradient_i_card_heller():
    svg = generate_faceplate(kapasitetstrinn=BKK, variant="card")
    assert "Gradient" not in svg


def _punkter(d: str) -> list[tuple[float, float]]:
    tall = [float(t) for t in re.findall(r"-?\d+(?:\.\d+)?", d)]
    return list(zip(tall[0::2], tall[1::2], strict=True))


def _polar_av(x: float, y: float) -> tuple[float, float]:
    """Vinkel i grader fra loddlinjen og radius fra navet."""
    dx, dy = x - NAV_X, NAV_Y - y
    return math.degrees(math.atan2(dx, dy)), math.hypot(dx, dy)


def _viserspiss(rot: ET.Element, ident: str) -> tuple[float, float]:
    element = _med_id(rot, ident)
    assert element is not None, f"mangler #{ident}"
    return _punkter(element.get("d", ""))[0]


def test_viserspissene_naar_fram_til_skalaen():
    rot = _rot(generate_faceplate(kapasitetstrinn=BKK))
    # Den svarte krysser buen, den roede stopper inne i delstrek-baandet.
    vinkel, radius = _polar_av(*_viserspiss(rot, "viser-svart"))
    assert vinkel == pytest.approx(0.0, abs=0.01), "viseren skal tegnes loddrett og roteres av kortet"
    assert radius >= R_SKALA, "svart viser naar ikke buen"
    vinkel, radius = _polar_av(*_viserspiss(rot, "viser-rod"))
    assert vinkel == pytest.approx(0.0, abs=0.01)
    assert R_SKALA - R_HOVEDMERKE < radius <= R_SKALA, "roed viser naar ikke inn i merkebaandet"


def test_rod_viser_peker_paa_riktig_merke():
    """Ved 6 kW skal spissen ligge paa 6-merket, ikke ved siden av."""
    rot = _rot(generate_faceplate(kapasitetstrinn=BKK, maks_kw=15))
    merkevinkler = _merkevinkler(rot)
    assert len(merkevinkler) == 6

    for kw, forventet in ((0.0, -50.0), (6.0, -10.0), (15.0, 50.0)):
        vinkel = vinkel_for_kw(kw, 15)
        assert vinkel == pytest.approx(forventet)
        assert min(abs(vinkel - m) for m in merkevinkler) == pytest.approx(0.0, abs=0.01)

    # Spissen rotert til 6 kW skal treffe det samme merket.
    x, y = _viserspiss(rot, "viser-rod")
    vinkel = math.radians(vinkel_for_kw(6.0, 15))
    dx, dy = x - NAV_X, y - NAV_Y
    rotert = (
        NAV_X + dx * math.cos(vinkel) - dy * math.sin(vinkel),
        NAV_Y + dx * math.sin(vinkel) + dy * math.cos(vinkel),
    )
    assert _polar_av(*rotert)[0] == pytest.approx(-10.0, abs=0.01)


def _vinkel_fra_kontrakten(rot: ET.Element, kw: float) -> float:
    """Samme regnestykke som kortet gjør, bare ut fra data-attributtene."""
    start = float(rot.get("data-vinkel-start", "0"))
    sveip = float(rot.get("data-vinkel-sveip", "0"))
    maks = float(rot.get("data-maks-kw", "0"))
    min_kw = float(rot.get("data-skala-min-kw", "0"))
    eksponent = float(rot.get("data-skala-eksponent", "1"))
    sokkel_kw = float(rot.get("data-skala-sokkel-kw", "0"))
    sokkel_andel = float(rot.get("data-skala-sokkel-andel", "0"))
    klemt = max(kw, min_kw)
    if sokkel_kw > min_kw and sokkel_andel > 0:
        if klemt <= sokkel_kw:
            andel = sokkel_andel * (klemt - min_kw) / (sokkel_kw - min_kw)
        else:
            nedre = sokkel_kw**eksponent
            andel = sokkel_andel + (1 - sokkel_andel) * (klemt**eksponent - nedre) / (maks**eksponent - nedre)
    else:
        andel = (klemt**eksponent - min_kw**eksponent) / (maks**eksponent - min_kw**eksponent)
    return start + andel * sveip


def _merkevinkler(rot: ET.Element) -> list[float]:
    """Vinkelen til hvert hovedmerke, slaatt sammen fra de to endene av streken.

    Koordinatene er avrundet til to desimaler i SVG-en, saa endene av samme
    strek spriker noen hundredeler.
    """
    merker = _med_id(rot, "hovedmerker")
    assert merker is not None
    vinkler = sorted(_polar_av(*punkt)[0] for punkt in _punkter(merker.get("d", "")))
    grupper: list[list[float]] = []
    for vinkel in vinkler:
        if grupper and vinkel - grupper[-1][-1] < 0.05:
            grupper[-1].append(vinkel)
        else:
            grupper.append([vinkel])
    return [sum(gruppe) / len(gruppe) for gruppe in grupper]


@pytest.mark.parametrize("maks_kw", [5, 10, 15, 20, 30])
def test_avlesningen_stemmer_i_alle_stiler(maks_kw: float):
    """Viseren rotert til et hovedtall skal peke paa det merket, ogsaa paa komprimert skala."""
    for navn, stil in STILER.items():
        svg = generate_faceplate(kapasitetstrinn=BKK, stil=navn, maks_kw=maks_kw)
        rot = _rot(svg)
        skala = lag_skala(stil, BKK, maks_kw)
        assert rot.get("data-maks-kw") == _n(skala.maks_kw), f"{navn}: kortet faar feil skalatopp"
        merkevinkler = _merkevinkler(rot)
        assert len(merkevinkler) == len(skala.hovedtall)

        spiss = _viserspiss(rot, "viser-rod")
        for kw in skala.hovedtall:
            fra_kontrakten = _vinkel_fra_kontrakten(rot, kw)
            forventet = skala.vinkel(kw)
            assert fra_kontrakten == pytest.approx(forventet, abs=1e-9), f"{navn}: kontrakten spriker"
            radianer = math.radians(fra_kontrakten)
            dx, dy = spiss[0] - NAV_X, spiss[1] - NAV_Y
            rotert = (
                NAV_X + dx * math.cos(radianer) - dy * math.sin(radianer),
                NAV_Y + dx * math.sin(radianer) + dy * math.cos(radianer),
            )
            traff = min(abs(_polar_av(*rotert)[0] - merke) for merke in merkevinkler)
            assert traff == pytest.approx(0.0, abs=0.02), f"{navn}: viseren peker ikke paa {kw} kW"

        # Hvert hovedtall skal ogsaa staa trykt paa skiven, ikke bare ha et merke.
        tekster = _tekster(rot)
        for kw in skala.hovedtall:
            assert _n(kw).replace(".", ",") in tekster, f"{navn}/{maks_kw}: mangler hovedtallet {kw}"


def test_komprimert_skala_er_trykket_sammen_mot_toppen():
    for navn, stil in STILER.items():
        if stil.eksponent >= 1.0:
            continue
        skala = lag_skala(stil, BKK, 15)
        nederst = skala.hovedtall[1] - skala.hovedtall[0]
        overst = skala.hovedtall[-1] - skala.hovedtall[-2]
        assert overst > nederst, f"{navn}: toppen skal romme flere kW per grad enn bunnen"
        assert skala.sokkel_kw > 0, f"{navn}: sokkelen skal ende paa foerste terskel"
        assert skala.min_kw == 0, f"{navn}: alle kapasitetstrinn skal vaere med"


def test_stilregisteret_er_eksponert():
    stiler = tilgjengelige_stiler()
    assert set(stiler) == set(STILER)
    assert all(visningsnavn for visningsnavn in stiler.values())
    for navn in stiler:
        assert _rot(generate_faceplate(kapasitetstrinn=BKK, stil=navn)).get("data-stil") == navn


def test_skala_uten_terskler_faar_ingen_sokkel():
    for navn in STILER:
        rot = _rot(generate_faceplate(kapasitetstrinn=[], stil=navn))
        assert rot.get("data-skala-min-kw") == "0"
        assert rot.get("data-skala-sokkel-andel") == "0", f"{navn}: uten terskler er det ingenting aa klemme"


def test_alle_trinn_er_med_i_alle_stiler():
    """Sokkelen finnes nettopp for at det laveste trinnet ikke skal falle utenfor."""
    for navn in STILER:
        rot = _rot(generate_faceplate(kapasitetstrinn=BKK, stil=navn))
        trinn = [e for e in rot.iter() if (e.get("id") or "").startswith("trinn-")]
        assert [e.get("data-kw-til") for e in trinn] == ["2", "5", "10", "15"], f"{navn}: mangler trinn"
        assert "155 KR" in _tekster(rot), f"{navn}: laveste trinn mangler pris"


def test_vinkel_for_kw_avviser_ugyldig_spenn():
    with pytest.raises(ValueError, match="maa vaere stoerre enn"):
        vinkel_for_kw(5, 2, min_kw=3)


def test_gjerdene_i_skalautledningen():
    """Vaktene som holder en framtidig stil fra aa lage ulesbare merker."""
    # Siste stigeverdi for naer toppen: da faller den ut til fordel for toppen.
    assert _stigehovedtall(2.0, 12.5, 0.5)[-2:] == (10.0, 12.5)
    # Et hovedintervall som er for trangt til delstreker faar ingen.
    trang = Skala(min_kw=0.0, maks_kw=15.0, eksponent=1.0, hovedtall=(14.9, 15.0))
    assert _delstreker(trang, "steg") == []


def test_ukjent_stil_avvises():
    with pytest.raises(ValueError, match="Ukjent stil"):
        generate_faceplate(kapasitetstrinn=BKK, stil="pluss")


def _avstand_til_sveipekanten(x: float, y: float) -> float:
    """Korteste avstand fra et punkt til viserens ytterstillinger."""
    vinkel, radius = _polar_av(x, y)
    ytterkanter = (VINKEL_START, VINKEL_START + VINKEL_SVEIP)
    if min(ytterkanter) <= vinkel <= max(ytterkanter):
        return 0.0
    return min(radius * abs(math.sin(math.radians(vinkel - kant))) for kant in ytterkanter)


def test_ikonrekken_ligger_utenfor_viserens_sveip():
    """Symbolene maa ikke dekkes av viseren, verken i hvile eller ved fullt utslag."""
    for navn, stil in STILER.items():
        rot = _rot(generate_faceplate(kapasitetstrinn=BKK, stil=navn))
        for symbol in stil.symboler:
            ident = stil.maaleverk if symbol.art == "maaleverk" else symbol.art
            element = _med_id(rot, f"symbol-{ident}")
            assert element is not None, f"{navn}: mangler symbol-{ident}"
            x, y = (float(t) for t in re.findall(r"-?\d+(?:\.\d+)?", element.get("transform", "")))
            avstand = _avstand_til_sveipekanten(x, y)
            assert avstand > 30, f"{navn}/{ident} ligger {avstand:.0f} fra viserens bane"


def test_maaleverk_og_skalaform_hoerer_sammen():
    """Dreispole er lineaert, dreiejern er det ikke. Symbolet skal si det samme som skalaen."""
    for navn, stil in STILER.items():
        rot = _rot(generate_faceplate(kapasitetstrinn=BKK, stil=navn))
        assert _med_id(rot, f"symbol-{stil.maaleverk}") is not None, f"{navn}: mangler maaleverksymbolet"
        lineaer = stil.eksponent == 1.0 and stil.sokkel_andel == 0.0
        assert lineaer == (stil.maaleverk == "dreispole"), f"{navn}: symbol og skalaform spriker"


def test_selvmotsigende_stil_avvises():
    forvridd = STILER["geha"]._replace(maaleverk="dreiejern")
    with pytest.raises(ValueError, match="ikke-lineaert"):
        _valider_stil("forvridd", forvridd)
    forvridd = STILER["gossen"]._replace(maaleverk="dreispole")
    with pytest.raises(ValueError, match="lineaert"):
        _valider_stil("forvridd", forvridd)


# Kortet lar viseren slaa noen grader forbi full skala, slik et ekte instrument
# gjoer i endestoppet. Sveipetesten maa regne med det samme overslaget.
OVERSLAG_GRADER = 4.0


def _tekstboks(linje, innhold: str) -> list[tuple[float, float]]:
    """Hjoernene av en trykt tekstlinje, regnet av ankeret og versalhoeyden."""
    bredde = _tekstbredde(innhold, linje.storrelse, linje.sperring or 0.0)
    if linje.anker == "end":
        venstre, hoyre = linje.x - bredde, linje.x
    elif linje.anker == "start":
        venstre, hoyre = linje.x, linje.x + bredde
    else:
        venstre, hoyre = linje.x - bredde / 2, linje.x + bredde / 2
    halv_hoyde = linje.storrelse * VERSAL_SENTER
    return [(x, y) for x in (venstre, hoyre) for y in (linje.y - halv_hoyde, linje.y + halv_hoyde)]


def test_trykt_tekst_ligger_utenfor_viserens_sveip():
    """Verksnavnet ble lest som "EHA-METER" fordi kilen la seg over G-en.

    Alt som er trykt paa skiven skal vaere lesbart i alle viserstillinger. Bare
    enheten ligger med vilje i sveipet, slik originalene har den.
    """
    for navn, stil in STILER.items():
        for linje in stil.tekst:
            if linje.i_sveipet or linje.bare_variant == "print":
                continue
            innhold = linje.mal.format(dso="BKK", min="0", maks="15")
            for x, y in _tekstboks(linje, innhold):
                _, radius = _polar_av(x, y)
                if radius > R_VISER_SVART:
                    continue  # utenfor viserspissen, der ingen viser naar
                luft = rod_viser_halvbredde(radius) + radius * math.radians(OVERSLAG_GRADER) + 8
                avstand = _avstand_til_sveipekanten(x, y)
                assert avstand > luft, (
                    f"{navn}: {innhold!r} er {avstand:.0f} fra kilen ved r={radius:.0f}, trenger {luft:.0f}"
                )


def test_verksnavnet_staar_paa_begge_variantene():
    for variant in ("card", "print"):
        tekster = _tekster(_rot(generate_faceplate(kapasitetstrinn=BKK, variant=variant)))
        assert "GEHA-METER" in tekster, f"{variant}: skiven mangler verksnavnet"


def test_hundre_ma_staar_bare_paa_trykkfilen():
    """Instrumentmerket forvirrer paa kortet og hoerer hjemme paa plata."""
    kort = _tekster(_rot(generate_faceplate(kapasitetstrinn=BKK, stil="gossen", variant="card")))
    trykk = _tekster(_rot(generate_faceplate(kapasitetstrinn=BKK, stil="gossen", variant="print")))
    assert "100 mA" not in kort
    assert "100 mA" in trykk
    assert "kW" in kort, "enheten skal staa paa begge variantene"


def test_klassemerket_skrives_med_komma():
    rot = _rot(generate_faceplate(kapasitetstrinn=BKK))
    kl = next(e for e in rot.iter(f"{SVG_NS}text") if (e.text or "").startswith("KL"))
    assert kl.text == "KL.1,5"
    assert _avstand_til_sveipekanten(float(kl.get("x", "0")), float(kl.get("y", "0"))) > 30


def test_skruen_sitter_under_navet_der_viseren_aldri_kommer():
    rot = _rot(generate_faceplate(kapasitetstrinn=BKK))
    skruer = [e for e in rot.iter() if e.get("class") == "skrue"]
    assert skruer, "mangler skrue i prismefeltet"
    for skrue in skruer:
        x, y = (float(t) for t in re.findall(r"-?\d+(?:\.\d+)?", skrue.get("transform", "")))
        assert x == NAV_X, "skruen skal staa i loddaksen"
        assert y > NAV_Y + HUB_R, "skruen skal staa under navkapselen, utenfor viserens bane"


def test_prismefeltet_ligger_over_navet_i_card_og_under_trykket_i_print():
    kort = generate_faceplate(kapasitetstrinn=BKK, variant="card")
    assert kort.index('id="riflet-felt"') > kort.index('id="viser-rod"'), "plasten skal ligge foran navet"
    trykk = generate_faceplate(kapasitetstrinn=BKK, variant="print")
    assert trykk.index('id="riflet-felt"') < trykk.index('id="hovedmerker"'), "trykket ligger over feltet"


def test_kabinettet_er_buet_ikke_et_rett_kvadrat():
    rot = _rot(generate_faceplate(kapasitetstrinn=BKK))
    kabinett = _med_id(rot, "kabinett")
    assert kabinett is not None
    bane = kabinett.get("d", "")
    assert bane.count("Q") >= 5, "omrisset skal ha buet overkant og kurvede hjoerner"
    punkter = _punkter(bane)
    assert min(y for _, y in punkter) < 44, "overkanten skal bue oppover midt paa"


def test_visere_hviler_paa_null_kw():
    rot = _rot(generate_faceplate(kapasitetstrinn=BKK))
    for ident in ("viser-rod", "viser-svart", "slepemerke"):
        element = _med_id(rot, ident)
        assert element is not None
        assert element.get("transform") == f"rotate({VINKEL_START:g} {NAV_X:g} {NAV_Y:g})"


def test_skalatoppen_brukes_som_den_er_naar_den_er_lesbar():
    """Brukerens egen toppverdi skal overleve, og hovedtallene utledes av den."""
    for oppgitt, forventet, steg in ((5, 5.0, 1.0), (10, 10.0, 2.0), (15, 15.0, 3.0), (30, 30.0, 6.0)):
        assert skalatopp(oppgitt) == (forventet, steg)
        assert normaliser_maks_kw(oppgitt) == forventet

    rot = _rot(generate_faceplate(kapasitetstrinn=BKK, maks_kw=10))
    assert rot.get("data-maks-kw") == "10"
    tekster = _tekster(rot)
    for tall in ("0", "2", "4", "6", "8", "10"):
        assert tall in tekster, f"mangler hovedtall {tall} paa 10 kW-skiven"
    assert "15" not in tekster, "skalaen skal ikke ha kroepet opp til 15"


def test_hovedtallene_er_hele_paa_alle_skalatopper():
    for topp, _ in SKALATOPPER_SMAA + SKALATOPPER:
        hovedtall = lag_skala(STILER["geha"], BKK, topp).hovedtall
        assert hovedtall[0] == 0 and hovedtall[-1] == topp
        assert all(float(kw).is_integer() for kw in hovedtall), f"{topp}: hovedtallene skal vaere hele"
        assert 4 <= len(hovedtall) <= 7, f"{topp}: {len(hovedtall)} hovedtall er ikke en lesbar rekke"


def test_verdi_utenfor_trappen_loeftes_og_sies_fra(caplog):
    """En verdi som ikke kan brukes som den er skal staa i loggen, ikke forsvinne stille."""
    with caplog.at_level(logging.WARNING, logger="custom_components.effektvakt.faceplate"):
        assert skalatopp(22) == (25.0, 5.0)
    assert "22" in caplog.text and "25" in caplog.text

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="custom_components.effektvakt.faceplate"):
        assert skalatopp(15) == (15.0, 3.0)
    assert caplog.text == "", "en verdi som treffer trappen skal ikke gi varsel"

    rot = _rot(generate_faceplate(kapasitetstrinn=BKK, maks_kw=22))
    assert rot.get("data-maks-kw") == "25", "kortet maa se hvilken skalatopp som faktisk ble brukt"


def test_ubrukelig_maks_kw_faller_tilbake_til_standarden(caplog):
    with caplog.at_level(logging.WARNING, logger="custom_components.effektvakt.faceplate"):
        assert normaliser_maks_kw(0) == MAKS_KW_STANDARD
        assert normaliser_maks_kw(float("inf")) == MAKS_KW_STANDARD
    assert caplog.text.count("duger ikke") == 2


def test_hoeye_verdier_stopper_paa_taket():
    topp, steg = skalatopp(1.0e9)
    assert topp == pytest.approx(8.0e5)
    assert steg == pytest.approx(1.6e5)


def test_vinkel_for_kw_folger_skalaen():
    assert vinkel_for_kw(0, 15) == VINKEL_START
    assert vinkel_for_kw(15, 15) == VINKEL_START + VINKEL_SVEIP
    assert vinkel_for_kw(7.5, 15) == pytest.approx(0.0)


def test_terskler_over_skalaen_utelates():
    rot = _rot(generate_faceplate(kapasitetstrinn=BKK, maks_kw=15))
    trinn = [e for e in rot.iter() if (e.get("id") or "").startswith("trinn-")]
    assert len(trinn) == 4, "bare trinn innenfor skalaen skal tegnes"
    assert all(float(e.get("data-kw-til", "0")) <= 15 for e in trinn)


def test_terskel_over_skalaen_klippes_til_maks():
    # Netera-formen: én terskel innenfor skalaen, neste langt utenfor.
    trinn = [(10.0, 167), (63.0, 333), (float("inf"), 667)]
    rot = _rot(generate_faceplate(kapasitetstrinn=trinn, maks_kw=15))
    siste = _med_id(rot, "trinn-1")
    assert siste is not None
    assert siste.get("data-kw-fra") == "10"
    assert siste.get("data-kw-til") == "15"


def test_terskel_uten_bredde_hoppes_over():
    # En terskel på 0 kW eller en gjentatt terskel gir ikke noe synlig segment.
    trinn = [(0.0, 100), (2.0, 155), (2.0, 155), (15.0, 600)]
    rot = _rot(generate_faceplate(kapasitetstrinn=trinn, maks_kw=15))
    segmenter = [e for e in rot.iter() if (e.get("id") or "").startswith("trinn-")]
    assert [e.get("data-kw-til") for e in segmenter] == ["2", "15"]


def test_tomt_trinnsett_gir_fortsatt_gyldig_skive():
    rot = _rot(generate_faceplate(kapasitetstrinn=[]))
    assert _med_id(rot, "trinn-0") is None
    assert "15" in _tekster(rot)


def test_dso_navn_blir_escapet():
    svg = generate_faceplate(kapasitetstrinn=BKK, dso_navn="Fuse & Kraft <AS>")
    rot = _rot(svg)
    assert "FUSE & KRAFT <AS>" in _tekster(rot)


def test_deterministisk_utdata():
    forste = generate_faceplate(kapasitetstrinn=BKK, dso_navn="BKK")
    andre = generate_faceplate(kapasitetstrinn=BKK, dso_navn="BKK")
    assert forste == andre


def test_ukjent_variant_avvises():
    with pytest.raises(ValueError, match="Ukjent variant"):
        generate_faceplate(kapasitetstrinn=BKK, variant="poster")  # type: ignore[arg-type]


def test_alle_farger_kommer_fra_paletten():
    for navn, stil in STILER.items():
        tillatt = set(PALETT.values()) | set(stil.palett.values())
        for variant in ("card", "print"):
            svg = generate_faceplate(kapasitetstrinn=BKK, variant=variant, dso_navn="BKK", stil=navn)
            for farge in re.findall(r"#[0-9a-fA-F]{3,8}", svg):
                assert farge in tillatt, f"{navn}/{variant}: hardkodet farge {farge} utenfor paletten"


def test_stilpalettene_har_maalt_kontrast():
    for navn, stil in STILER.items():
        emalje = stil.palett.get("emalje", PALETT["emalje"])
        assert _kontrast(PALETT["trykk"], emalje) >= 7.0, f"{navn}: trykket må være lesbart"
        assert _kontrast(PALETT["viserrod"], emalje) >= 3.0, f"{navn}: viserrød må skille seg ut"


def test_palett_har_maalt_kontrast():
    emalje = PALETT["emalje"]
    assert _kontrast(PALETT["trykk"], emalje) >= 7.0, "trykk må være lesbart som tekst"
    assert _kontrast(PALETT["viserrod"], emalje) >= 3.0, "viserrød må skille seg fra emaljen"
    assert _kontrast(PALETT["krom-mork"], emalje) >= 3.0, "kromkanten må være synlig"


def test_palett_har_rollene_kortet_speiler():
    for rolle in ("emalje", "trykk", "viserrod", "krom-lys", "krom-mork", "skygge"):
        assert rolle in PALETT


def test_tilgjengelighet_har_tittel_og_rolle():
    rot = _rot(generate_faceplate(kapasitetstrinn=BKK, dso_navn="BKK"))
    assert rot.get("role") == "img"
    assert rot.get("aria-label")
    assert rot.find(f"{SVG_NS}title") is not None
    assert rot.find(f"{SVG_NS}desc") is not None
