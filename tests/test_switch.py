"""Tester for switch.py, hovedbryteren for automatikken."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.effektvakt.binary_sensor import EffektvaktKuttNedAnbefaltBinarySensor
from custom_components.effektvakt.const import (
    RISIKO_LIKE_UNDER,
    RISIKO_OVER_TERSKEL,
    SWITCH_KEY_AUTOMATIKK,
)
from custom_components.effektvakt.switch import EffektvaktAutomatikkSwitch


async def _ferdig(verdi):
    """Liten awaitable som står inn for async_get_last_state."""
    return verdi


def make_coordinator():
    """Coordinator-mock med det bryteren faktisk rører."""
    coord = MagicMock()
    coord.entry.entry_id = "test_entry"
    coord.automatikk_aktiv = True
    return coord


def make_switch(coordinator=None) -> EffektvaktAutomatikkSwitch:
    return EffektvaktAutomatikkSwitch(coordinator or make_coordinator())


def make_last_state(state: str):
    forrige = MagicMock()
    forrige.state = state
    return forrige


def test_bryteren_er_paa_uten_lagret_tilstand():
    """Nyoppsett skal starte med vakten på."""
    assert make_switch().is_on is True


def test_unique_id_henger_paa_config_entry():
    sw = make_switch()
    assert sw._attr_unique_id == "test_entry_automatikk"


def test_bryteren_er_oversettbar_og_beholder_id_en():
    """Navnet kommer fra oversettelsen, id-en er den docs og blueprintene navngir."""
    sw = make_switch()
    assert sw._attr_translation_key == SWITCH_KEY_AUTOMATIKK
    assert not hasattr(sw, "_attr_name")
    assert sw.entity_id == "switch.effektvakt_automatikk"


@pytest.mark.parametrize(
    "lagret,forventet",
    [
        ("off", False),
        ("on", True),
        # unavailable og unknown er tapt historikk, ikke et valg brukeren tok.
        ("unavailable", True),
        ("unknown", True),
    ],
)
async def test_tilstanden_overlever_omstart(lagret: str, forventet: bool):
    sw = make_switch()
    sw.async_get_last_state = lambda: _ferdig(make_last_state(lagret))
    await sw.async_added_to_hass()
    assert sw.is_on is forventet
    assert sw.coordinator.automatikk_aktiv is forventet


async def test_uten_lagret_tilstand_havner_den_paa():
    sw = make_switch()
    sw.async_get_last_state = lambda: _ferdig(None)
    await sw.async_added_to_hass()
    assert sw.is_on is True


async def test_bryteren_dytter_binary_sensoren_med_en_gang():
    """Ellers henger attributtet etter til neste coordinator-tikk."""
    coord = make_coordinator()
    sw = make_switch(coord)

    await sw.async_turn_off()
    coord.async_update_listeners.assert_called_once()


async def test_restore_vekker_ikke_lytterne():
    """Under oppstart er de andre entitetene ikke lagt til enda."""
    coord = make_coordinator()
    sw = make_switch(coord)
    sw.async_get_last_state = lambda: _ferdig(make_last_state("off"))

    await sw.async_added_to_hass()
    coord.async_update_listeners.assert_not_called()


async def test_turn_off_og_turn_on_folger_med_paa_coordinatoren():
    coord = make_coordinator()
    sw = make_switch(coord)

    await sw.async_turn_off()
    assert sw.is_on is False
    assert coord.automatikk_aktiv is False

    await sw.async_turn_on()
    assert sw.is_on is True
    assert coord.automatikk_aktiv is True


def test_binary_sensor_folger_ikke_bryteren():
    """Anbefalingen skal stå selv om ingen kommer til å handle på den."""
    coord = MagicMock()
    coord.entry.entry_id = "test_entry"
    coord.min_risiko_for_kutt = RISIKO_LIKE_UNDER
    coord.data = {"risiko_niva": RISIKO_OVER_TERSKEL}
    coord.automatikk_aktiv = False

    bs = EffektvaktKuttNedAnbefaltBinarySensor(coord)
    assert bs.is_on is True
    assert bs.extra_state_attributes == {"automatikk_aktiv": False}


def test_binary_sensor_eksponerer_bryteren_som_attributt():
    coord = MagicMock()
    coord.entry.entry_id = "test_entry"
    coord.min_risiko_for_kutt = RISIKO_LIKE_UNDER
    coord.data = None
    coord.automatikk_aktiv = True

    bs = EffektvaktKuttNedAnbefaltBinarySensor(coord)
    assert bs.extra_state_attributes == {"automatikk_aktiv": True}
