"""Valgt maanedsmaal, med haandregnet topp-3 og uten lovnad om straksgevinst."""

from datetime import date

import pytest

from custom_components.effektvakt.dso import KAPASITETSTRINN_PER_DSO
from custom_components.effektvakt.modell import beregn_terskel, gyldig_maaltrinn, vurder_kuttkriterium

BKK = KAPASITETSTRINN_PER_DSO["bkk"]["kapasitetstrinn"]
D1, D2, D3 = (date(2026, 10, d) for d in (1, 2, 3))


def kriterium(dager, *, dag=D1, valgt=5.0, projisert=6.0, brukt=0.0, elapsed=0.0, kutt=1.0):
    return vurder_kuttkriterium(
        trinn=BKK,
        daily_max_kw=dager,
        today=dag,
        projected_kw=projisert,
        actual_kwh_this_hour=brukt,
        elapsed_h=elapsed,
        tilgjengelig_kutt_kw=kutt,
        valgt_maal_kw=valgt,
    )


def test_maalet_fra_foerste_dag_er_fem_ikke_to():
    t = beregn_terskel(trinn=BKK, daily_max_kw={}, today=D1, projected_kw=6, valgt_maal_kw=5)
    assert t.maal_status == "aktiv"
    assert t.maal_terskel_kw == 5
    assert t.maal_trinn_kr == 250
    assert t.margin_kw == -1


def test_tre_seks_kw_dager_kan_reduseres_til_fem_foer_maalet_tapes():
    dager = {}
    for dag in (D1, D2, D3):
        k = kriterium(dager, dag=dag)
        assert k.oppfylt
        assert k.bevarer_maanedsmaal
        dager[dag] = 5.0
    assert sum(dager.values()) / 3 == 5


def test_tidlig_kutt_er_maalbevaring_ikke_maalte_sparekroner():
    k = kriterium({})
    assert k.oppfylt and k.kutt_mulig
    assert k.mulig_besparelse_kr == 0
    assert k.unngaaelig_besparelse_kr == 0


def test_standardmodus_beholdes():
    k = kriterium({}, valgt=None)
    assert not k.oppfylt
    assert not k.bevarer_maanedsmaal
    t = beregn_terskel(trinn=BKK, daily_max_kw={}, today=D1, projected_kw=6)
    assert t.maal_status == "ikke_valgt"
    assert t.maal_terskel_kw == 2


@pytest.mark.parametrize("verdi", [0, -5, 3, float("inf"), float("nan"), True, "5"])
def test_bare_endelige_tariffterskler_er_gyldige(verdi):
    assert not gyldig_maaltrinn(trinn=BKK, valgt_maal_kw=verdi)


def test_tapt_maal_faar_ikke_fiktive_maal_kutt():
    dager = {D1: 8.0, D2: 8.0}
    k = kriterium(dager, dag=D3)
    assert not k.bevarer_maanedsmaal
    t = beregn_terskel(trinn=BKK, daily_max_kw=dager, today=D3, projected_kw=6, valgt_maal_kw=5)
    assert t.maal_status == "tapt"
    assert t.maal_terskel_kw == 10


def test_dagens_laaste_topp_kan_ikke_kuttes_bort():
    k = kriterium({D1: 7.0}, projisert=6.0)
    assert not k.bevarer_maanedsmaal


@pytest.mark.parametrize("kutt", [None, 0, -1])
def test_uten_tilgjengelig_last_er_det_ingen_proaktive_kutt(kutt):
    assert not kriterium({}, kutt=kutt).bevarer_maanedsmaal


def test_brukt_energi_kan_ikke_hentes_tilbake():
    assert not kriterium({}, projisert=6, brukt=6, elapsed=0.99).bevarer_maanedsmaal
    assert not kriterium({}, elapsed=1).bevarer_maanedsmaal


def test_delvis_kutt_bevarer_handlingsrom_uten_aa_love_reddet_time():
    k = kriterium({}, elapsed=0.25, brukt=1.5)
    assert k.bevarer_maanedsmaal
    assert k.unngaaelig_besparelse_kr == 0


def test_hoye_andre_dager_reduserer_maalets_dagstak():
    t = beregn_terskel(trinn=BKK, daily_max_kw={D1: 6, D2: 5.8}, today=D3, projected_kw=4, valgt_maal_kw=5)
    assert t.dagstak_kw == pytest.approx(3.2)
    assert t.kutt_anbefalt_kw == pytest.approx(0.8)
