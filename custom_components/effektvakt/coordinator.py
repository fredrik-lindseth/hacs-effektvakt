"""Coordinator for Effektvakt."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from .const import (
    MAX_POWER_CLAMP_W,
    VALID_ENERGY_UNITS,
    VALID_POWER_UNITS,
)

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
