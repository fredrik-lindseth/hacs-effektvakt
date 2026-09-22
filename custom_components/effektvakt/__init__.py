"""Effektvakt integration for Home Assistant."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN, WATCHDOG_INTERVAL_SECONDS
from .coordinator import EffektvaktCoordinator, dt_util_now, is_coordinator_stale
from .frontend import async_register_frontend, async_unregister_frontend

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.typing import ConfigType

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH]


async def async_setup(hass: HomeAssistant, _config: ConfigType) -> bool:
    """Sett opp det som hoerer til HA-oppstarten, ikke til en enkelt entry.

    Kortet serveres og meldes inn i Lovelace her, saa det ligger paa plass
    ogsaa naar HA starter uten at noen entry er satt opp enda.
    """
    await async_register_frontend(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Sett opp Effektvakt fra en config entry."""
    # Kallet er idempotent og skriver ingenting naar ressursen alt staar
    # riktig. Det maa likevel med: fjerner man oppsettet og legger det inn
    # igjen uten aa starte HA paa nytt, kjoerer async_setup aldri mer, og uten
    # dette ville kortet blitt staaende uten ressursoppfoering.
    await async_register_frontend(hass)

    coordinator = EffektvaktCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    async def _watchdog_check(_now) -> None:
        if is_coordinator_stale(
            last_successful_update=coordinator._last_successful_update,
            now=dt_util_now(),
        ):
            _LOGGER.warning("Effektvakt coordinator stale, setter sensorer til unknown")
            coordinator.async_set_updated_data({})

    entry.async_on_unload(
        async_track_time_interval(hass, _watchdog_check, timedelta(seconds=WATCHDOG_INTERVAL_SECONDS))
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _set_safety_buffer(call) -> None:
        kw = float(call.data["kw"])
        coordinator.safety_buffer_kw = kw
        await coordinator.async_request_refresh()

    async def _reset_topp_3(call) -> None:
        coordinator._daily_max_kw = {}
        await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, "set_safety_buffer", _set_safety_buffer)
    hass.services.async_register(DOMAIN, "reset_topp_3", _reset_topp_3)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload integration når options endrer seg."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Avregistrer platforms."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, _entry: ConfigEntry) -> None:
    """Ta kortet ut av Lovelace-ressursene naar siste oppsett er fjernet.

    Ressursregisteret er brukerens eget og deles med HACS, saa det vi la inn
    der skal ryddes ut igjen. Har brukeren flere Effektvakt-oppsett, blir
    oppfoeringen staaende til det siste er borte.
    """
    if hass.config_entries.async_entries(DOMAIN):
        return
    await async_unregister_frontend(hass)
