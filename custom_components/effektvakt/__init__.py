"""Effektvakt integration for Home Assistant."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN, WATCHDOG_INTERVAL_SECONDS
from .coordinator import EffektvaktCoordinator, dt_util_now, is_coordinator_stale
from .frontend import async_register_frontend, async_unregister_frontend

if TYPE_CHECKING:
    from datetime import datetime

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant, ServiceCall
    from homeassistant.helpers.typing import ConfigType

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH]

SERVICE_SET_SAFETY_BUFFER = "set_safety_buffer"
SERVICE_RESET_TOPP_3 = "reset_topp_3"
SERVICES: tuple[str, ...] = (SERVICE_SET_SAFETY_BUFFER, SERVICE_RESET_TOPP_3)

# Effektvakt settes bare opp gjennom config entries, ingen YAML. Uten denne
# sier hassfest fra om at en integrasjon med async_setup maa ha et skjema.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, _config: ConfigType) -> bool:
    """Sett opp det som hoerer til HA-oppstarten, ikke til en enkelt entry.

    Kortet serveres og meldes inn i Lovelace her, saa det ligger paa plass
    ogsaa naar HA starter uten at noen entry er satt opp enda.
    """
    await async_register_frontend(hass)
    return True


def _loaded_coordinators(hass: HomeAssistant) -> list[EffektvaktCoordinator]:
    """Alle coordinators som er lastet akkurat naa, paa tvers av entries."""
    coordinators = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        coordinator = getattr(entry, "runtime_data", None)
        if coordinator is not None:
            coordinators.append(coordinator)
    return coordinators


def _async_register_services(hass: HomeAssistant) -> None:
    """Registrer tjenestene en gang, ikke en gang per entry.

    Tjenestene er domenetjenester uten maal, saa to oppsett ville ellers
    registrert hver sin handler og latt det siste overstyre det foerste. De
    virker derfor paa alle lastede entries.
    """

    async def _set_safety_buffer(call: ServiceCall) -> None:
        kw = float(call.data["kw"])
        for coordinator in _loaded_coordinators(hass):
            coordinator.safety_buffer_kw = kw
            await coordinator.async_request_refresh()

    async def _reset_topp_3(_call: ServiceCall) -> None:
        for coordinator in _loaded_coordinators(hass):
            coordinator._daily_max_kw = {}
            await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, SERVICE_SET_SAFETY_BUFFER, _set_safety_buffer)
    hass.services.async_register(DOMAIN, SERVICE_RESET_TOPP_3, _reset_topp_3)


def _async_unregister_services(hass: HomeAssistant) -> None:
    """Fjern tjenestene naar siste entry er lastet ut."""
    for service in SERVICES:
        hass.services.async_remove(DOMAIN, service)


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

    async def _watchdog_check(_now: datetime) -> None:
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

    if not hass.services.has_service(DOMAIN, SERVICE_SET_SAFETY_BUFFER):
        _async_register_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload integration når options endrer seg."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Avregistrer platforms, og tjenestene naar dette var siste entry."""
    unload_ok: bool = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    # Ryddes her fordi _loaded_coordinators teller paa runtime_data: uten
    # dette ville entryen vi nettopp lastet ut fortsatt telle som lastet, og
    # tjenestene ville aldri blitt fjernet.
    entry.runtime_data = None
    if not _loaded_coordinators(hass):
        _async_unregister_services(hass)

    return True


async def async_remove_entry(hass: HomeAssistant, _entry: ConfigEntry) -> None:
    """Ta kortet ut av Lovelace-ressursene naar siste oppsett er fjernet.

    Ressursregisteret er brukerens eget og deles med HACS, saa det vi la inn
    der skal ryddes ut igjen. Har brukeren flere Effektvakt-oppsett, blir
    oppfoeringen staaende til det siste er borte.
    """
    if hass.config_entries.async_entries(DOMAIN):
        return
    await async_unregister_frontend(hass)
