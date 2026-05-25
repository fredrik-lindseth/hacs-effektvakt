"""Effektvakt integration for Home Assistant."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN, WATCHDOG_INTERVAL_SECONDS
from .coordinator import EffektvaktCoordinator, dt_util_now, is_coordinator_stale

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Sett opp Effektvakt fra en config entry."""
    coordinator = EffektvaktCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    async def _watchdog_check(_now) -> None:
        if is_coordinator_stale(
            last_successful_update=coordinator._last_successful_update,
            now=dt_util_now(),
        ):
            _LOGGER.warning(
                "Effektvakt coordinator stale, setter sensorer til unknown"
            )
            coordinator.async_set_updated_data({})

    entry.async_on_unload(
        async_track_time_interval(
            hass, _watchdog_check, timedelta(seconds=WATCHDOG_INTERVAL_SECONDS)
        )
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
