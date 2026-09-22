"""Tester for terskelmodellen i modell.py.

Tallene her er regnet for hånd fra topp-3-regelen, ikke lest ut av koden. Det
er med vilje: både denne feilen og timemålerfeilen overlevde fordi testene
kodet inn den samme antakelsen som koden.
"""

from __future__ import annotations

from datetime import date

import pytest

from custom_components.effektvakt.dso import KAPASITETSTRINN_PER_DSO
from custom_components.effektvakt.modell import (
    beregn_terskel,
    dagstak,
    snitt_av_topp_3,
    top_n_average,
    topp_2_andre_dager,
    trinn_indeks,
)

BKK = list(KAPASITETSTRINN_PER_DSO["bkk"]["kapasitetstrinn"])

D1 = date(2026, 6, 1)
D2 = date(2026, 6, 2)
D3 = date(2026, 6, 3)


def test_bkk_trinn_er_som_forventet():
    """Regneeksemplene under hviler på disse tersklene og prisene."""
    assert BKK[:4] == [(2.0, 155), (5.0, 250), (10.0, 415), (15.0, 600)]


# --- x* alene, med terskelen gitt ------------------------------------------
#
# De tre vektorene fra hacs-effektvakt-2p7wpch, alle mot BKKs 5 kW-trinn.
# Mot koden slik den sto til september 2026 ga de 5,90, 5,50 og 5,00: max av
# terskelen og topp-2-snittet, altså motsatt vei av regelen.


@pytest.mark.parametrize(
    "a,b,forventet",
    [
        # (a + b + 3,2) / 3 = 5,0. Jo høyere de andre dagene er, jo mindre tåler i dag.
        (6.0, 5.8, 3.2),
        (5.5, 5.5, 4.0),
        # 3T - (a + b) = 11,0, men kappet ved T: en dag på 11 kW holder seg
        # innenfor bare ved å tvinge resten av måneden ned mot null.
        (2.0, 2.0, 5.0),
    ],
)
def test_dagstak_mot_fem_kw_trinnet(a: float, b: float, forventet: float):
    assert dagstak(maal_terskel_kw=5.0, topp_2_andre_kw=a + b) == pytest.approx(forventet)


def test_dagstak_treffer_terskelen_naar_snittet_regnes_tilbake():
    """Ligger dagen nøyaktig på x*, ligger topp-3-snittet nøyaktig på T."""
    for a, b in [(6.0, 5.8), (5.5, 5.5), (4.0, 3.0)]:
        x = dagstak(maal_terskel_kw=5.0, topp_2_andre_kw=a + b)
        if x < 5.0:  # kappet ved T er en policy, ikke aritmetikk
            assert (a + b + x) / 3 == pytest.approx(5.0)


def test_dagstak_er_aldri_negativt():
    """Har de andre dagene alt brukt opp hele budsjettet, er taket null, ikke minus."""
    assert dagstak(maal_terskel_kw=5.0, topp_2_andre_kw=20.0) == 0.0


# --- byggeklossene ----------------------------------------------------------


def test_snitt_av_topp_3_deler_alltid_paa_tre():
    assert snitt_av_topp_3({}) == 0.0
    assert snitt_av_topp_3({D1: 7.0}) == pytest.approx(7 / 3)
    assert snitt_av_topp_3({D1: 6.0, D2: 4.0}) == pytest.approx(10 / 3)


def test_snitt_av_topp_3_er_monotont():
    """En ny dag kan bare dra snittet opp, aldri ned."""
    maaned: dict[date, float] = {}
    forrige = 0.0
    for dag, kw in [(D1, 6.0), (D2, 1.0), (D3, 4.0), (date(2026, 6, 4), 0.5)]:
        maaned[dag] = kw
        na = snitt_av_topp_3(maaned)
        assert na >= forrige
        forrige = na


def test_snitt_av_topp_3_tar_de_tre_hoyeste():
    maaned = {D1: 5.0, D2: 7.0, D3: 3.0, date(2026, 6, 4): 9.0}
    assert snitt_av_topp_3(maaned) == pytest.approx((9 + 7 + 5) / 3)


def test_topp_2_andre_dager_holder_i_dag_utenfor():
    maaned = {D1: 6.0, D2: 5.8, D3: 9.0}
    assert topp_2_andre_dager(maaned, today=D3) == pytest.approx(11.8)
    assert topp_2_andre_dager(maaned, today=D1) == pytest.approx(14.8)


def test_topp_2_andre_dager_uten_andre_dager():
    assert topp_2_andre_dager({D3: 9.0}, today=D3) == 0.0


def test_top_n_average_deler_paa_antallet_som_finnes():
    """Brukes bare på en måned som er gjort opp, der antall dager er et faktum."""
    assert top_n_average({}, n=3) is None
    assert top_n_average({D1: 6.0, D2: 4.0}, n=3) == pytest.approx(5.0)


def test_trinn_indeks():
    assert trinn_indeks(1.5, BKK) == 0
    assert trinn_indeks(2.0, BKK) == 0
    assert trinn_indeks(2.1, BKK) == 1
    assert trinn_indeks(5.0, BKK) == 1
    assert trinn_indeks(7.5, BKK) == 2
    assert trinn_indeks(1000.0, BKK) == len(BKK) - 1


# --- hele modellen, mot BKK -------------------------------------------------


def test_hoye_andre_dager_gir_lavt_tak():
    """Seks og 5,8 kW logget: måneden ligger i 5 kW-trinnet, og i dag tåler 3,2.

    minste mulige topp-3 = 11,8 / 3 = 3,93, altså 5 kW-trinnet (250 kr).
    x* = 3 x 5 - 11,8 = 3,2. Dagen har ingen egen topp ennå, så timetaket er 3,2.
    """
    t = beregn_terskel(trinn=BKK, daily_max_kw={D1: 6.0, D2: 5.8}, today=D3, projected_kw=3.0)
    assert t.minste_mulige_topp_3_kw == pytest.approx(3.933, abs=0.001)
    assert t.maal_terskel_kw == 5.0
    assert t.maal_trinn_kr == 250
    assert t.dagstak_kw == pytest.approx(3.2)
    assert t.time_tak_kw == pytest.approx(3.2)
    assert t.margin_kw == pytest.approx(0.2)
    assert t.kan_legge_paa_kw == pytest.approx(0.2)
    assert t.kutt_anbefalt_kw == 0.0


def test_hoye_andre_dager_melder_kutt_der_gammel_modell_meldte_god_margin():
    """Projisert 5,0 kW med 6,0 og 5,8 bak seg: 1,8 kW for høyt, ikke 0,9 til gode.

    Modellen som sto her til september 2026 ga effective_threshold 5,90 og
    dermed margin +0,90 i nøyaktig dette tilfellet.
    """
    t = beregn_terskel(trinn=BKK, daily_max_kw={D1: 6.0, D2: 5.8}, today=D3, projected_kw=5.0)
    assert t.margin_kw == pytest.approx(-1.8)
    assert t.kutt_anbefalt_kw == pytest.approx(1.8)
    assert t.kan_legge_paa_kw == 0.0


def test_to_like_dager():
    """5,5 og 5,5: minste mulige topp-3 er 3,67, trinnet er 5 kW, og i dag tåler 4,0."""
    t = beregn_terskel(trinn=BKK, daily_max_kw={D1: 5.5, D2: 5.5}, today=D3, projected_kw=0.0)
    assert t.maal_terskel_kw == 5.0
    assert t.dagstak_kw == pytest.approx(4.0)


def test_lave_andre_dager_sikter_paa_det_billige_trinnet():
    """To dager på 2,0: måneden ligger fortsatt i 2 kW-trinnet, og det er det som forsvares.

    minste mulige topp-3 = 4 / 3 = 1,33, altså 155 kr-trinnet. x* = 3 x 2 - 4 = 2,0,
    som også er kappet ved T. En time over 2,0 flytter måneden til 250 kr.

    Regnet mot 5 kW-trinnet ville svaret vært 5,0 (kappet fra 11,0), men det
    trinnet er ikke det måneden ligger i.
    """
    t = beregn_terskel(trinn=BKK, daily_max_kw={D1: 2.0, D2: 2.0}, today=D3, projected_kw=1.5)
    assert t.maal_terskel_kw == 2.0
    assert t.maal_trinn_kr == 155
    assert t.dagstak_kw == pytest.approx(2.0)
    assert t.margin_kw == pytest.approx(0.5)


def test_blandede_dager():
    """9,0 og 1,0 logget: 10 / 3 = 3,33 er 5 kW-trinnet, og i dag tåler 15 - 10 = 5,0."""
    t = beregn_terskel(trinn=BKK, daily_max_kw={D1: 9.0, D2: 1.0}, today=D3, projected_kw=2.0)
    assert t.maal_terskel_kw == 5.0
    assert t.dagstak_kw == pytest.approx(5.0)
    assert t.margin_kw == pytest.approx(3.0)


def test_dagens_egen_topp_teller_med():
    """Er dagens topp alt 12 kW, flytter ikke en ny time på 12 noe som helst.

    Dagene 1,0 / 1,0 / 12,0 gir minste mulige topp-3 = 4,67, altså 5 kW-trinnet.
    x* er kappet til 5,0, men dagen har alt satt 12,0, og dagen teller bare med
    sin høyeste time. Timetaket er derfor 12,0.
    """
    t = beregn_terskel(trinn=BKK, daily_max_kw={D1: 1.0, D2: 1.0, D3: 12.0}, today=D3, projected_kw=12.0)
    assert t.dagens_maks_kw == 12.0
    assert t.dagstak_kw == pytest.approx(5.0)
    assert t.time_tak_kw == pytest.approx(12.0)
    assert t.margin_kw == pytest.approx(0.0)


def test_time_under_dagens_topp_har_margin():
    t = beregn_terskel(trinn=BKK, daily_max_kw={D1: 1.0, D2: 1.0, D3: 12.0}, today=D3, projected_kw=9.0)
    assert t.margin_kw == pytest.approx(3.0)


def test_tom_maaned_faar_sin_andel_av_det_billigste_trinnet():
    """Uten en eneste dag logget er måltrinnet det laveste, og andelen er terskelen.

    Ukappet ville en enkelt dag tålt 3 x 2 = 6 kW, men da måtte de to neste
    dagene holdt seg på null. Kappet ved T gir hver av de tre dagene lik andel.
    """
    t = beregn_terskel(trinn=BKK, daily_max_kw={}, today=D1, projected_kw=1.0)
    assert t.maal_terskel_kw == 2.0
    assert t.dagstak_kw == pytest.approx(2.0)
    assert t.time_tak_kw == pytest.approx(2.0)


def test_ukjent_nettselskap_har_ingenting_aa_maale_mot():
    t = beregn_terskel(trinn=[], daily_max_kw={D1: 6.0}, today=D2, projected_kw=5.0)
    assert t.maal_terskel_kw is None
    assert t.time_tak_kw is None
    assert t.margin_kw is None
    assert t.kan_legge_paa_kw is None
    assert t.kutt_anbefalt_kw == 0.0
    # Skranken regnes uansett, den trenger ikke trinn
    assert t.minste_mulige_topp_3_kw == pytest.approx(2.0)


def test_oeverste_trinn_har_ingenting_aa_unngaa():
    """Ligger måneden på øverste trinn, koster ikke en høy time mer enn en lav."""
    t = beregn_terskel(trinn=BKK, daily_max_kw={D1: 400.0, D2: 400.0, D3: 400.0}, today=D3, projected_kw=500.0)
    assert t.maal_terskel_kw is None
    assert t.margin_kw is None


def test_egendefinerte_trinn_uten_aapent_topptrinn():
    """Over siste terskel i en egendefinert tabell finnes det ikke noe dyrere trinn."""
    egne = [(2.0, 155), (5.0, 250), (10.0, 415)]
    t = beregn_terskel(trinn=egne, daily_max_kw={D1: 30.0, D2: 30.0, D3: 30.0}, today=D3, projected_kw=30.0)
    assert t.maal_terskel_kw is None


def test_taket_faller_naar_de_andre_dagene_stiger():
    """Kjernen i saken: innenfor ett og samme trinn senker høye andre dager taket.

    Modellen som sto her til september 2026 gikk motsatt vei. Den ga
    max(T, snitt av topp-2), som steg med de andre dagene og meldte god margin
    i nettopp den måneden vakten finnes for.
    """
    andre = (4.0, 5.0, 5.5, 6.0, 6.5)
    tak = [dagstak(maal_terskel_kw=5.0, topp_2_andre_kw=2 * kw) for kw in andre]
    assert tak == [5.0, 5.0, 4.0, 3.0, 2.0]
    assert tak == sorted(tak, reverse=True)

    gammel_modell = [max(5.0, kw) for kw in andre]
    assert gammel_modell == sorted(gammel_modell)


def test_maaltrinnet_stiger_med_dagene_som_er_laast_inn():
    """Blir dagene tunge nok, er det billige trinnet tapt, og det neste forsvares i stedet."""
    lavt = beregn_terskel(trinn=BKK, daily_max_kw={D1: 2.0, D2: 2.0}, today=D3, projected_kw=0.0)
    hoyt = beregn_terskel(trinn=BKK, daily_max_kw={D1: 4.0, D2: 4.0}, today=D3, projected_kw=0.0)
    assert lavt.maal_terskel_kw == 2.0
    assert hoyt.maal_terskel_kw == 5.0
    # 8 / 3 = 2,67 er over 2 kW-terskelen: 155 kr-trinnet er ikke lenger mulig,
    # uansett hva dagen i dag gjør.
    assert hoyt.minste_mulige_topp_3_kw == pytest.approx(2.667, abs=0.001)
