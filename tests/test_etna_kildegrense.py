"""Etna-råd må holde seg innenfor kildebekreftet topp-3-tariff."""

from datetime import date, datetime
from unittest.mock import patch

import pytest

from custom_components.effektvakt.dso import KAPASITETSTRINN_PER_DSO
from custom_components.effektvakt.modell import fastledd_innenfor_kildegrunnlag
from custom_components.effektvakt.oppsett import les_trinn
from scripts.generer_dso_fra_fri_nettleie import bygg_rader, generer
from tests.conftest import make_state
from tests.test_coordinator_integration import _make_coordinator

DAG = date(2026, 10, 9)


@pytest.mark.parametrize(
    "topper,projisert,gyldig",
    [
        ([], 75, True),
        ([], 75.001, False),
        ([25, 25], 25, True),
        ([25, 25], 25.001, False),
        ([35, 20], 20, True),
        ([80], 0, False),
    ],
)
def test_kildegrensen_bruker_projisert_topp_3_og_nedre_skranke(topper, projisert, gyldig):
    daily = {date(2026, 10, i + 1): kw for i, kw in enumerate(topper)}
    assert fastledd_innenfor_kildegrunnlag(daily_max_kw=daily, today=DAG, projected_kw=projisert, maks_kw=25) is gyldig


def test_custom_trinn_har_ikke_kataloggrense():
    assert les_trinn(dso_id="etna_nett", custom=None).kjent_fastledd_maks_kw == 25
    custom = les_trinn(dso_id="etna_nett", custom=[[25, 100], [None, 200]])
    assert custom.kjent_fastledd_maks_kw is None
    assert fastledd_innenfor_kildegrunnlag(
        daily_max_kw={}, today=DAG, projected_kw=300, maks_kw=custom.kjent_fastledd_maks_kw
    )


def test_generator_bevarer_egen_kildegrense_uten_a_endre_prisene():
    tariff = {
        "kundegrupper": ["husholdning"],
        "gyldig_fra": "2026-10-01",
        "fastledd": {"metode": "TRE_DØGNMAX_MND", "terskler": [{"terskel": 0, "pris": 3360}]},
    }
    rader, utelatt, _ = bygg_rader(
        {"etna": {"slug": "etna", "mva": 0.25, "navn": "Etna", "prisomrade": "NO1", "kjent_fastledd_maks_kw": 25}},
        {"etna": {"tariffer": [tariff]}},
        DAG,
    )
    assert not utelatt
    assert rader["etna"]["kapasitetstrinn"] == [(float("inf"), 350)]
    assert rader["etna"]["kjent_fastledd_maks_kw"] == 25
    assert '"kjent_fastledd_maks_kw": 25.0' in generer(
        {"kilde": "test", "commit": "test", "tariff_dato": "2026-10-01"}, rader
    )
    assert KAPASITETSTRINN_PER_DSO["etna_nett"]["kjent_fastledd_maks_kw"] == 25


@pytest.mark.asyncio
async def test_coordinator_ukjent_raad_utenfor_kilden_og_gjenopptakelse():
    states = {"sensor.power": make_state("78000", unit="W")}
    coord = _make_coordinator(states, {"dso": "etna_nett"})
    with patch("custom_components.effektvakt.coordinator.dt_util_now", return_value=datetime(2026, 10, 9, 14)):
        data = await coord._async_update_data()
    assert data["maalegrunnlag_gyldig"]
    assert not data["beregning_gyldig"]
    assert data["maalegrunnlag_problem"] == "fastledd_utenfor_kildegrunnlag"
    assert data["kjent_fastledd_maks_kw"] == 25
    for key in ("risiko_niva", "kutt_anbefalt_kw", "margin_kw", "kostnad_denne_timen_kr", "trinn_na_kr"):
        assert data[key] is None
    states["sensor.power"] = make_state("75000", unit="W")
    with patch("custom_components.effektvakt.coordinator.dt_util_now", return_value=datetime(2026, 10, 9, 14)):
        data = await coord._async_update_data()
    assert data["beregning_gyldig"]
    assert data["topp_3_projisert_kw"] == 25


@pytest.mark.asyncio
async def test_lagrede_topper_utenfor_kilden_fortsetter_ukjent_etter_restart():
    states = {"sensor.power": make_state("0", unit="W")}
    coord = _make_coordinator(states, {"dso": "etna_nett"})
    coord._store_loaded = True
    coord._regnskap.current_month = "2026-10"
    coord._regnskap.daily_max_kw = {date(2026, 10, i): 26 for i in (1, 2, 3)}
    with patch("custom_components.effektvakt.coordinator.dt_util_now", return_value=datetime(2026, 10, 9, 14)):
        data = await coord._async_update_data()
    assert not data["beregning_gyldig"]
    lagret = coord._store.async_save.call_args.args[0]
    ny = _make_coordinator(states, {"dso": "etna_nett"})
    ny._store.async_load.return_value = lagret
    with patch("custom_components.effektvakt.coordinator.dt_util_now", return_value=datetime(2026, 10, 9, 14)):
        data = await ny._async_update_data()
    assert not data["beregning_gyldig"]
    assert data["topp_3_snitt_denne_maned_kw"] == 26
