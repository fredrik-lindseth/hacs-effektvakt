"""Watchdog-kontrakten, med HA sine egne timere.

``tests/`` tester ``is_coordinator_stale`` som funksjon, og den funksjonen har
aldri vaert feilen. Det som kan ryke er ledningen rundt den: at
``async_track_time_interval`` faktisk er koblet paa i ``async_setup_entry``,
at intervallet er kort nok til at terskelen naas, at ``async_set_updated_data({})``
gir ``unknown`` og ikke ``unavailable``, og at timeren tas ned igjen med
entryen. Alt det krever en ekte HA.

Automasjonene og blueprintene bygger paa at ``unknown`` betyr «vet ikke». En
sensor som blir staaende med det siste tallet den rakk aa regne ut, ser
nemlig ut som «alt er fint».
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING
from unittest.mock import patch

from homeassistant.const import STATE_UNKNOWN
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.effektvakt.const import (
    WATCHDOG_INTERVAL_SECONDS,
    WATCHDOG_STALE_THRESHOLD_SECONDS,
)
from custom_components.effektvakt.coordinator import EffektvaktCoordinator

from .conftest import SENSOR_IDS

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

# Sensorene som faktisk regner. Enum-sensoren er med: «vet ikke» er ikke et
# risikonivaa, og et dashbord som viser «God margin» mens ingenting maales er
# verre enn et tomt felt.
TALLSENSORER = SENSOR_IDS


async def _tikk(hass: HomeAssistant, freezer, sekunder: int) -> None:
    """Flytt klokken framover i steg og la timerne kjoere underveis.

    Ett stort hopp ville latt alle timerne forfalle i samme runde, og da
    avgjoer rekkefoelgen HA tilfeldigvis velger hva testen ser.
    """
    steg = WATCHDOG_INTERVAL_SECONDS // 2
    for _ in range(sekunder // steg):
        freezer.tick(timedelta(seconds=steg))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()


async def _staar_stille(self: EffektvaktCoordinator) -> dict:
    """En coordinator som svarer, men ikke kommer noen vei.

    Den returnerer forrige runde om igjen og roerer ikke
    ``_last_successful_update``. Det er nettopp tilfellet watchdogen finnes
    for: ingen feil noen ser, bare tall som slutter aa vaere sanne.
    """
    return dict(self.data or {})


async def test_sensorene_gaar_til_unknown_naar_coordinatoren_staar_stille(
    hass: HomeAssistant, freezer, oppsett: MockConfigEntry
) -> None:
    for entity_id in TALLSENSORER:
        assert hass.states.get(entity_id).state != STATE_UNKNOWN, entity_id

    with patch.object(EffektvaktCoordinator, "_async_update_data", _staar_stille):
        await _tikk(hass, freezer, WATCHDOG_STALE_THRESHOLD_SECONDS + 2 * WATCHDOG_INTERVAL_SECONDS)

        for entity_id in TALLSENSORER:
            assert hass.states.get(entity_id).state == STATE_UNKNOWN, entity_id


async def test_watchdogen_slaar_ikke_til_paa_en_frisk_coordinator(
    hass: HomeAssistant, freezer, oppsett: MockConfigEntry
) -> None:
    """Fem minutter i normal drift skal ikke gi et eneste «vet ikke»."""
    await _tikk(hass, freezer, 300)

    for entity_id in TALLSENSORER:
        assert hass.states.get(entity_id).state != STATE_UNKNOWN, entity_id


async def test_sensorene_kommer_tilbake_naar_coordinatoren_svarer_igjen(
    hass: HomeAssistant, freezer, oppsett: MockConfigEntry
) -> None:
    """Watchdogen er en pause, ikke en enveisbillett."""
    with patch.object(EffektvaktCoordinator, "_async_update_data", _staar_stille):
        await _tikk(hass, freezer, WATCHDOG_STALE_THRESHOLD_SECONDS + 2 * WATCHDOG_INTERVAL_SECONDS)
    assert hass.states.get("sensor.effektvakt_projisert_time_snitt").state == STATE_UNKNOWN

    # Neste vellykkede runde, uten aa vente paa tick-intervallet: poenget er
    # at watchdogen ikke har satt noe i en tilstand den ikke kommer ut av.
    await oppsett.runtime_data.async_refresh()
    await hass.async_block_till_done()

    for entity_id in TALLSENSORER:
        assert hass.states.get(entity_id).state != STATE_UNKNOWN, entity_id


async def test_watchdogen_tas_ned_sammen_med_entryen(hass: HomeAssistant, freezer, oppsett: MockConfigEntry) -> None:
    """Timeren henger paa ``entry.async_on_unload``, saa den skal ikke overleve.

    En timer som blir staaende igjen holder paa coordinatoren og logger
    advarsler om et oppsett brukeren har fjernet.
    """
    assert await hass.config_entries.async_unload(oppsett.entry_id)
    await hass.async_block_till_done()

    with patch.object(EffektvaktCoordinator, "async_set_updated_data", autospec=True) as sett_data:
        await _tikk(hass, freezer, WATCHDOG_STALE_THRESHOLD_SECONDS + 2 * WATCHDOG_INTERVAL_SECONDS)

    sett_data.assert_not_called()
