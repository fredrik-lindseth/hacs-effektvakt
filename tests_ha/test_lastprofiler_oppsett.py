"""Profilvalg gjennom HA-flow, sensor, recorderlivssyklus og lastvern."""

from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType

from custom_components.effektvakt.lastprofil import Effektpunkt, analyser_lastprofil
from custom_components.effektvakt.lastvern import DATA_LASTVERN, Lastkutt
from custom_components.effektvakt.profilhistorikk import Profilhistorikk

from .conftest import LAST, LAST_BRYTER, LAST_SENSOR, lag_entry
from .test_config_flow import _meny

ENERGI = "sensor.effektvakt_estimert_kuttenergi_resten_av_timen"


def _tid(hass, freezer):
    now = datetime(2026, 10, 10, 10, 30, tzinfo=ZoneInfo("Europe/Oslo"))
    freezer.move_to(now)
    for state in hass.states.async_all():
        hass.states.async_set(state.entity_id, state.state, state.attributes)
    return now


async def test_manuell_profil_uten_maaling_gir_energi_men_ikke_maalt_kutt(hass, maalere, freezer):
    _tid(hass, freezer)
    entry = lag_entry(laster=[])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(ENERGI) is None
    res = await _meny(hass, entry, "legg_til_last")
    res = await hass.config_entries.options.async_configure(
        res["flow_id"],
        {
            "navn": "Gulvvarme",
            "profil": "manuell",
            "nominell_w": 2300,
            "arbeidssyklus_pct": 15,
            "maks_kutt_minutter": 60,
        },
    )
    assert res["type"] is FlowResultType.MENU
    await hass.async_block_till_done()
    state = hass.states.get(ENERGI)
    assert float(state.state) == pytest.approx(0.1725)
    assert state.attributes["unit_of_measurement"] == "kWh"
    assert "state_class" not in state.attributes
    assert hass.states.get("sensor.effektvakt_tilgjengelig_kutt") is None
    profil = state.attributes["lastprofiler"]["manuell:Gulvvarme"]
    assert profil["planleggingsestimat"] is True
    assert profil["arbeidssyklus_pct"] == 15
    assert entry.runtime_data.data["profilraad_energi_kwh"] == 0

    res = await _meny(hass, entry, "velg_last")
    res = await hass.config_entries.options.async_configure(res["flow_id"], {"effekt_sensor": "manuell:Gulvvarme"})
    assert res["step_id"] == "rediger_last"
    await hass.config_entries.options.async_configure(res["flow_id"], {"slett": True})
    await hass.async_block_till_done()
    assert hass.states.get(ENERGI) is None
    assert not entry.runtime_data.laster


async def test_manuell_profil_krever_grunnlag_og_duplikater_avvises(hass, maalere):
    entry = lag_entry(laster=[])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    res = await _meny(hass, entry, "legg_til_last")
    res = await hass.config_entries.options.async_configure(res["flow_id"], {"profil": "manuell"})
    assert res["errors"]["navn"] == "profil_navn_kreves"
    assert res["errors"]["arbeidssyklus_pct"] == "profil_felt_kreves"
    svar = {"profil": "manuell", "navn": "Varme", "nominell_w": 300, "arbeidssyklus_pct": 15}
    res = await hass.config_entries.options.async_configure(res["flow_id"], svar)
    assert res["type"] is FlowResultType.MENU
    await hass.async_block_till_done()
    res = await _meny(hass, entry, "legg_til_last")
    res = await hass.config_entries.options.async_configure(res["flow_id"], svar)
    assert res["errors"]["navn"] == "last_finnes_allerede"
    assert len(entry.data["laster"]) == 1


async def test_historikkprofil_oppdaterer_sensor_og_styringsvalg_er_valgfritt(hass, maalere, freezer):
    now = _tid(hass, freezer)
    start = now - timedelta(hours=2)
    profile = analyser_lastprofil(
        [
            Effektpunkt(start, 0),
            Effektpunkt(start + timedelta(minutes=10), 2000),
            Effektpunkt(start + timedelta(minutes=30), 0),
            Effektpunkt(start + timedelta(minutes=50), 2000),
            Effektpunkt(start + timedelta(minutes=70), 0),
        ],
        start=start,
        slutt=now,
        terskel_w=1000,
    )
    calls = []

    async def hent(self, terskler, **kwargs):
        calls.append(terskler)
        self.profiler = {LAST_SENSOR: profile}
        self.oppdatert = now
        self.status = "klar"

    entry = lag_entry(laster=[{**LAST, "profil": "auto", "maks_kutt_minutter": 10}])
    entry.add_to_hass(hass)
    with patch.object(Profilhistorikk, "async_oppdater", hent):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)
    assert calls == [{LAST_SENSOR: 1000}]
    state = hass.states.get(ENERGI)
    assert float(state.state) == pytest.approx(0.225)
    profil = state.attributes["lastprofiler"][LAST_SENSOR]
    assert profil["hele_sykluser"] == 2
    assert profil["planleggingsestimat"] is False
    assert profil["maks_kutt_minutter"] == 10
    assert entry.runtime_data.data["tilgjengelig_kutt_kw"] == 1.8
    assert not entry.runtime_data.bruk_lastprofiler

    # Eget styrt kutt gir ikke ny tilgjengelig energi, selv foer neste W-rapport.
    vern = hass.data[DATA_LASTVERN]
    vern.kutt[LAST_BRYTER] = Lastkutt("automation.test", now.timestamp() + 600, 300, start=now.timestamp())
    await entry.runtime_data.async_refresh()
    assert entry.runtime_data.data["estimert_kuttenergi_resten_av_timen_kwh"] == 0
    assert entry.runtime_data.data["lastprofiler"][LAST_SENSOR]["kilde"] == "egen_kuttet"
    vern.kutt.clear()
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_climate_er_aktuator_ikke_bevis_paa_varme(hass, maalere, freezer):
    _tid(hass, freezer)
    hass.states.async_set("climate.gulv", "heat", {"temperature": 22, "hvac_action": "idle"})
    entry = lag_entry(
        laster=[
            {"navn": "Gulv", "bryter": "climate.gulv", "profil": "manuell", "nominell_w": 2000, "arbeidssyklus_pct": 15}
        ]
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    data = entry.runtime_data.data
    assert data["tilgjengelig_kutt_kw"] is None
    assert data["profilraad_energi_kwh"] == 0
    assert data["estimert_kuttenergi_resten_av_timen_kwh"] == pytest.approx(0.15)


async def test_valgfritt_profilraad_bruker_energi_uten_aa_endre_maalt_kw(hass, maalere, freezer):
    _tid(hass, freezer)
    hass.states.async_set("sensor.hus_effekt", "6000", {"unit_of_measurement": "W", "device_class": "power"})
    hass.states.async_set(LAST_SENSOR, "2400", {"unit_of_measurement": "W", "device_class": "power"})
    entry = lag_entry(
        laster=[{**LAST, "profil": "manuell", "nominell_w": 2400, "arbeidssyklus_pct": 15, "typisk_paa_minutter": 10}]
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coord = entry.runtime_data
    coord._regnskap.current_hour_kwh = 3
    coord._regnskap.daily_max_kw = {datetime(2026, 10, 8).date(): 5, datetime(2026, 10, 9).date(): 5}
    await coord.async_refresh()
    assert coord.data["unngaaelig_besparelse_kr"] == 165
    assert coord.data["kutt_mulig"]
    assert coord.data["tilgjengelig_kutt_kw"] == 2.4
    assert coord.data["estimert_kuttenergi_resten_av_timen_kwh"] == pytest.approx(0.2)

    coord.bruk_lastprofiler = True
    await coord.async_refresh()
    assert coord.data["tilgjengelig_kutt_kw"] == 2.4
    assert coord.data["unngaaelig_besparelse_kr"] == 0
    assert not coord.data["kutt_mulig"]
    # Den faktiske innstillingen lagres og gjenopprettes ogsaa gjennom options.
    res = await _meny(hass, entry, "innstillinger")
    await hass.config_entries.options.async_configure(
        res["flow_id"],
        {
            "safety_buffer_kw": 1,
            "min_risiko_for_kutt": "like_under_terskel",
            "risiko_holdetid_minutter": 5,
            "bruk_lastprofiler": True,
        },
    )
    await hass.async_block_till_done()
    assert entry.data["bruk_lastprofiler"] is True
    assert entry.runtime_data.bruk_lastprofiler
