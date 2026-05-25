"""Diagnostics support for Effektvakt."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Returner diagnose-info for support-issues."""
    coordinator = entry.runtime_data
    return {
        "config": dict(entry.data),
        "coordinator": {
            "data": coordinator.data,
            "daily_max_kw_count": len(coordinator._daily_max_kw),
            "previous_month_top_3_snitt_kw": coordinator._previous_month_top_3_snitt_kw,
            "hysterese_state": {
                "nivå": coordinator._hysterese_state.nivå,
                "pending_nivå": coordinator._hysterese_state.pending_nivå,
            },
            "kapasitetstrinn": coordinator.kapasitetstrinn,
        },
    }
