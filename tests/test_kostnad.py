"""Tester for kostnadsberegningen bak sensor.effektvakt_kostnad_neste_trinn."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given
from hypothesis import strategies as st

from custom_components.effektvakt.coordinator import EffektvaktCoordinator
from custom_components.effektvakt.dso import KAPASITETSTRINN_PER_DSO
from custom_components.effektvakt.modell import KOSTNAD_FELT_NAVN, beregn_terskel, compute_kostnad
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


def test_en_dag_logget_deler_fortsatt_paa_tre():
    """Én dag på 7 kW og 6 kW projisert nå: 13 / 3 = 4,33, altså 5 kW-trinnet.

    Den tredje dagen finnes ikke ennå og teller som null. Delte vi på antall
    dager i stedet, ville de samme to dagene gitt 6,5 og dermed 10 kW-trinnet,
    og tallet ville falt igjen så snart en rolig dag nummer tre kom til.
    """
    info = compute_kostnad(trinn=BKK, daily_max_kw={D1: 7.0}, today=D2, projected_kw=6.0)
    assert info is not None
    assert info.topp_3_projisert_kw == pytest.approx(4.333, abs=0.001)
    assert info.trinn_na_kr == 250
    assert info.kostnad_neste_trinn_kr == 165
    assert info.besparelse_trinn_under_kr == 95
    assert info.minste_mulige_topp_3_kw == pytest.approx(2.333, abs=0.001)
    # 2 kW-trinnet er ikke lenger mulig: én dag på 7 kW gir minst 2,33
    assert info.trinn_under_oppnaelig is False


def test_trinn_under_er_oppnaelig_naar_skranken_tillater_det():
    info = compute_kostnad(trinn=BKK, daily_max_kw={D1: 5.0}, today=D2, projected_kw=6.0)
    assert info is not None
    assert info.minste_mulige_topp_3_kw == pytest.approx(1.667, abs=0.001)
    assert info.trinn_na_ovre_grense_kw == 5.0
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
    assert info.topp_3_projisert_kw == pytest.approx(5.0)


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
    info = compute_kostnad(trinn=BKK, daily_max_kw={D1: 400.0, D2: 400.0}, today=D3, projected_kw=400.0)
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
    # Projisert 1,5 kW (3 kW i et halvt kvarter igjen av timen) løfter ingenting:
    # 9,0 og 9,5 gir 18,5 / 3 = 6,17 alene, og timen koster derfor null.
    assert data["kostnad_denne_timen_kr"] == 0
    # Måltrinnet er det samme trinnet, og det er dette marginen måles mot
    assert data["maal_terskel_kw"] == 10.0
    assert data["maal_trinn_kr"] == 415


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


# --- risiko og kostnad skal ikke motsi hverandre ----------------------------


def _maaned(verdier: list[float]) -> dict[date, float]:
    return {date(2026, 6, 1 + i): kw for i, kw in enumerate(verdier)}


@given(
    andre=st.lists(st.floats(min_value=0.0, max_value=25.0, allow_nan=False), min_size=0, max_size=5),
    dagens_maks=st.floats(min_value=0.0, max_value=25.0, allow_nan=False),
    projisert=st.floats(min_value=0.0, max_value=30.0, allow_nan=False),
)
def test_margin_i_pluss_betyr_alltid_at_timen_er_gratis(andre: list[float], dagens_maks: float, projisert: float):
    """Invarianten reviewen etterlyste: risikosensoren sier aldri «rolig» mens kroner påløper.

    Marginen er en ledende indikator og slår ut på eller før kostnaden. Det
    motsatte, at kostnadssensoren viser penger mens risikoen melder god margin,
    skal være umulig.
    """
    i_dag = date(2026, 6, 20)
    daily = _maaned(andre)
    daily[i_dag] = dagens_maks

    terskel = beregn_terskel(trinn=BKK, daily_max_kw=daily, today=i_dag, projected_kw=projisert)
    kostnad = compute_kostnad(trinn=BKK, daily_max_kw=daily, today=i_dag, projected_kw=projisert)
    assert kostnad is not None

    if terskel.margin_kw is not None and terskel.margin_kw >= 0:
        assert kostnad.kostnad_denne_timen_kr == 0


def test_kostnaden_kan_vaere_null_mens_marginen_er_negativ():
    """Den motsatte veien er tillatt, og det er kappet ved T som gjør det.

    To dager på 4,0 og en projeksjon på 5,0: måneden blir stående i 5 kW-trinnet
    uansett, for 13 / 3 = 4,33. Men dagen i dag er over sin andel av de tre
    plassene, og fortsetter resten av måneden i samme spor, ryker trinnet.
    Timen koster ikke noe ennå, den bruker opp slarken.
    """
    daily = {D1: 4.0, D2: 4.0}
    terskel = beregn_terskel(trinn=BKK, daily_max_kw=daily, today=D3, projected_kw=5.0)
    kostnad = compute_kostnad(trinn=BKK, daily_max_kw=daily, today=D3, projected_kw=5.0)
    assert terskel.dagstak_kw == pytest.approx(5.0)
    assert terskel.margin_kw == pytest.approx(0.0)
    assert kostnad is not None
    assert kostnad.kostnad_denne_timen_kr == 0

    # Ett hakk til, og marginen er negativ mens kronene fortsatt venter
    over = beregn_terskel(trinn=BKK, daily_max_kw=daily, today=D3, projected_kw=6.0)
    over_kr = compute_kostnad(trinn=BKK, daily_max_kw=daily, today=D3, projected_kw=6.0)
    assert over.margin_kw == pytest.approx(-1.0)
    assert over_kr is not None
    assert over_kr.kostnad_denne_timen_kr == 0

    # Og der de andre dagene alt har spist budsjettet, faller de sammen
    tungt = {D1: 6.0, D2: 5.8}
    assert beregn_terskel(trinn=BKK, daily_max_kw=tungt, today=D3, projected_kw=4.0).margin_kw == pytest.approx(-0.8)
    tungt_kr = compute_kostnad(trinn=BKK, daily_max_kw=tungt, today=D3, projected_kw=4.0)
    assert tungt_kr is not None
    assert tungt_kr.kostnad_denne_timen_kr == 165


def test_topp_3_projisert_er_aldri_under_skranken():
    """Begge deler på tre, så det projiserte tallet ligger alltid over eller på skranken."""
    daily = {D1: 9.0, D2: 1.0}
    for p in (0.0, 0.5, 5.0, 20.0):
        info = compute_kostnad(trinn=BKK, daily_max_kw=daily, today=D3, projected_kw=p)
        assert info is not None
        assert info.topp_3_projisert_kw >= info.minste_mulige_topp_3_kw
        assert info.kostnad_denne_timen_kr >= 0


# --- er trinnet under noe man kunne siktet paa? -----------------------------


def test_trinnet_under_er_urealistisk_naar_huset_aldri_har_vaert_i_naerheten():
    """Fredriks sak: under BKKs 2 til 5 kW ligger 0 til 2 kW, som ingen bolig naar.

    `trinn_under_oppnaelig` er False hele aaret, og en melding om at trinnet
    under er tapt ville staatt permanent. Den skal bare vises naar trinnet
    under er noe man kunne siktet paa.
    """
    info = compute_kostnad(trinn=BKK, daily_max_kw={D1: 4.0, D2: 4.5, D3: 3.8}, today=D3, projected_kw=4.0)
    assert info is not None
    assert info.trinn_na_ovre_grense_kw == 5.0
    assert info.trinn_under_terskel_kw == 2.0
    assert info.trinn_under_oppnaelig is False
    assert info.trinn_under_realistisk is False


def test_trinnet_under_er_realistisk_naar_de_roligste_dagene_ligger_der():
    """En enkelt topp loefter maaneden til 10 kW-trinnet, men huset bor i 5 kW-trinnet.

    De tre roligste dagene snitter 4,43. En maaned bygget av dager som disse
    hadde landet under 5 kW, saa spoersmaalet om aa komme ned dit er ekte.
    """
    dager = {D1: 4.8, D2: 9.0, D3: 4.0, date(2026, 6, 4): 4.5}
    info = compute_kostnad(trinn=BKK, daily_max_kw=dager, today=date(2026, 6, 4), projected_kw=9.0)
    assert info is not None
    assert info.trinn_na_ovre_grense_kw == 10.0
    assert info.trinn_under_terskel_kw == 5.0
    assert info.trinn_under_oppnaelig is False
    assert info.trinn_under_realistisk is True


def test_forrige_maaned_teller_som_belegg():
    """Landet forrige maaned der, er trinnet naaelig selv om denne maaneden er tapt."""
    dager = {D1: 12.0, D2: 11.0, D3: 13.0}
    uten_historikk = compute_kostnad(trinn=BKK, daily_max_kw=dager, today=D3, projected_kw=12.0)
    assert uten_historikk is not None
    assert uten_historikk.trinn_under_terskel_kw == 10.0
    assert uten_historikk.trinn_under_realistisk is False

    info = compute_kostnad(
        trinn=BKK,
        daily_max_kw=dager,
        today=D3,
        projected_kw=12.0,
        forrige_maaned_topp_3_kw=9.0,
    )
    assert info is not None
    assert info.trinn_under_oppnaelig is False
    assert info.trinn_under_realistisk is True


def test_uten_dager_aa_maale_paa_sier_vi_ingenting():
    """Helt i starten av en maaned uten historikk finnes det ikke belegg for en dom."""
    info = compute_kostnad(trinn=BKK, daily_max_kw={}, today=D1, projected_kw=6.0)
    assert info is not None
    assert info.trinn_under_realistisk is False


def test_laveste_trinn_har_ingen_terskel_under_seg():
    info = compute_kostnad(trinn=BKK, daily_max_kw={D1: 1.0}, today=D2, projected_kw=1.0)
    assert info is not None
    assert info.trinn_under_terskel_kw is None
    assert info.trinn_under_realistisk is False
