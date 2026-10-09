"""Målefriskhet og ukjente råd gjennom HAs ekte State.last_reported."""

from datetime import timedelta

from homeassistant.const import STATE_UNKNOWN

from .conftest import BINARY_SENSOR_ID, POWER_SENSOR


async def test_unavailable_blir_unknown_raad_mens_coordinatoren_fortsetter(hass, oppsett):
    coordinator = oppsett.runtime_data
    kjent_energi = coordinator.data["actual_kwh_this_hour"]
    hass.states.async_set(POWER_SENSOR, "unavailable", {"unit_of_measurement": "W"})
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    for entity_id in (
        "sensor.effektvakt_projisert_time_snitt",
        "sensor.effektvakt_margin_til_neste_trinn",
        "sensor.effektvakt_risiko_niva",
        BINARY_SENSOR_ID,
    ):
        state = hass.states.get(entity_id)
        assert state.state == STATE_UNKNOWN
        assert state.attributes["maalegrunnlag_gyldig"] is False
    assert coordinator.data["actual_kwh_this_hour"] == kjent_energi
    assert coordinator.data["kan_legge_paa_resten_av_timen_kw"] is None
    assert hass.states.get("sensor.effektvakt_topp_3_snitt_denne_maned").state != STATE_UNKNOWN


async def test_uendret_state_med_ny_rapport_er_fersk(hass, freezer, oppsett):
    coordinator = oppsett.runtime_data
    foer = hass.states.get(POWER_SENSOR)
    rapport_foer = foer.last_reported
    freezer.tick(timedelta(seconds=121))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.effektvakt_projisert_time_snitt").state == STATE_UNKNOWN
    assert coordinator.data["maalegrunnlag_gyldig"] is False

    hass.states.async_set(POWER_SENSOR, foer.state, foer.attributes)
    etter = hass.states.get(POWER_SENSOR)
    assert etter.last_changed == foer.last_changed
    assert etter.last_reported > rapport_foer
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.data["maalegrunnlag_gyldig"] is True
    assert hass.states.get("sensor.effektvakt_projisert_time_snitt").state != STATE_UNKNOWN
