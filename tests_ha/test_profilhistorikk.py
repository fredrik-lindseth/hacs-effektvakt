"""Recorder-innlesing med ekte HA, ikke kopierte historikksvar."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.components.recorder.common import async_wait_recording_done

from custom_components.effektvakt.profilhistorikk import Profilhistorikk


@pytest.fixture
def mock_recorder_before_hass(recorder_db_url):
    """Forbered databasemiljoet foer HA-fixturen opprettes."""


async def _tilstand(hass, freezer, tid, verdi, enhet="W"):
    freezer.move_to(tid)
    hass.states.async_set("sensor.testlast", verdi, {"unit_of_measurement": enhet})
    await hass.async_block_till_done()
    await async_wait_recording_done(hass)


@pytest.mark.usefixtures("recorder_mock")
async def test_recorder_enheter_hull_og_egne_kutt(hass: HomeAssistant, freezer):
    start = datetime.now(UTC) + timedelta(minutes=1)
    await _tilstand(hass, freezer, start, "0")
    await _tilstand(hass, freezer, start + timedelta(minutes=10), "2", "kW")
    await _tilstand(hass, freezer, start + timedelta(minutes=40), "unavailable")
    await _tilstand(hass, freezer, start + timedelta(minutes=50), "0")
    slutt = start + timedelta(hours=1)
    freezer.move_to(slutt)
    adapter = Profilhistorikk(hass)
    await adapter.async_oppdater({"sensor.testlast": 100, "sensor.finnes_ikke": 100}, naa=slutt)
    profil = adapter.profiler["sensor.testlast"]
    assert adapter.status == "klar"
    assert adapter.oppdatert == slutt
    assert profil.tidsgrunnlag.kjent_s == pytest.approx(3000)
    assert profil.tidsgrunnlag.aktiv_andel == pytest.approx(0.6)
    assert profil.tidsgrunnlag.aktiv_wh == pytest.approx(1000)
    assert profil.aktive_perioder[0].hoyre_sensurert
    assert adapter.profiler["sensor.finnes_ikke"].tidsgrunnlag.kjent_s == 0

    adapter.noter_kutt("sensor.testlast", start + timedelta(minutes=20), start + timedelta(minutes=30))
    maskert = adapter.profiler["sensor.testlast"]
    assert maskert.tidsgrunnlag.kjent_s == pytest.approx(2400)
    assert maskert.tidsgrunnlag.aktiv_wh == pytest.approx(2000 / 3)
    assert not maskert.hele_varigheter_s
    # Etter oppdatering skal masken fortsatt gjelde; den er ikke bare attrs.
    await adapter.async_oppdater({"sensor.testlast": 100}, naa=slutt)
    assert adapter.profiler["sensor.testlast"].tidsgrunnlag.aktiv_wh == pytest.approx(2000 / 3)


@pytest.mark.usefixtures("recorder_mock")
async def test_recorder_tar_med_starttilstand(hass: HomeAssistant, freezer):
    start = datetime.now(UTC) + timedelta(minutes=1)
    await _tilstand(hass, freezer, start, "1000")
    slutt = start + timedelta(days=7, minutes=30)
    freezer.move_to(slutt)
    adapter = Profilhistorikk(hass)
    await adapter.async_oppdater({"sensor.testlast": 100}, naa=slutt)
    profil = adapter.profiler["sensor.testlast"]
    assert profil.tidsgrunnlag.dekning == pytest.approx(1)
    assert profil.tidsgrunnlag.aktiv_andel == pytest.approx(1)
    assert profil.aktive_perioder[0].venstre_sensurert
    assert profil.aktive_perioder[0].hoyre_sensurert
    assert not profil.hele_varigheter_s


async def test_uten_recorder_er_profil_ukjent(hass: HomeAssistant):
    adapter = Profilhistorikk(hass)
    await adapter.async_oppdater({"sensor.testlast": 100})
    assert adapter.status == "recorder_mangler"
    assert not adapter.profiler
    assert adapter.oppdatert is None
    await adapter.async_oppdater({})
    assert adapter.status == "ingen_sensorer"


async def test_avviser_tid_uten_tidssone(hass: HomeAssistant):
    adapter = Profilhistorikk(hass)
    with pytest.raises(ValueError, match="tidssone"):
        await adapter.async_oppdater({"sensor.testlast": 100}, naa=datetime(2026, 10, 1))


@pytest.mark.usefixtures("recorder_mock")
async def test_feilet_historikk_beholder_siste_snapshot(hass: HomeAssistant, freezer):
    start = datetime.now(UTC) + timedelta(minutes=1)
    await _tilstand(hass, freezer, start, "1000")
    slutt = start + timedelta(minutes=30)
    freezer.move_to(slutt)
    adapter = Profilhistorikk(hass)
    await adapter.async_oppdater({"sensor.testlast": 100}, naa=slutt)
    profil = adapter.profiler["sensor.testlast"]
    with patch("homeassistant.components.recorder.history.get_significant_states", side_effect=RuntimeError("lukket")):
        await adapter.async_oppdater({"sensor.testlast": 100}, naa=slutt + timedelta(hours=1))
    assert adapter.status == "historikk_feilet"
    assert adapter.oppdatert == slutt
    assert adapter.profiler["sensor.testlast"] is profil
    # Unload skal kunne avbryte, ikke bli til et vanlig historikkproblem.
    with (
        patch("homeassistant.components.recorder.history.get_significant_states", side_effect=asyncio.CancelledError),
        pytest.raises(asyncio.CancelledError),
    ):
        await adapter.async_oppdater({"sensor.testlast": 100}, naa=slutt)
