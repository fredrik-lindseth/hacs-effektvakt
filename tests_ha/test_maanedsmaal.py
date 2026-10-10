"""Maanedsmaal i ekte HA: options, reload, entiteter og ukjent grunnlag."""

from datetime import datetime
from zoneinfo import ZoneInfo

from homeassistant.data_entry_flow import FlowResultType

from custom_components.effektvakt.const import CONF_VALGT_MAAL_KW

from .conftest import POWER_SENSOR, lag_entry
from .test_config_flow import _meny


async def test_velg_og_slaa_av_maal_beholder_resten_av_oppsettet(hass, maalere):
    entry = lag_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    foer = dict(entry.data)
    res = await _meny(hass, entry, "maaltrinn")
    assert res["step_id"] == "maaltrinn"
    res = await hass.config_entries.options.async_configure(res["flow_id"], {CONF_VALGT_MAAL_KW: "5.0"})
    assert res["type"] is FlowResultType.MENU
    await hass.async_block_till_done()
    assert dict(entry.data) == {**foer, CONF_VALGT_MAAL_KW: 5.0}
    assert entry.runtime_data.valgt_maal_kw == 5.0
    res = await _meny(hass, entry, "maaltrinn")
    await hass.config_entries.options.async_configure(res["flow_id"], {CONF_VALGT_MAAL_KW: "av"})
    await hass.async_block_till_done()
    assert dict(entry.data) == foer
    assert entry.runtime_data.valgt_maal_kw is None


async def test_proaktivt_maal_er_synlig_uten_fiktive_sparekroner(hass, maalere, freezer):
    now = datetime(2026, 10, 1, 12, 0, tzinfo=ZoneInfo("Europe/Oslo"))
    freezer.move_to(now)
    for state in hass.states.async_all():
        hass.states.async_set(state.entity_id, state.state, state.attributes)
    hass.states.async_set(POWER_SENSOR, "6000", {"unit_of_measurement": "W", "device_class": "power"})
    entry = lag_entry(valgt_maal_kw=5.0)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    data = entry.runtime_data.data
    assert data["maal_status"] == "aktiv"
    assert data["maal_kutt_anbefalt"]
    assert not data["timen_flytter_trinnet"]
    assert data["unngaaelig_besparelse_kr"] == 0
    s = hass.states.get("sensor.effektvakt_projisert_time_snitt")
    assert s.attributes["valgt_maal_kw"] == 5.0
    assert s.attributes["maal_status"] == "aktiv"
    hass.states.async_set(POWER_SENSOR, "unavailable", {"unit_of_measurement": "W"})
    await entry.runtime_data.async_request_refresh()
    assert entry.runtime_data.data["maal_status"] is None
    assert entry.runtime_data.data["maal_kutt_anbefalt"] is None
