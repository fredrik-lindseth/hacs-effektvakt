"""Diagnostics support for Effektvakt."""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from .lastvern import DATA_LASTVERN, Lastvern

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Returner diagnose-info for support-issues."""
    coordinator = entry.runtime_data
    vern = hass.data.get(DATA_LASTVERN)
    return {
        "config": dict(entry.data),
        "lastvern": {
            "aktive_kutt": {entity_id: asdict(kutt) for entity_id, kutt in vern.kutt.items()},
            "tidligst_kutt": dict(vern.tidligst_kutt),
        }
        if isinstance(vern, Lastvern)
        else {},
        "coordinator": {
            "data": coordinator.data,
            "daily_max_kw_count": len(coordinator._regnskap.daily_max_kw),
            "previous_month_top_3_snitt_kw": coordinator._regnskap.previous_month_top_3_snitt_kw,
            "hysterese_state": {
                "nivå": coordinator._hysterese_state.nivå,
                "pending_nivå": coordinator._hysterese_state.pending_nivå,
            },
            "kapasitetstrinn": coordinator.kapasitetstrinn,
            "fastledd_metode": coordinator.trinn_oppsett.fastledd_metode,
            "metode_ikke_stoettet": coordinator.trinn_oppsett.metode_ikke_stoettet,
        },
    }
