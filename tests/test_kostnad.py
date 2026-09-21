"""Tester for kostnadsberegningen bak sensor.effektvakt_kostnad_neste_trinn."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.effektvakt.coordinator import (
    KOSTNAD_FELT_NAVN,
    EffektvaktCoordinator,
    compute_kostnad,
)
from custom_components.effektvakt.dso import KAPASITETSTRINN_PER_DSO
from tests.conftest import make_entry, make_hass_with_states, make_state

BKK = list(KAPASITETSTRINN_PER_DSO["bkk"]["kapasitetstrinn"])

D1 = date(2026, 6, 1)
D2 = date(2026, 6, 2)
D3 = date(2026, 6, 3)


def test_bkk_trinn_er_som_forventet():
    """Regneeksemplene under hviler på disse prisene."""
    assert BKK[:5] == [(2.0, 155), (5.0, 250), (10.0, 415), (15.0, 600), (20.0, 770)]


def test_tre_dager_over_trinnet_loepet_er_kjort():
    """6/7/8 kW gir topp-3 på 7,0: trinn 415, og trinnet under er utenfor rekkevidde."""
    info = compute_kostnad(trinn=BKK, daily_max_kw={D1: 6.0, D2: 7.0, D3: 8.0}, today=D3, projected_kw=5.0)
    assert info is not None
    assert info.topp_3_projisert_kw == pytest.approx(7.0)
    assert info.trinn_na_kr == 415
    assert info.trinn_na_ovre_grense_kw == 10.0
    assert info.trinn_neste_kr == 600
    assert info.kostnad_neste_trinn_kr == 185
    assert info.besparelse_trinn_under_kr == 165
    assert info.minste_mulige_topp_3_kw == pytest.approx(7.0)
    assert info.trinn_under_oppnaelig is False
    assert info.hoyeste_trinn is False


def test_en_dag_logget_trinn_under_er_oppnaelig():
    """Én dag på 7 kW: samme trinn og samme hopp, men måneden kan fortsatt reddes."""
    info = compute_kostnad(trinn=BKK, daily_max_kw={D1: 7.0}, today=D2, projected_kw=6.0)
    assert info is not None
    assert info.topp_3_projisert_kw == pytest.approx(6.5)
    assert info.trinn_na_kr == 415
    assert info.kostnad_neste_trinn_kr == 185
    assert info.besparelse_trinn_under_kr == 165
    assert info.minste_mulige_topp_3_kw == pytest.approx(2.333, abs=0.001)
    assert info.trinn_under_oppnaelig is True


def test_denne_timen_loefter_maneden_et_trinn():
    """9/9,5 kW logget og 12 kW projisert nå: timen er i ferd med å låse inn 185 kr."""
    info = compute_kostnad(trinn=BKK, daily_max_kw={D1: 9.0, D2: 9.5}, today=D3, projected_kw=12.0)
    assert info is not None
    assert info.topp_3_projisert_kw == pytest.approx(10.167, abs=0.001)
    assert info.trinn_na_kr == 600
    assert info.trinn_neste_kr == 770
    assert info.kostnad_neste_trinn_kr == 170
    assert info.kostnad_denne_timen_kr == 185


def test_dagens_egen_maks_beholdes_naar_projisert_er_lavere():
    """Har dagen alt en høyere time bak seg, teller den, ikke den rolige timen nå."""
    info = compute_kostnad(trinn=BKK, daily_max_kw={D1: 6.0, D2: 9.0}, today=D2, projected_kw=1.0)
    assert info is not None
    assert info.topp_3_projisert_kw == pytest.approx(7.5)


def test_rolig_time_koster_ingenting():
    """Ligger timen under det topp-3 alt er, er kostnaden for timen null, aldri negativ."""
    info = compute_kostnad(trinn=BKK, daily_max_kw={D1: 12.0, D2: 12.0}, today=D3, projected_kw=0.5)
    assert info is not None
    assert info.kostnad_denne_timen_kr == 0


def test_laveste_trinn_har_ingen_besparelse():
    info = compute_kostnad(trinn=BKK, daily_max_kw={}, today=D1, projected_kw=1.0)
    assert info is not None
    assert info.trinn_na_kr == 155
    assert info.trinn_na_ovre_grense_kw == 2.0
    assert info.besparelse_trinn_under_kr == 0
    assert info.trinn_under_oppnaelig is False
    assert info.kostnad_neste_trinn_kr == 95


def test_hoyeste_trinn_har_ingen_vei_opp():
    """Øverste trinn har ingen terskel over seg: hoppet er 0 og grensen serialiseres som None."""
    info = compute_kostnad(trinn=BKK, daily_max_kw={}, today=D1, projected_kw=200.0)
    assert info is not None
    assert info.hoyeste_trinn is True
    assert info.kostnad_neste_trinn_kr == 0
    assert info.trinn_neste_kr is None
    assert info.trinn_na_ovre_grense_kw is None
    assert info.trinn_na_kr == 6900


def test_over_hoyeste_terskel_i_egendefinerte_trinn():
    """Egendefinerte trinn uten et åpent topptrinn: alt over siste terskel er øverste trinn."""
    egne = [(2.0, 155), (5.0, 250), (10.0, 415)]
    info = compute_kostnad(trinn=egne, daily_max_kw={D1: 30.0}, today=D2, projected_kw=30.0)
    assert info is not None
    assert info.hoyeste_trinn is True
    assert info.trinn_na_kr == 415
    assert info.trinn_na_ovre_grense_kw == 10.0
    assert info.kostnad_neste_trinn_kr == 0


def test_ukjent_nettselskap_gir_none():
    assert compute_kostnad(trinn=[], daily_max_kw={D1: 7.0}, today=D2, projected_kw=6.0) is None


@pytest.mark.asyncio
async def test_coordinator_eksponerer_kostnadsnoklene():
    """Sensoren i T2 leser disse nøklene rett fra coordinator-dataene."""
    entry = make_entry()
    hass = make_hass_with_states(
        {
            "sensor.power": make_state("3000", unit="W"),
            "sensor.energy": make_state("100.0", unit="kWh"),
        }
    )
    with patch("custom_components.effektvakt.coordinator.Store"):
        coord = EffektvaktCoordinator(hass, entry)
    coord._store = MagicMock()
    coord._store.async_load = AsyncMock(return_value=None)
    coord._store.async_save = AsyncMock()
    coord._daily_max_kw = {D1: 9.0, D2: 9.5}

    with patch(
        "custom_components.effektvakt.coordinator.dt_util_now",
        return_value=datetime(2026, 6, 3, 18, 30, 0),
    ):
        data = await coord._async_update_data()

    assert set(KOSTNAD_FELT_NAVN) <= set(data)
    assert data["trinn_na_kr"] == 415
    assert data["kostnad_neste_trinn_kr"] == 185
    assert data["hoyeste_trinn"] is False
    # Den gamle nøkkelen står urørt og følger den projiserte timen (1,5 kW), ikke topp-3
    assert data["next_tier_pris_per_maned"] == 155


@pytest.mark.asyncio
async def test_coordinator_gir_none_uten_kjente_trinn():
    entry = make_entry(dso="finnes_ikke")
    hass = make_hass_with_states({"sensor.power": make_state("3000", unit="W")})
    with patch("custom_components.effektvakt.coordinator.Store"):
        coord = EffektvaktCoordinator(hass, entry)
    coord._store = MagicMock()
    coord._store.async_load = AsyncMock(return_value=None)
    coord._store.async_save = AsyncMock()

    with patch(
        "custom_components.effektvakt.coordinator.dt_util_now",
        return_value=datetime(2026, 6, 3, 18, 30, 0),
    ):
        data = await coord._async_update_data()

    assert all(data[navn] is None for navn in KOSTNAD_FELT_NAVN)
