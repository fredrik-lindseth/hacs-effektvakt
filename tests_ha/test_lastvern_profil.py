"""Egne kutt skal ikke bli laert som korte naturlige driftssykluser."""

from datetime import timedelta

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from custom_components.effektvakt.lastvern import DATA_LASTVERN, Lastvern, async_setup_lastvern

from .test_lastvern import LAST, styr
from .test_lastvern import vern as vern


async def _restart(hass, gammel):
    gammel._stopp()
    del hass.data[DATA_LASTVERN]
    await async_setup_lastvern(hass)
    return hass.data[DATA_LASTVERN]


async def test_kuttprofil_overlever_restart_og_bekreftet_restore(hass, freezer, vern):
    start = dt_util.utcnow()
    await styr(hass)
    freezer.tick(timedelta(minutes=3))
    assert vern.profilvinduer(LAST, dt_util.utcnow()) == [(start, dt_util.utcnow())]
    ny = await _restart(hass, vern)
    assert not ny.kutt
    assert hass.states.is_state(LAST, "on")
    assert ny.profilvinduer(LAST, dt_util.utcnow()) == [(start, dt_util.utcnow())]
    # Historikken bestaar ogsaa gjennom enda en restart uten aktive kutt.
    tredje = await _restart(hass, ny)
    assert tredje.profilvinduer(LAST, dt_util.utcnow()) == [(start, dt_util.utcnow())]


async def test_feilet_restore_holder_masken_aapen(hass, freezer, vern):
    start = dt_util.utcnow()
    await styr(hass)

    async def feilet(_call):
        raise HomeAssistantError("ikke kontakt")

    hass.services.async_register("switch", "turn_on", feilet)
    freezer.tick(timedelta(minutes=3))
    ny = await _restart(hass, vern)
    assert LAST in ny.kutt
    assert ny.profilvinduer(LAST, dt_util.utcnow()) == [(start, dt_util.utcnow())]
    freezer.tick(timedelta(minutes=10))
    assert ny.profilvinduer(LAST, dt_util.utcnow()) == [(start, dt_util.utcnow())]
    hass.states.async_set(LAST, "on")
    await ny.async_sjekk()
    assert not ny.kutt
    assert ny.profilvinduer(LAST, dt_util.utcnow()) == [(start, dt_util.utcnow())]


async def test_feilet_opprinnelig_kutt_maskeres_konservativt(hass, freezer, vern):
    start = dt_util.utcnow()

    async def feilet(_call):
        raise HomeAssistantError("utfallet er ukjent")

    hass.services.async_register("switch", "turn_off", feilet)
    with pytest.raises(HomeAssistantError):
        await styr(hass)
    assert vern.kutt[LAST].slipp
    freezer.tick(timedelta(minutes=1))
    assert vern.profilvinduer(LAST, dt_util.utcnow()) == [(start, dt_util.utcnow())]
    await vern.async_sjekk()
    assert not vern.kutt
    assert vern.profilvinduer(LAST, dt_util.utcnow()) == [(start, dt_util.utcnow())]


async def test_gammelt_ansvar_uten_start_utelater_hele_vinduet(hass, freezer, vern):
    naa = dt_util.utcnow()
    await vern.store.async_save(
        {"kutt": {LAST: {"eier": "automation.vern", "frist": naa.timestamp() + 600, "min_paatid": 300}}}
    )
    hass.states.async_set(LAST, "unavailable")
    ny = await _restart(hass, vern)
    assert ny.kutt[LAST].start is None
    assert ny.profilvinduer(LAST, naa) == [(naa - timedelta(days=7), naa)]
    freezer.tick(timedelta(minutes=1))
    hass.states.async_set(LAST, "on")
    await ny.async_sjekk()
    assert not ny.kutt
    assert ny.profilvinduer(LAST, dt_util.utcnow()) == [(dt_util.utcnow() - timedelta(days=7), dt_util.utcnow())]


async def test_historikk_prunes_til_syvdager_og_ugyldige_rader_ignoreres(hass, vern):
    naa = dt_util.utcnow()
    tid = naa.timestamp()
    await vern.store.async_save(
        {
            "profilkutt": {
                LAST: [[tid - 9 * 86400, tid - 8 * 86400], [tid - 8 * 86400, tid - 6 * 86400], [tid - 60, tid]],
                "switch.ugyldig": [["x", tid], [tid, tid - 1], [True, tid], [float("inf"), tid]],
            }
        }
    )
    ny = await _restart(hass, vern)
    assert ny.profilvinduer(LAST, naa) == [
        (naa - timedelta(days=7), naa - timedelta(days=6)),
        (naa - timedelta(minutes=1), naa),
    ]
    assert ny.profilvinduer("switch.ugyldig", naa) == []
    await ny._lagre()
    lagret = await ny.store.async_load()
    assert len(lagret["profilkutt"][LAST]) == 2


async def test_tidssone_paa_profilvinduer_er_paakrevd(hass):
    vern = Lastvern(hass)
    with pytest.raises(ValueError, match="tidssone"):
        vern.profilvinduer(LAST, dt_util.utcnow().replace(tzinfo=None))
