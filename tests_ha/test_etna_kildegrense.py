"""Ekte HA publiserer ikke operative råd utenfor Etna-tariffens kildeomfang."""

from datetime import date

import pytest
from homeassistant.const import STATE_UNKNOWN
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.effektvakt.const import DOMAIN, ENTRY_VERSION


@pytest.mark.parametrize("dso,gyldig_w,ukjent_w", [("etna_nett", 75000, 78000), ("nettselskapet", 74999, 75000)])
async def test_risiko_og_kutt_er_unknown_utenfor_kilden(hass, freezer, dso, gyldig_w, ukjent_w):
    freezer.move_to("2026-10-09T14:00:00+00:00")
    hass.states.async_set("sensor.etna_power", str(gyldig_w), {"unit_of_measurement": "W"})
    entry = MockConfigEntry(
        domain=DOMAIN, version=ENTRY_VERSION, data={"dso": dso, "power_sensor": "sensor.etna_power"}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    if dso == "nettselskapet":
        coordinator._regnskap.daily_max_kw = {date(2026, 10, 1): 75, date(2026, 10, 2): 75}
    for power, ukjent in [(gyldig_w, False), (ukjent_w, True), (gyldig_w, False)]:
        hass.states.async_set("sensor.etna_power", str(power), {"unit_of_measurement": "W"})
        coordinator.async_set_updated_data(await coordinator._async_update_data())
        await hass.async_block_till_done()
        assert coordinator.data["beregning_gyldig"] is not ukjent
        for entity_id in (
            "sensor.effektvakt_risiko_niva",
            "binary_sensor.effektvakt_kutt_ned_anbefalt",
            "sensor.effektvakt_kostnad_neste_trinn",
        ):
            state = hass.states.get(entity_id)
            assert state is not None
            assert (state.state == STATE_UNKNOWN) is ukjent
