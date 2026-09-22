"""Avlesning av Home Assistant-entiteter, normalisert til enhetene vi regner i.

Ansvar i en setning: les en HA-entitet og gi den som kW, kWh, navn,
bryterstilling eller tidsstempel, eller None hvis den ikke svarer.

Dette er de eneste funksjonene i pakken som rører `hass.states`, og de ligger
samlet nettopp derfor: da er HA-flaten synlig på ett sted, og resten av koden
slipper å lure på hvor den går. None betyr «vet ikke» hele veien gjennom, og
skal aldri erstattes av en null noen kan regne videre på.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime
from typing import TYPE_CHECKING

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.util import dt as dt_util_module

from .const import MAX_POWER_CLAMP_W, VALID_ENERGY_UNITS, VALID_POWER_UNITS

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def read_power_kw(hass: HomeAssistant, entity_id: str | None) -> float | None:
    """Les power-sensor og returner verdi normalisert til kW.

    Returnerer None hvis sensor ikke finnes, er unavailable, har ugyldig
    unit, eller verdien er ikke-finit/over MAX_POWER_CLAMP_W.
    """
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in ("unknown", "unavailable", None):
        return None
    try:
        value = float(state.state)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(value):
        return None
    unit = (state.attributes or {}).get("unit_of_measurement")
    if unit not in VALID_POWER_UNITS:
        return None
    if unit == "W":
        if value > MAX_POWER_CLAMP_W:
            _LOGGER.warning("power_sensor %s = %s W > clamp %s", entity_id, value, MAX_POWER_CLAMP_W)
            return None
        return value / 1000
    return value  # kW


def read_friendly_name(hass: HomeAssistant, entity_id: str) -> str | None:
    """HA sitt friendly_name for en entitet, None hvis den ikke finnes ennå."""
    state = hass.states.get(entity_id)
    if state is None:
        return None
    navn = (state.attributes or {}).get("friendly_name")
    return navn if isinstance(navn, str) else None


def read_switch_on(hass: HomeAssistant, entity_id: str | None) -> bool | None:
    """Om en bryter staar paa. None naar den ikke finnes eller ikke svarer.

    Skillet mellom None og False betyr noe her: «bryteren er av» og «vi vet
    ikke hvor bryteren staar» gir ulike svar paa om lasten nettopp ble kuttet.
    Gjettet ville blitt til et kutt i hendelsesloggen som aldri fant sted.

    Alt annet enn on og off er «vet ikke», ogsaa unavailable og unknown.
    """
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None:
        return None
    if state.state == STATE_ON:
        return True
    if state.state == STATE_OFF:
        return False
    return None


def read_energy_kwh(hass: HomeAssistant, entity_id: str | None) -> float | None:
    """Les energy-sensor og returner verdi normalisert til kWh.

    Returnerer None hvis sensor ikke finnes, er unavailable, eller har ugyldig
    unit.
    """
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in ("unknown", "unavailable", None):
        return None
    try:
        value = float(state.state)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    unit = (state.attributes or {}).get("unit_of_measurement")
    if unit not in VALID_ENERGY_UNITS:
        return None
    if unit == "Wh":
        return value / 1000
    return value  # kWh


def read_state_timestamp(hass: HomeAssistant, entity_id: str | None, *, now: datetime) -> datetime | None:
    """Når entiteten sist meldte en ny verdi, i samme tidsform som `now`.

    Tidspunktet er viktigere enn det ser ut: en AMS-måler som rapporterer
    10:00:13 leverer kWh-en som hører til timen før, og ticket som leser den
    kommer gjerne et halvt minutt senere. Bruker vi tidspunktet for ticket i
    stedet, havner hele timen på feil side av timeskiftet.

    Returnerer None hvis tidsstempelet mangler, ikke lar seg gjøre om til lokal
    tid, eller ender opp med en annen tidssone-form enn `now`. Da faller
    kalleren tilbake på tidspunktet for ticket.
    """
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None:
        return None
    rå = getattr(state, "last_changed", None)
    if not isinstance(rå, datetime):
        return None
    lokal = dt_util_module.as_local(rå)
    if not isinstance(lokal, datetime):
        return None
    if (lokal.tzinfo is None) != (now.tzinfo is None):
        return None
    return lokal
