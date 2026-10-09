"""Nettselskapets privatkundetabell har dokumentert omfang opp til 75 kW."""

from datetime import date, datetime
from unittest.mock import patch

import pytest

from custom_components.effektvakt.oppsett import les_trinn
from tests.conftest import make_state
from tests.test_coordinator_integration import _make_coordinator


@pytest.mark.asyncio
@pytest.mark.parametrize("kw,gyldig", [(74.999, True), (75, False), (75.001, False), (100, False)])
async def test_nettselskapet_raad_og_kostnad_folger_kildegrensen(kw, gyldig):
    states = {"sensor.power": make_state(str(kw * 1000), unit="W")}
    coord = _make_coordinator(states, {"dso": "nettselskapet"})
    coord._store_loaded = True
    coord._regnskap.current_month = "2026-10"
    coord._regnskap.daily_max_kw = {date(2026, 10, 1): kw, date(2026, 10, 2): kw}
    with patch("custom_components.effektvakt.coordinator.dt_util_now", return_value=datetime(2026, 10, 9, 14)):
        data = await coord._async_update_data()
    assert data["beregning_gyldig"] is gyldig
    if gyldig:
        assert data["trinn_na_kr"] == 3325
        assert data["risiko_niva"] is not None
    else:
        assert data["maalegrunnlag_problem"] == "fastledd_utenfor_kildegrunnlag"
        assert data["risiko_niva"] is None
        assert data["kutt_anbefalt_kw"] is None
        assert data["trinn_na_kr"] is None


def test_kataloggrensen_beholdes_men_custom_er_brukerens_egen_tariff():
    assert les_trinn(dso_id="nettselskapet", custom=None).kjent_fastledd_maks_kw == 75
    assert les_trinn(dso_id="nettselskapet", custom=[[50, 100], [None, 200]]).kjent_fastledd_maks_kw is None
