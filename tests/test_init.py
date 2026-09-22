"""Tester for __init__.py setup/unload."""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.effektvakt import (
    SERVICE_RESET_TOPP_3,
    SERVICE_SET_SAFETY_BUFFER,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.effektvakt.oppsett import les_trinn
from tests.conftest import make_entry


class _FakeCoordinator:
    """Nok coordinator til at __init__.py kan settes opp og tjenestene kalles."""

    def __init__(self) -> None:
        # Et oppsett uten problemer aa melde. Repair-meldingene har egne tester
        # i test_oppsett.py.
        self.trinn_oppsett = les_trinn(dso_id="bkk", custom=None)
        self.safety_buffer_kw = 1.0
        self._daily_max_kw = {"2026-06-15": 5.0}
        self._last_successful_update = None
        self.refresh_count = 0

    async def async_config_entry_first_refresh(self) -> None:
        pass

    async def async_request_refresh(self) -> None:
        self.refresh_count += 1


def _make_hass(entries: list | None = None):
    """hass-mock med et ekte tjenesteregister, saa vi kan telle registreringer."""
    hass = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

    registered: dict[str, object] = {}
    hass.services.async_register = MagicMock(
        side_effect=lambda _domain, service, handler: registered.__setitem__(service, handler)
    )
    hass.services.async_remove = MagicMock(side_effect=lambda _domain, service: registered.pop(service, None))
    hass.services.has_service = MagicMock(side_effect=lambda _domain, service: service in registered)

    entry_list = list(entries or [])
    hass.config_entries.async_entries = MagicMock(side_effect=lambda _domain: entry_list)
    return hass, registered


def _patches():
    return (
        patch("custom_components.effektvakt.async_track_time_interval"),
        # Kort-registreringen har sine egne tester i test_frontend.py.
        patch("custom_components.effektvakt.async_register_frontend", AsyncMock()),
    )


@pytest.mark.asyncio
async def test_async_setup_entry_oppretter_coordinator():
    entry = make_entry()
    entry.runtime_data = None
    hass, registered = _make_hass([entry])

    track, frontend = _patches()
    with (
        patch("custom_components.effektvakt.EffektvaktCoordinator") as MockCoord,
        track,
        frontend,
    ):
        MockCoord.return_value.async_config_entry_first_refresh = AsyncMock()
        MockCoord.return_value._last_successful_update = None
        ok = await async_setup_entry(hass, entry)

    assert ok is True
    MockCoord.assert_called_once_with(hass, entry)
    assert set(registered) == {SERVICE_SET_SAFETY_BUFFER, SERVICE_RESET_TOPP_3}


@pytest.mark.asyncio
async def test_async_unload_entry():
    entry = make_entry()
    entry.runtime_data = MagicMock()
    hass, _registered = _make_hass([entry])
    ok = await async_unload_entry(hass, entry)
    assert ok is True


@pytest.mark.asyncio
async def test_unload_gir_false_naar_plattformene_nekter():
    entry = make_entry()
    entry.runtime_data = MagicMock()
    hass, registered = _make_hass([entry])
    registered[SERVICE_SET_SAFETY_BUFFER] = object()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)

    assert await async_unload_entry(hass, entry) is False
    # Tjenesten staar igjen: entryen er fortsatt i drift.
    assert SERVICE_SET_SAFETY_BUFFER in registered


async def _sett_opp_to_entries():
    """To oppsett i samme hass, med hver sin coordinator."""
    entry_a = make_entry("entry_a")
    entry_b = make_entry("entry_b", power_sensor="sensor.power_b")
    entry_a.runtime_data = None
    entry_b.runtime_data = None
    hass, registered = _make_hass([entry_a, entry_b])
    coord_a, coord_b = _FakeCoordinator(), _FakeCoordinator()

    track, frontend = _patches()
    lag_coordinator = MagicMock(side_effect=[coord_a, coord_b])
    with (
        patch("custom_components.effektvakt.EffektvaktCoordinator", lag_coordinator),
        track,
        frontend,
    ):
        assert await async_setup_entry(hass, entry_a) is True
        assert await async_setup_entry(hass, entry_b) is True

    return hass, registered, entry_a, entry_b, coord_a, coord_b


@pytest.mark.asyncio
async def test_to_oppsett_registrerer_tjenestene_bare_en_gang():
    hass, registered, entry_a, entry_b, coord_a, coord_b = await _sett_opp_to_entries()

    assert entry_a.runtime_data is coord_a
    assert entry_b.runtime_data is coord_b
    assert set(registered) == {SERVICE_SET_SAFETY_BUFFER, SERVICE_RESET_TOPP_3}
    # To registreringer totalt, ikke to per entry.
    assert hass.services.async_register.call_count == 2


@pytest.mark.asyncio
async def test_tjenestene_virker_paa_alle_oppsett():
    _hass, registered, _entry_a, _entry_b, coord_a, coord_b = await _sett_opp_to_entries()

    call = MagicMock()
    call.data = {"kw": 2.5}
    await registered[SERVICE_SET_SAFETY_BUFFER](call)
    assert coord_a.safety_buffer_kw == 2.5
    assert coord_b.safety_buffer_kw == 2.5

    await registered[SERVICE_RESET_TOPP_3](MagicMock())
    assert coord_a._daily_max_kw == {}
    assert coord_b._daily_max_kw == {}
    assert coord_a.refresh_count == 2
    assert coord_b.refresh_count == 2


@pytest.mark.asyncio
async def test_tjenestene_ryddes_foerst_naar_siste_entry_lastes_ut():
    hass, registered, entry_a, entry_b, _coord_a, _coord_b = await _sett_opp_to_entries()

    assert await async_unload_entry(hass, entry_a) is True
    assert set(registered) == {SERVICE_SET_SAFETY_BUFFER, SERVICE_RESET_TOPP_3}

    assert await async_unload_entry(hass, entry_b) is True
    assert registered == {}
    assert hass.services.async_remove.call_count == 2


def test_config_schema_er_definert_paa_modulnivaa():
    """Samme sjekk som hassfest gjoer: navnet CONFIG_SCHEMA paa modulnivaa."""
    kilde = Path(__file__).parent.parent / "custom_components" / "effektvakt" / "__init__.py"
    tre = ast.parse(kilde.read_text(encoding="utf-8"))
    navn = {
        target.id
        for node in tre.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    assert "CONFIG_SCHEMA" in navn
