"""Oktoberprisene fra nettselskapenes offisielle husholdningstariffer."""

from __future__ import annotations

import math

import pytest

from custom_components.effektvakt.dso import KAPASITETSTRINN_PER_DSO

# Kilder gjelder fra 1. oktober 2026. Alle prisene er kr/mnd inkl. mva.
# Midtnett oppgir baade eks. og inkl. mva, med hele kroner i inkl.-kolonnen.
# Grunnlaget nedenfor bevarer eks.-prisen ganger mva, slik generatoren gjoer.
# https://midtnett.no/wp-content/uploads/2026/09/Pris-fra-1.okt-2026.pdf


@pytest.mark.parametrize(
    ("dso", "forventede_trinn"),
    [
        # https://askernett.no/prisliste-for-naeringskunder-okt-2026/
        (
            "asker_nett",
            [
                (2.0, 225.0),
                (5.0, 320.0),
                (10.0, 500.0),
                (15.0, 850.0),
                (20.0, 1090.0),
                (25.0, 1350.0),
                (50.0, 2130.0),
                (75.0, 3150.0),
                (100.0, 4200.0),
                (math.inf, 7300.0),
            ],
        ),
        # https://www.barents-nett.no/getfile.php/1315602-1790233965/Bilder/Nett/Nettleiebrosjyre%2001.10.2026.pdf
        (
            "barents_nett",
            [
                (2.0, 491.0),
                (5.0, 541.0),
                (10.0, 589.0),
                (15.0, 639.0),
                (20.0, 737.0),
                (math.inf, 884.0),
            ],
        ),
        # https://www.glitrenett.no/kunde/nettleie-og-priser/nettleiepriser-privatkunde
        (
            "glitre",
            [
                (2.0, 165.0),
                (5.0, 270.0),
                (10.0, 455.0),
                (15.0, 765.0),
                (20.0, 1025.0),
                (25.0, 1275.0),
                (50.0, 2062.5),
                (75.0, 3075.0),
                (100.0, 4105.0),
                (math.inf, 7190.0),
            ],
        ),
        # https://kystnett.no/Nettleie/?Article=68
        (
            "kystnett",
            [
                (5.0, 508.0),
                (10.0, 916.0),
                (15.0, 1324.0),
                (20.0, 1733.0),
                (25.0, 2141.0),
                (50.0, 3366.0),
                (75.0, 5407.0),
                (100.0, 7448.0),
                (150.0, 10510.0),
                (math.inf, 14593.0),
            ],
        ),
        # https://midtnett.no/wp-content/uploads/2026/09/Pris-fra-1.okt-2026.pdf
        (
            "midtnett",
            [
                (5.0, 275.0),
                (10.0, 412.5),
                (15.0, 625.0),
                (20.0, 937.5),
                (25.0, 1250.0),
                (50.0, 1746.25),
                (75.0, 2620.0),
                (100.0, 3250.0),
                (math.inf, 3750.0),
            ],
        ),
    ],
)
def test_oktobertrinn_folger_offisielt_tariffgrunnlag(dso: str, forventede_trinn: list[tuple[float, float]]) -> None:
    info = KAPASITETSTRINN_PER_DSO[dso]
    assert info["fastledd_metode"] == "TRE_DØGNMAX_MND"
    assert info["kapasitetstrinn"] == forventede_trinn


def test_norgesnett_oktoberpriser_folger_offisiell_prisliste() -> None:
    """https://norgesnett.no/kunde/nettleie-privat/, priser fra 1. oktober 2026."""
    info = KAPASITETSTRINN_PER_DSO["norgesnett"]
    assert info["fastledd_metode"] == "TRE_DØGNMAX_MND"
    assert info["kapasitetstrinn"] == [
        (2.0, 165.0),
        (5.0, 270.0),
        (10.0, 455.0),
        (15.0, 765.0),
        (20.0, 1025.0),
        (25.0, 1275.0),
        (50.0, 2062.50),
        (75.0, 3075.0),
        (100.0, 4105.0),
        (math.inf, 7190.0),
    ]
