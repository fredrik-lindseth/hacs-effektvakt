"""Tester for trinn-tabellen et oppsett faar, og for at hullene i den sier fra.

To ting feilet stille foer september 2026: en config entry som peker paa et
fjernet nettselskap fikk tom tabell, og en egendefinert tabell uten et aapent
oeverste trinn meldte god margin uansett hvor hoeyt forbruket gikk.
"""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers import issue_registry as ir

from custom_components.effektvakt import (
    ISSUE_MANGLER_TOPPTRINN,
    ISSUE_UKJENT_DSO,
    async_setup_entry,
)
from custom_components.effektvakt.dso import KAPASITETSTRINN_PER_DSO
from custom_components.effektvakt.oppsett import les_trinn
from tests.conftest import make_entry

# --- trinn-tabellen ---------------------------------------------------------


def test_kjent_nettselskap_gir_tabellen_sin():
    oppsett = les_trinn(dso_id="bkk", custom=None)
    assert oppsett.trinn == list(KAPASITETSTRINN_PER_DSO["bkk"]["kapasitetstrinn"])
    assert oppsett.dso_ukjent is False
    assert oppsett.mangler_topptrinn is False


def test_fjernet_nettselskap_melder_fra_framfor_aa_gi_tom_tabell():
    """Synken 22.09.2026 fjernet blant annet area_nett. Noekkelen ligger igjen i config entryen."""
    oppsett = les_trinn(dso_id="area_nett", custom=None)
    assert oppsett.trinn == []
    assert oppsett.dso_ukjent is True
    assert oppsett.dso_noekkel == "area_nett"


def test_oppsett_uten_nettselskap_er_ogsaa_ukjent():
    oppsett = les_trinn(dso_id=None, custom=None)
    assert oppsett.dso_ukjent is True
    assert oppsett.trinn == []


def test_egendefinerte_trinn_med_null_som_oeverste_terskel():
    """null er trinnet uten oevre grense, slik de innebygde slutter paa (inf, pris)."""
    oppsett = les_trinn(dso_id="custom", custom=[[2, 155], [5, 250], [None, 415]])
    assert oppsett.trinn[:2] == [(2.0, 155), (5.0, 250)]
    assert math.isinf(oppsett.trinn[-1][0])
    assert oppsett.trinn[-1][1] == 415
    assert oppsett.mangler_topptrinn is False


def test_egendefinerte_trinn_uten_topptrinn_meldes():
    """Over 10 kW finnes det ingen pris, og da melder vakten god margin i taushet."""
    oppsett = les_trinn(dso_id="custom", custom=[[2, 155], [5, 250], [10, 415]])
    assert oppsett.mangler_topptrinn is True
    assert oppsett.hoyeste_terskel_kw == 10.0


def test_egendefinerte_trinn_vinner_over_nettselskapet():
    oppsett = les_trinn(dso_id="bkk", custom=[[3, 100], [None, 200]])
    assert oppsett.trinn[0] == (3.0, 100)
    assert oppsett.dso_noekkel == "custom"
    assert oppsett.dso_ukjent is False


# --- repair-meldingene ------------------------------------------------------


def _hass():
    hass = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_entries = MagicMock(return_value=[])
    hass.services.has_service = MagicMock(return_value=True)
    return hass


async def _sett_opp(entry) -> None:
    entry.runtime_data = None
    ir.reset_mock()
    with (
        patch("custom_components.effektvakt.async_track_time_interval"),
        patch("custom_components.effektvakt.async_register_frontend", AsyncMock()),
        # Stubben for DataUpdateCoordinator i conftest har ingen
        # foerstegangsoppfriskning aa overstyre, derfor create=True.
        patch(
            "custom_components.effektvakt.EffektvaktCoordinator.async_config_entry_first_refresh",
            AsyncMock(),
            create=True,
        ),
        patch("custom_components.effektvakt.coordinator.Store"),
    ):
        assert await async_setup_entry(_hass(), entry) is True


def _opprettede_issues() -> dict[str, dict]:
    return {kall.args[2]: kall.kwargs for kall in ir.async_create_issue.call_args_list}


def _slettede_issues() -> list[str]:
    return [kall.args[2] for kall in ir.async_delete_issue.call_args_list]


@pytest.mark.asyncio
async def test_ukjent_nettselskap_gir_repair_melding():
    """Sensorene gaar tomme uansett. Da skal brukeren i det minste vite hvorfor."""
    await _sett_opp(make_entry(entry_id="abc", dso="area_nett"))

    issues = _opprettede_issues()
    assert f"{ISSUE_UKJENT_DSO}_abc" in issues
    assert issues[f"{ISSUE_UKJENT_DSO}_abc"]["translation_key"] == ISSUE_UKJENT_DSO
    assert issues[f"{ISSUE_UKJENT_DSO}_abc"]["translation_placeholders"] == {"dso": "area_nett"}
    assert issues[f"{ISSUE_UKJENT_DSO}_abc"]["is_fixable"] is False


@pytest.mark.asyncio
async def test_egendefinerte_trinn_uten_topptrinn_gir_repair_melding():
    entry = make_entry(entry_id="abc", dso="custom", kapasitetstrinn_custom=[[2, 155], [5, 250], [10, 415]])
    await _sett_opp(entry)

    issues = _opprettede_issues()
    assert issues[f"{ISSUE_MANGLER_TOPPTRINN}_abc"]["translation_placeholders"] == {"hoyeste_kw": "10"}


@pytest.mark.asyncio
async def test_et_oppsett_uten_problemer_rydder_begge_meldingene():
    """Har brukeren rettet opp, skal meldingen vekk uten at noen maa trykke bort noe."""
    await _sett_opp(make_entry(entry_id="abc", dso="bkk"))

    assert ir.async_create_issue.call_count == 0
    assert _slettede_issues() == [f"{ISSUE_UKJENT_DSO}_abc", f"{ISSUE_MANGLER_TOPPTRINN}_abc"]
