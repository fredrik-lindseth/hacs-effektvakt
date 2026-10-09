"""Lastvern og de tre blueprintene i ekte HA, med kontrollerbar klokke."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.setup import async_setup_component
from homeassistant.util import yaml
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.effektvakt.lastvern import DATA_LASTVERN, async_setup_lastvern

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall

ROT = Path(__file__).resolve().parents[1]
LAST = "switch.last"
ROM = "climate.rom"
RISIKO = "binary_sensor.risiko"
BRYTER = "switch.automatikk"
EIER = "automation.vern"


@pytest.fixture
async def vern(hass: HomeAssistant, freezer, hass_storage, tmp_path):
    hass.config.config_dir = str(tmp_path)
    freezer.move_to(datetime(2026, 10, 9, 10, 50, tzinfo=UTC))
    hass.states.async_set(LAST, "on")
    hass.states.async_set("switch.ekstra", "on")
    hass.states.async_set(ROM, "heat", {"temperature": 21})
    hass.states.async_set(BRYTER, "on")
    hass.states.async_set(RISIKO, "off")
    hass.states.async_set("sensor.risiko", "god_margin")

    async def bryter(call: ServiceCall):
        hass.states.async_set(call.data["entity_id"], "off" if call.service == "turn_off" else "on")

    async def temperatur(call: ServiceCall):
        hass.states.async_set(call.data["entity_id"], "heat", {"temperature": call.data["temperature"]})

    hass.services.async_register("switch", "turn_off", bryter)
    hass.services.async_register("switch", "turn_on", bryter)
    hass.services.async_register("climate", "set_temperature", temperatur)
    await async_setup_lastvern(hass)
    yield hass.data[DATA_LASTVERN]
    if hass.services.has_service("automation", "turn_off"):
        await hass.services.async_call("automation", "turn_off", {"entity_id": EIER}, blocking=True)
        await hass.async_block_till_done()


async def styr(hass, kutt=True, **data):
    await hass.services.async_call(
        "effektvakt",
        "styr_last",
        {
            "entity_id": LAST,
            "eier": EIER,
            "kutt": kutt,
            "automatikk_switch": BRYTER,
            **data,
        },
        blocking=True,
    )
    await hass.async_block_till_done()


async def tikk(hass, freezer, sekunder):
    freezer.tick(timedelta(seconds=sekunder))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def blueprint(hass, fil):
    ra = yaml.load_yaml(str(ROT / "docs/blueprints" / fil))
    verdier = {k: v["default"] for k, v in ra["blueprint"]["input"].items() if "default" in v}
    verdier.update(
        {
            "automatikk_switch": BRYTER,
            "binary_sensor_entity": RISIKO,
            "risiko_sensor": "sensor.risiko",
            "switch_entity": LAST,
            "switch_high_priority": LAST,
            "switch_medium_priority": "switch.ekstra",
            "climate_entity": ROM,
        }
    )
    data = yaml.substitute(ra, verdier)
    data.pop("blueprint")
    data.update({"id": "vern", "alias": "Vern"})
    assert await async_setup_component(hass, "automation", {"automation": [data]})
    await hass.async_start()
    await hass.async_block_till_done()


async def test_frist_slipper_uten_ny_risikohendelse(hass, freezer, vern):
    await styr(hass)
    assert hass.states.is_state(LAST, "off")
    await tikk(hass, freezer, 600)
    assert hass.states.is_state(LAST, "on")
    assert LAST not in vern.kutt


async def test_max_off_er_tidligere_enn_timeskiftet(hass, freezer, vern):
    await styr(hass, max_off_minutes=2)
    await tikk(hass, freezer, 60)
    await styr(hass, max_off_minutes=60)
    await tikk(hass, freezer, 60)
    assert hass.states.is_state(LAST, "on")


async def test_blink_kan_ikke_omgaa_persistert_minste_paatid(hass, freezer, vern):
    await styr(hass)
    await styr(hass, False)
    for _ in range(3):
        await styr(hass, True)
        assert hass.states.is_state(LAST, "on")
        await styr(hass, False)
    # Last inn igjen fra Store: paatiden maa ikke forsvinne ved HA-restart.
    vern._stopp()
    del hass.data[DATA_LASTVERN]
    await async_setup_lastvern(hass)
    await tikk(hass, freezer, 299)
    await styr(hass)
    assert hass.states.is_state(LAST, "on")
    await tikk(hass, freezer, 1)
    await styr(hass)
    assert hass.states.is_state(LAST, "off")


@pytest.mark.parametrize("entity_id", [LAST, ROM])
async def test_ha_restart_gjenopptar_lagret_ansvar(hass, vern, entity_id):
    await styr(hass, entity_id=entity_id)
    vern._stopp()
    del hass.data[DATA_LASTVERN]
    await async_setup_lastvern(hass)
    await hass.async_block_till_done()
    assert not hass.data[DATA_LASTVERN].kutt
    assert hass.states.is_state(LAST, "on")
    assert hass.states.get(ROM).attributes["temperature"] == 21


async def test_utilgjengelig_aktuator_beholder_ansvaret_til_bekreftet_restore(hass, freezer, vern):
    await styr(hass)
    hass.states.async_set(LAST, "unavailable")
    await tikk(hass, freezer, 600)
    assert LAST in vern.kutt
    hass.states.async_set(LAST, "off")
    await hass.async_block_till_done()
    assert hass.states.is_state(LAST, "on")
    assert LAST not in vern.kutt


async def test_tjenestefeil_ved_restore_proeves_igjen(hass, freezer, vern):
    await styr(hass)

    async def feiler(_call):
        raise HomeAssistantError("ingen forbindelse")

    hass.services.async_register("switch", "turn_on", feiler)
    await styr(hass, False)
    assert LAST in vern.kutt
    assert hass.states.is_state(LAST, "off")

    async def virker(call):
        hass.states.async_set(call.data["entity_id"], "on")

    hass.services.async_register("switch", "turn_on", virker)
    await tikk(hass, freezer, 30)
    assert hass.states.is_state(LAST, "on")
    assert LAST not in vern.kutt


async def test_ingen_restore_foer_tilstanden_bekrefter_handlingen(hass, vern):
    await styr(hass)

    async def ingen_kvittering(_call):
        pass

    hass.services.async_register("switch", "turn_on", ingen_kvittering)
    await styr(hass, False)
    assert LAST in vern.kutt
    hass.states.async_set(LAST, "on")
    await hass.async_block_till_done()
    assert LAST not in vern.kutt


async def test_manuelt_av_og_manuelt_setpunkt_overtas_ikke(hass, vern):
    hass.states.async_set(LAST, "off")
    hass.states.async_set(ROM, "heat", {"temperature": 8})
    await styr(hass)
    await styr(hass, False)
    await styr(hass, entity_id=ROM)
    await styr(hass, False, entity_id=ROM)
    assert not vern.kutt
    assert hass.states.is_state(LAST, "off")
    assert hass.states.get(ROM).attributes["temperature"] == 8


async def test_nytt_manuelt_setpunkt_beholdes(hass, vern):
    await styr(hass, entity_id=ROM)
    hass.states.async_set(ROM, "heat", {"temperature": 19})
    await styr(hass, False, entity_id=ROM)
    assert hass.states.get(ROM).attributes["temperature"] == 19
    assert ROM not in vern.kutt


async def test_to_automasjoner_kan_ikke_overta_samme_aktive_kutt(hass, vern):
    await styr(hass)
    with pytest.raises(ServiceValidationError, match="styres allerede") as feil:
        await styr(hass, False, eier="automation.annen")
    assert feil.value.translation_domain == "effektvakt"
    assert feil.value.translation_key == "lastvern_opptatt"
    assert feil.value.translation_placeholders == {"entity_id": LAST, "eier": EIER}
    assert LAST in vern.kutt


@pytest.mark.parametrize("fil", ["enkel_lastkutt.yaml", "prioritert_lastkutt.yaml", "climate_min_temp.yaml"])
async def test_blueprint_unknown_on_med_automatikk_av_gjenoppretter(hass, vern, fil):
    await blueprint(hass, fil)
    hass.states.async_set(RISIKO, "on")
    hass.states.async_set("sensor.risiko", "over_terskel")
    await hass.async_block_till_done()
    assert vern.kutt
    hass.states.async_set(BRYTER, "off")
    hass.states.async_set(RISIKO, "unknown")
    hass.states.async_set("sensor.risiko", "unknown")
    await hass.async_block_till_done()
    hass.states.async_set(RISIKO, "on")
    hass.states.async_set("sensor.risiko", "over_terskel")
    await hass.async_block_till_done()
    assert not vern.kutt
    assert hass.states.is_state(LAST, "on")
    assert hass.states.get(ROM).attributes["temperature"] == 21


@pytest.mark.parametrize("fil", ["enkel_lastkutt.yaml", "prioritert_lastkutt.yaml", "climate_min_temp.yaml"])
async def test_automation_reload_under_kutt_beholder_uavhengig_fristslipp(hass, freezer, vern, fil):
    await blueprint(hass, fil)
    hass.states.async_set(RISIKO, "on")
    hass.states.async_set("sensor.risiko", "over_terskel")
    await hass.async_block_till_done()
    assert vern.kutt
    with patch("homeassistant.config.async_hass_config_yaml", return_value={"automation": []}):
        await hass.services.async_call("automation", "reload", {}, blocking=True)
    await hass.async_block_till_done()
    await tikk(hass, freezer, 600)
    assert not vern.kutt
    assert hass.states.is_state(LAST, "on")
    assert hass.states.get(ROM).attributes["temperature"] == 21


@pytest.mark.parametrize("fil", ["enkel_lastkutt.yaml", "prioritert_lastkutt.yaml", "climate_min_temp.yaml"])
async def test_vedvarende_risiko_kutter_igjen_foerst_etter_minste_paatid(hass, freezer, vern, fil):
    await blueprint(hass, fil)
    hass.states.async_set(RISIKO, "on")
    hass.states.async_set("sensor.risiko", "over_terskel")
    await hass.async_block_till_done()
    await tikk(hass, freezer, 600)
    assert not vern.kutt
    await tikk(hass, freezer, 240)
    assert not vern.kutt
    await tikk(hass, freezer, 60)
    assert vern.kutt


@pytest.mark.parametrize("fil", ["enkel_lastkutt.yaml", "prioritert_lastkutt.yaml", "climate_min_temp.yaml"])
async def test_blueprint_blink_under_paatid_kutter_ikke_paa_nytt(hass, freezer, vern, fil):
    await blueprint(hass, fil)
    for _ in range(2):
        hass.states.async_set(RISIKO, "on")
        hass.states.async_set("sensor.risiko", "over_terskel")
        await hass.async_block_till_done()
        hass.states.async_set(RISIKO, "off")
        hass.states.async_set("sensor.risiko", "god_margin")
        await hass.async_block_till_done()
        assert not vern.kutt
    hass.states.async_set(RISIKO, "on")
    hass.states.async_set("sensor.risiko", "over_terskel")
    await hass.async_block_till_done()
    assert not vern.kutt
    await tikk(hass, freezer, 301)
    assert vern.kutt


async def test_entry_unload_avbryter_ikke_aktivt_vern(hass, freezer, vern, oppsett):
    await styr(hass)
    assert await hass.config_entries.async_unload(oppsett.entry_id)
    await tikk(hass, freezer, 600)
    assert not vern.kutt
    assert hass.states.is_state(LAST, "on")


async def test_feilet_kutt_beholder_restoreansvaret(hass, freezer, vern):
    async def feiler_etter_kutt(call):
        hass.states.async_set(call.data["entity_id"], "off")
        raise HomeAssistantError("kvitteringen uteble")

    hass.services.async_register("switch", "turn_off", feiler_etter_kutt)
    with pytest.raises(HomeAssistantError, match="kvitteringen uteble"):
        await styr(hass)
    await tikk(hass, freezer, 30)
    assert hass.states.is_state(LAST, "on")
    assert not vern.kutt
