"""Tester for __init__.py setup/unload."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.effektvakt import async_setup_entry, async_unload_entry
from tests.conftest import make_entry


@pytest.mark.asyncio
async def test_async_setup_entry_oppretter_coordinator():
    entry = make_entry()
    hass = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.services.async_register = MagicMock()

    with (
        patch("custom_components.effektvakt.EffektvaktCoordinator") as MockCoord,
        patch("custom_components.effektvakt.async_track_time_interval"),
    ):
        MockCoord.return_value.async_config_entry_first_refresh = AsyncMock()
        MockCoord.return_value._last_successful_update = None
        ok = await async_setup_entry(hass, entry)
    assert ok is True
    MockCoord.assert_called_once_with(hass, entry)


@pytest.mark.asyncio
async def test_async_unload_entry():
    entry = make_entry()
    entry.runtime_data = MagicMock()
    hass = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    ok = await async_unload_entry(hass, entry)
    assert ok is True
