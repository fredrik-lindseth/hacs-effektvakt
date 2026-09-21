"""Tester for SVG-generatoren til GEHA-METER-skiven."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import pytest

from custom_components.effektvakt.dso import KAPASITETSTRINN_PER_DSO
from custom_components.effektvakt.faceplate import (
    PALETT,
    VINKEL_START,
    VINKEL_SVEIP,
    generate_faceplate,
    normaliser_maks_kw,
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
        for variant in ("card", "print"):
            svg = generate_faceplate(
                kapasitetstrinn=info["kapasitetstrinn"],
                variant=variant,
                dso_navn=info["navn"],
            )
            rot = _rot(svg)
            assert rot.tag == f"{SVG_NS}svg", f"{dso_id}/{variant}: feil rot-element"


def test_rot_har_geometrikontrakten():
    rot = _rot(generate_faceplate(kapasitetstrinn=BKK))
    assert rot.get("data-maks-kw") == "15"
    assert rot.get("data-nav-x") == "500"
    assert rot.get("data-nav-y") == "900"
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


def test_visere_hviler_paa_null_kw():
    rot = _rot(generate_faceplate(kapasitetstrinn=BKK))
    for ident in ("viser-rod", "viser-svart", "slepemerke"):
        element = _med_id(rot, ident)
        assert element is not None
        assert element.get("transform") == "rotate(-50 500 900)"


def test_maks_kw_rundes_opp_til_multiplum_av_15():
    assert normaliser_maks_kw(15) == 15
    assert normaliser_maks_kw(10) == 15
    assert normaliser_maks_kw(16) == 30
    assert normaliser_maks_kw(30) == 30
    rot = _rot(generate_faceplate(kapasitetstrinn=BKK, maks_kw=22))
    assert rot.get("data-maks-kw") == "30"
    tekster = _tekster(rot)
    for tall in ("0", "6", "12", "18", "24", "30"):
        assert tall in tekster


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
    tillatt = set(PALETT.values())
    for variant in ("card", "print"):
        svg = generate_faceplate(kapasitetstrinn=BKK, variant=variant, dso_navn="BKK")
        for farge in re.findall(r"#[0-9a-fA-F]{3,8}", svg):
            assert farge in tillatt, f"{variant}: hardkodet farge {farge} utenfor paletten"


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
