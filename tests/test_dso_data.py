"""Sanity-sjekker på generert dso.py."""

from __future__ import annotations

import itertools

from custom_components.effektvakt.dso import KAPASITETSTRINN_PER_DSO


def test_har_minst_en_dso():
    assert len(KAPASITETSTRINN_PER_DSO) >= 10, "Forventer minst 10 DSO-er"


def test_alle_dso_har_navn_og_kapasitetstrinn():
    for dso_id, info in KAPASITETSTRINN_PER_DSO.items():
        assert info["navn"], f"{dso_id}: mangler navn"
        assert info["kapasitetstrinn"], f"{dso_id}: tom kapasitetstrinn-liste"


def test_kapasitetstrinn_terskler_stigende():
    for dso_id, info in KAPASITETSTRINN_PER_DSO.items():
        trinn = info["kapasitetstrinn"]
        terskler = [t[0] for t in trinn]
        assert terskler == sorted(terskler), f"{dso_id}: terskler ikke stigende: {terskler}"


def test_kapasitetstrinn_priser_stigende_eller_likt():
    for dso_id, info in KAPASITETSTRINN_PER_DSO.items():
        trinn = info["kapasitetstrinn"]
        priser = [t[1] for t in trinn]
        # Noen DSO-er kan ha samme pris over flere trinn, men aldri synkende
        for prev, curr in itertools.pairwise(priser):
            assert curr >= prev, f"{dso_id}: pris {curr} < forrige {prev}"


def test_bkk_eksisterer():
    assert "bkk" in KAPASITETSTRINN_PER_DSO
    bkk = KAPASITETSTRINN_PER_DSO["bkk"]
    assert bkk["navn"]
    assert len(bkk["kapasitetstrinn"]) >= 5


def test_alle_terskler_positive():
    for dso_id, info in KAPASITETSTRINN_PER_DSO.items():
        for terskel, pris in info["kapasitetstrinn"]:
            assert terskel > 0, f"{dso_id}: ikke-positiv terskel {terskel}"
            assert pris > 0, f"{dso_id}: ikke-positiv pris {pris}"
