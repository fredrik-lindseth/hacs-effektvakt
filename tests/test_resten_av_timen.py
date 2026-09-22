"""Tester for det brukeren faktisk lurer paa: hvor lenge til, og hvor mye kan jeg slaa paa.

Dekker `beregn_resten_av_timen` og `beregn_topp_3_oversikt` i modell.py, og at
coordinatoren legger begge ut i data-dicten sensorene leser.
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.effektvakt.coordinator import EffektvaktCoordinator
from custom_components.effektvakt.modell import (
    MAKS_PAASLAG_KW,
    beregn_resten_av_timen,
    beregn_topp_3_oversikt,
    compute_elapsed_h,
)
from tests.conftest import make_entry, make_hass_with_states, make_state

D1 = date(2026, 6, 1)
D2 = date(2026, 6, 2)
D3 = date(2026, 6, 3)
D4 = date(2026, 6, 4)


# --- minutter igjen og kW som kan legges paa --------------------------------


def test_ti_minutter_igjen_gjor_en_kw_margin_til_seks():
    """Regneeksempelet fra saken: kl. 18:50 med 1 kW margin kan du legge paa 6 kW."""
    resten = beregn_resten_av_timen(margin_kw=1.0, elapsed_h=compute_elapsed_h(datetime(2026, 6, 3, 18, 50)))
    assert resten.minutter_igjen == 10
    assert resten.kan_legge_paa_resten_av_timen_kw == pytest.approx(6.0)


def test_helt_i_starten_av_timen_er_paaslaget_lik_marginen():
    """Med hele timen igjen holder en ekstra last snittet, og margin er svaret."""
    resten = beregn_resten_av_timen(margin_kw=2.5, elapsed_h=0.0)
    assert resten.minutter_igjen == 60
    assert resten.kan_legge_paa_resten_av_timen_kw == pytest.approx(2.5)


def resten_minutter(elapsed_h: float) -> int:
    return beregn_resten_av_timen(margin_kw=1.0, elapsed_h=elapsed_h).minutter_igjen


def test_minuttene_summerer_alltid_til_seksti():
    """Nedtellingen teller ned slik elapsed_minutes_in_hour teller opp."""
    for minutt in range(60):
        elapsed_h = compute_elapsed_h(datetime(2026, 6, 3, 18, minutt, 30))
        assert resten_minutter(elapsed_h) + int(elapsed_h * 60) == 60


def test_negativ_margin_gir_ingenting_aa_legge_paa():
    resten = beregn_resten_av_timen(margin_kw=-1.5, elapsed_h=0.5)
    assert resten.kan_legge_paa_resten_av_timen_kw == 0.0


def test_uten_terskel_aa_maale_mot_er_paaslaget_ukjent():
    """Margin None betyr at det ikke finnes noe dyrere trinn. Da vet vi ikke."""
    resten = beregn_resten_av_timen(margin_kw=None, elapsed_h=0.5)
    assert resten.kan_legge_paa_resten_av_timen_kw is None
    assert resten.minutter_igjen == 30


def test_siste_sekundene_kappes_framfor_aa_gaa_mot_uendelig():
    """Formelen deler paa resten av timen. Uten tak spretter tallet til tusener."""
    resten = beregn_resten_av_timen(margin_kw=1.0, elapsed_h=compute_elapsed_h(datetime(2026, 6, 3, 18, 59, 59)))
    assert resten.kan_legge_paa_resten_av_timen_kw == MAKS_PAASLAG_KW
    assert beregn_resten_av_timen(margin_kw=1.0, elapsed_h=1.0).kan_legge_paa_resten_av_timen_kw == MAKS_PAASLAG_KW


# --- hvilke tre dager som teller --------------------------------------------


def test_de_tre_hoyeste_dagene_med_dato_og_kw():
    oversikt = beregn_topp_3_oversikt({D1: 4.0, D2: 9.0, D3: 6.0, D4: 1.0}, today=D4)
    assert [(dag.dato, dag.kw) for dag in oversikt.dager] == [
        ("2026-06-02", 9.0),
        ("2026-06-03", 6.0),
        ("2026-06-01", 4.0),
    ]


def test_dagen_som_ryker_er_den_laveste_av_de_tre():
    """I dag er ikke blant de tre, saa en hoeyere dagsmaks i dag skyver ut 4,0."""
    oversikt = beregn_topp_3_oversikt({D1: 4.0, D2: 9.0, D3: 6.0, D4: 1.0}, today=D4)
    assert oversikt.i_dag_teller_med is False
    assert oversikt.dag_som_ryker is not None
    assert oversikt.dag_som_ryker.dato == "2026-06-01"


def test_teller_dagen_alt_med_skyver_en_hoyere_time_ingen_ut():
    """Domeneregelen: er dagens topp alt blant de tre, bytter den bare ut sin egen plass."""
    oversikt = beregn_topp_3_oversikt({D1: 4.0, D2: 9.0, D3: 6.0}, today=D3)
    assert oversikt.i_dag_teller_med is True
    assert oversikt.dag_som_ryker is None


def test_faerre_enn_tre_dager_har_ledig_plass():
    oversikt = beregn_topp_3_oversikt({D1: 4.0, D2: 9.0}, today=D3)
    assert len(oversikt.dager) == 2
    assert oversikt.dag_som_ryker is None


def test_tom_maaned_gir_tom_liste():
    oversikt = beregn_topp_3_oversikt({}, today=D1)
    assert oversikt.dager == []
    assert oversikt.i_dag_teller_med is False
    assert oversikt.dag_som_ryker is None


def test_like_hoye_dager_sorteres_paa_dato_saa_listen_star_stille():
    foerst = beregn_topp_3_oversikt({D3: 5.0, D1: 5.0, D2: 5.0}, today=D4)
    igjen = beregn_topp_3_oversikt({D2: 5.0, D1: 5.0, D3: 5.0}, today=D4)
    assert [dag.dato for dag in foerst.dager] == [dag.dato for dag in igjen.dager]
    assert [dag.dato for dag in foerst.dager] == ["2026-06-01", "2026-06-02", "2026-06-03"]


# --- coordinatoren legger det ut --------------------------------------------


async def _tick(coord: EffektvaktCoordinator, naa: datetime) -> dict:
    with patch("custom_components.effektvakt.coordinator.dt_util_now", return_value=naa):
        return await coord._async_update_data()


def _coordinator(hass, entry) -> EffektvaktCoordinator:
    with patch("custom_components.effektvakt.coordinator.Store"):
        coord = EffektvaktCoordinator(hass, entry)
    coord._store = MagicMock()
    coord._store.async_load = AsyncMock(return_value=None)
    coord._store.async_save = AsyncMock()
    return coord


@pytest.mark.asyncio
async def test_coordinator_legger_ut_resten_av_timen_og_topp_3_dagene():
    hass = make_hass_with_states(
        {
            "sensor.power": make_state("3000", unit="W"),
            "sensor.energy": make_state("100.0", unit="kWh"),
        }
    )
    coord = _coordinator(hass, make_entry())
    coord._daily_max_kw = {D1: 9.0, D2: 9.5, D3: 2.0}

    data = await _tick(coord, datetime(2026, 6, 4, 18, 45, 0))

    assert data["minutter_igjen_av_timen"] == 15
    assert data["elapsed_minutes_in_hour"] == 45
    # Marginen holder seg mot taket, og paaslaget er den delt paa den siste
    # fjerdedelen av timen.
    assert data["kan_legge_paa_resten_av_timen_kw"] == pytest.approx(data["kan_legge_paa_kw"] * 4, abs=0.01)
    assert data["topp_3_dager"] == [
        {"dato": "2026-06-02", "kw": 9.5},
        {"dato": "2026-06-01", "kw": 9.0},
        {"dato": "2026-06-03", "kw": 2.0},
    ]
    assert data["topp_3_inkluderer_i_dag"] is False
    assert data["dag_som_ryker"] == {"dato": "2026-06-03", "kw": 2.0}
