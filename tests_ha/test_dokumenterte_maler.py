"""Prøv dashbordmalene og varsel-blueprinten i ekte HA."""

from pathlib import Path

import pytest
from homeassistant.helpers.template import Template
from homeassistant.setup import async_setup_component
from homeassistant.util import yaml

ROT = Path(__file__).resolve().parents[1]
P = "sensor.effektvakt_projisert_time_snitt"
K = "sensor.effektvakt_kostnad_neste_trinn"
S = "sensor.effektvakt_tilgjengelig_kutt"
E = "sensor.effektvakt_estimert_kuttenergi_resten_av_timen"


def maler():
    dashboard = yaml.load_yaml(str(ROT / "docs/dashboard-eksempel.yaml"))
    return [kort["content"] for kort in dashboard["views"][0]["cards"][1]["cards"]]


async def test_dashbord_uten_sensorer_gir_ikke_raad(hass):
    tekster = [Template(mal, hass).async_render(parse_result=False) for mal in maler()]
    assert "Venter på beregningsgrunnlag" in tekster[0]
    assert "øverste" not in tekster[0]
    assert "Ingen målte kuttkilder" in tekster[2]
    assert "Ingen profilgrunnlag" in tekster[3]
    assert "0 kW" not in tekster[2]


@pytest.mark.parametrize("gyldig", [True, False])
async def test_dashbord_bruker_timens_tak_og_krever_gyldig_grunnlag(hass, gyldig):
    hass.states.async_set(
        P,
        "2",
        {
            "beregning_gyldig": gyldig,
            "minutter_igjen_av_timen": 10,
            "kan_legge_paa_resten_av_timen_kw": 6,
            "time_tak_kw": 3.2,
            "maal_terskel_kw": 5,
        },
    )
    hass.states.async_set(K, "unknown")
    tekst = Template(maler()[0], hass).async_render(parse_result=False)
    if gyldig:
        assert "tak på 3,2 kW" in tekst
        assert "6 kW" in tekst
        assert "tariffvirkning er ukjent" in tekst
    else:
        assert "Venter på beregningsgrunnlag" in tekst
        assert "6 kW" not in tekst
    assert "ingenting ekstra" not in tekst


async def test_dashbord_skiller_kutt_terskel_og_manglende_maaling(hass):
    hass.states.async_set(
        S,
        "1",
        {
            "kutt_kilder": [
                {"navn": "Bereder", "entity_id": "sensor.bereder", "kuttet": True, "effekt_w": 0, "teller_med": False},
                {"navn": "Ovn", "entity_id": "sensor.ovn", "kuttet": False, "effekt_w": 20, "teller_med": False},
                {"navn": "Lader", "entity_id": "sensor.lader", "kuttet": False, "effekt_w": None, "teller_med": False},
            ]
        },
    )
    tekst = Template(maler()[2], hass).async_render(parse_result=False)
    assert "kuttet av Effektvakt" in tekst
    assert "under terskelen" in tekst
    assert "ukjent måling" in tekst
    assert "ikke med i summen" in tekst


async def test_dashbord_manuell_profil_uten_maalt_kutt(hass):
    hass.states.async_set(
        E,
        "0.17",
        {
            "lastprofiler": {
                "Gulvvarme": {"arbeidssyklus_pct": 15, "planleggingsestimat": True},
            }
        },
    )
    tekst = Template(maler()[3], hass).async_render(parse_result=False)
    assert "0,17 kWh" in tekst
    assert "15,0 % arbeidssyklus" in tekst
    assert "manuelt planleggingsanslag" in tekst
    assert "ikke målt sparing" in tekst


@pytest.mark.parametrize(
    "status,forventet",
    [
        ("aktiv", "fortsatt innen rekkevidde"),
        ("tapt", "styrer ikke nye kutt"),
        ("ikke_valgt", "Ingen eget månedsmål"),
        ("ugyldig", "kan ikke vurderes"),
    ],
)
async def test_dashbord_maalstatus_og_observasjon(hass, status, forventet):
    hass.states.async_set(P, "2", {"maal_status": status, "valgt_maal_kw": 5})
    hass.states.async_set("switch.effektvakt_automatikk", "off")
    tekst = Template(maler()[1], hass).async_render(parse_result=False)
    assert forventet in tekst
    assert "ingen nye kutt" in tekst


@pytest.mark.parametrize(
    "timen,neste,forventet",
    [
        (0, 165, "Trinnet over koster 165 kr"),
        (100, 165, "låser inn 100 kr"),
        (None, None, "på vei mot neste kapasitetstrinn"),
    ],
)
async def test_varsel_priser_uten_kutt_sensor_og_med_hovedbryter_av(hass, timen, neste, forventet):
    risiko = "sensor.effektvakt_risiko_niva"
    bryter = "switch.effektvakt_automatikk"
    hass.states.async_set(risiko, "god_margin")
    hass.states.async_set(bryter, "off")
    hass.states.async_set(
        K,
        str(timen) if timen is not None else "unknown",
        {
            "kostnad_denne_timen_kr": timen,
            "kostnad_neste_trinn_kr": neste,
        },
    )
    meldinger = []
    hass.services.async_register("notify", "test", lambda call: meldinger.append(call.data))
    ra = yaml.load_yaml(str(ROT / "docs/blueprints/kun_varsel.yaml"))
    verdier = {navn: felt["default"] for navn, felt in ra["blueprint"]["input"].items()}
    verdier.update({"notify_service": "test", "automatikk_switch": bryter})
    data = yaml.substitute(ra, verdier)
    data.pop("blueprint")
    data.update({"id": "varseltest", "alias": "Varseltest"})
    assert await async_setup_component(hass, "automation", {"automation": [data]})
    await hass.async_start()
    await hass.async_block_till_done()
    hass.states.async_set(risiko, "over_terskel")
    await hass.async_block_till_done()
    assert len(meldinger) == 1
    assert forventet in meldinger[0]["message"]
    assert "Automatikken er av" in meldinger[0]["message"]
    assert "Slå av det som varmer" in meldinger[0]["message"]
