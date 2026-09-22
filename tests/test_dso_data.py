"""Sanity-sjekker på generert dso.py."""

from __future__ import annotations

import itertools
import json
import math
from pathlib import Path

from custom_components.effektvakt.dso import KAPASITETSTRINN_PER_DSO

KILDER = Path(__file__).resolve().parent.parent / "scripts" / "dso_kilder.json"

# Nøklene ligger i brukernes config entries. Forsvinner en av dem, mister
# installasjonen nettselskapet sitt og faller tilbake til tomme sensorer. Nye
# nettselskap kan legges til; disse kan ikke fjernes uten en migrering.
NOKLER_I_BRUK = frozenset({
    "area_nett_omrade1", "area_nett_omrade2", "area_nett_omrade3", "arva", "asker_nett",
    "barents_nett", "bindal_kraftnett", "bkk", "bomlo_kraftnett", "breheim_nett", "de_nett",
    "elinett", "elmea", "elvenett", "elvia", "enida", "etna_nett", "everket", "fagne", "foie",
    "fore", "glitre", "griug", "haringnett", "havnett", "holand_setskog", "indre_hordaland",
    "jaren_everk", "ke_nett", "klive", "kystnett", "lede", "linea", "linja", "lnett", "lucerna",
    "lysna", "mellom", "meloy_energi", "midtnett", "modalen_kraftlag", "nettselskapet",
    "noranett", "noranett_andoy", "noranett_hadsel", "nordvest_nett", "norefjell_nett",
    "norgesnett", "r_nett", "rakkestad_energi", "rk_nett", "romsdalsnett", "s_nett",
    "sor_aurdal_energi", "stannum", "stram", "straumen_nett", "straumnett", "sygnir",
    "telemark_nett", "tendranett", "tensio_tn", "tensio_ts", "tinfos", "uvdal_kraftforsyning",
    "vang_energiverk", "vestall", "vestmar_nett", "vevig", "viermie", "vissi",
})  # fmt: skip


def test_har_minst_en_dso():
    assert len(KAPASITETSTRINN_PER_DSO) >= 10, "Forventer minst 10 DSO-er"


def test_ingen_nokkel_i_bruk_har_forsvunnet():
    mangler = NOKLER_I_BRUK - set(KAPASITETSTRINN_PER_DSO)
    assert not mangler, f"Nøkler brukere har i config entry er borte: {sorted(mangler)}"


def test_nokler_matcher_kildetabellen():
    kilder = json.loads(KILDER.read_text(encoding="utf-8"))["nettselskap"]
    assert set(kilder) == set(KAPASITETSTRINN_PER_DSO), (
        "dso.py og scripts/dso_kilder.json er ute av takt, kjør generer-scriptet"
    )


def test_alle_dso_har_navn_og_kapasitetstrinn():
    for dso_id, info in KAPASITETSTRINN_PER_DSO.items():
        assert info["navn"], f"{dso_id}: mangler navn"
        assert info["kapasitetstrinn"], f"{dso_id}: tom kapasitetstrinn-liste"


def test_kapasitetstrinn_terskler_stigende():
    for dso_id, info in KAPASITETSTRINN_PER_DSO.items():
        trinn = info["kapasitetstrinn"]
        terskler = [t[0] for t in trinn]
        assert terskler == sorted(terskler), f"{dso_id}: terskler ikke stigende: {terskler}"


def test_oeverste_trinn_er_uendelig():
    """Et tak på 999 kW er ikke et tak, og et forbruk over det ville falt ut av tabellen."""
    for dso_id, info in KAPASITETSTRINN_PER_DSO.items():
        siste = info["kapasitetstrinn"][-1][0]
        assert math.isinf(siste), f"{dso_id}: øverste trinn stopper på {siste} kW"


def test_kapasitetstrinn_priser_stigende_eller_likt():
    for dso_id, info in KAPASITETSTRINN_PER_DSO.items():
        trinn = info["kapasitetstrinn"]
        priser = [t[1] for t in trinn]
        # Noen DSO-er kan ha samme pris over flere trinn, men aldri synkende
        for prev, curr in itertools.pairwise(priser):
            assert curr >= prev, f"{dso_id}: pris {curr} < forrige {prev}"


def test_bkk_stemmer_med_prislisten():
    """Fasit fra bkk.no per 01.01.2026, den ene tabellen vi har verifisert mot faktura."""
    bkk = KAPASITETSTRINN_PER_DSO["bkk"]
    assert bkk["navn"] == "BKK"
    assert bkk["prisomrade"] == "NO5"
    assert bkk["kapasitetstrinn"][:3] == [(2.0, 155), (5.0, 250), (10.0, 415)]


def test_alle_terskler_positive():
    for dso_id, info in KAPASITETSTRINN_PER_DSO.items():
        for terskel, pris in info["kapasitetstrinn"]:
            assert terskel > 0, f"{dso_id}: ikke-positiv terskel {terskel}"
            assert pris > 0, f"{dso_id}: ikke-positiv pris {pris}"
