"""Kuttet maa virke fysisk og fortsatt spare et kapasitetstrinn."""

from datetime import date

import pytest

from custom_components.effektvakt.config_flow import _dso_options, parse_kapasitetstrinn
from custom_components.effektvakt.dso import KAPASITETSTRINN_PER_DSO
from custom_components.effektvakt.modell import beregn_terskel, vurder_kuttkriterium
from custom_components.effektvakt.oppsett import les_trinn
from scripts.generer_dso_fra_fri_nettleie import bygg_rader, generer, kr_mnd

DAG = date(2026, 10, 9)
ANDRE = {date(2026, 10, 1): 4.99, date(2026, 10, 2): 4.99}
TRINN = [(2.0, 155), (5.0, 250), (10.0, 415), (float("inf"), 600)]


def test_ti_minutter_igjen_krever_seks_kw_reduksjon():
    terskel = beregn_terskel(trinn=TRINN, daily_max_kw=ANDRE, today=DAG, projected_kw=6, elapsed_h=50 / 60)
    assert terskel.margin_kw == -1
    assert terskel.kutt_anbefalt_kw == pytest.approx(6)
    assert 6 - terskel.kutt_anbefalt_kw * (1 - 50 / 60) == pytest.approx(5)


def kriterium(*, minutt, brukt, projisert=5.2, kutt=0.3):
    return vurder_kuttkriterium(
        trinn=TRINN,
        daily_max_kw=ANDRE,
        today=DAG,
        projected_kw=projisert,
        actual_kwh_this_hour=brukt,
        elapsed_h=minutt / 60,
        tilgjengelig_kutt_kw=kutt,
    )


def test_liten_last_kuttes_mens_timen_kan_berges():
    svar = kriterium(minutt=10, brukt=5.2 * 10 / 60)
    assert svar.oppfylt
    assert svar.unngaaelig_besparelse_kr == 165
    assert pytest.approx(4.95) == 5.2 - 0.3 * (1 - 10 / 60)


def test_samme_last_for_sent_gir_ikke_meningsloest_kutt():
    svar = kriterium(minutt=53, brukt=5.2 * 53 / 60)
    assert not svar.oppfylt
    assert svar.mulig_besparelse_kr == 165
    assert svar.unngaaelig_besparelse_kr == 0


def test_allerede_laast_energi_gir_ikke_kutt_selv_med_stor_last():
    svar = kriterium(minutt=54, brukt=5.2, projisert=5.8, kutt=6)
    assert not svar.kutt_mulig
    assert not svar.oppfylt


def test_kort_vannkoker_gir_ikke_tidlig_smaalast_kutt():
    assert not kriterium(minutt=3, brukt=3.5 / 60 + 5.5 * 2 / 60, projisert=5.5).oppfylt


@pytest.mark.parametrize("dso", ["sor_aurdal_energi", "tinfos"])
def test_unsupported_fastledd_gir_ingen_topp3_raad(dso):
    oppsett = les_trinn(dso_id=dso, custom=None)
    assert not oppsett.dso_ukjent
    assert oppsett.metode_ikke_stoettet
    assert oppsett.trinn == []
    assert dso not in [option["value"] for option in _dso_options()]


def test_sae_tariff_bevarer_halve_kroner():
    # Offisiell tariff fra 1.9.2026: sae.no/uploads/Kundeinformasjon/2026_09_Kundeinformasjon_tariffer.pdf, side 2.
    sae = KAPASITETSTRINN_PER_DSO["sor_aurdal_energi"]
    assert sae["fastledd_metode"] == "MND_MAX"
    assert sae["kapasitetstrinn"][:2] == [(5.0, 562.5), (8.0, 650.0)]
    assert sae["kapasitetstrinn"][1][1] - sae["kapasitetstrinn"][0][1] == 87.5
    assert parse_kapasitetstrinn("[[5,562.5],[null,650]]") == [(5.0, 562.5), (None, 650.0)]


def test_generator_bevarer_metode_og_tariffpresisjon():
    tariff = {
        "kundegrupper": ["husholdning"],
        "gyldig_fra": "2026-09-01",
        "fastledd": {"metode": "MND_MAX", "terskler": [{"terskel": 0, "pris": 5400}, {"terskel": 5, "pris": 6240}]},
    }
    rader, utelatt, ikke_nve = bygg_rader(
        {"sae": {"slug": "sae", "mva": 0.25, "navn": "SAE", "prisomrade": "NO1"}}, {"sae": {"tariffer": [tariff]}}, DAG
    )
    assert not utelatt
    assert ikke_nve == ["sae (MND_MAX)"]
    assert rader["sae"]["fastledd_metode"] == "MND_MAX"
    assert kr_mnd(5400, 0.25) == 562.5
    kilde = generer({"kilde": "test", "commit": "test", "tariff_dato": "2026-09-01"}, rader)
    assert '"fastledd_metode": "MND_MAX"' in kilde
    assert "562.5" in kilde
