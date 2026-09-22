"""Tester for sensor.py."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from custom_components.effektvakt.const import RISIKO_LEVELS
from custom_components.effektvakt.sensor import (
    EffektvaktKostnadNesteTrinnSensor,
    EffektvaktMarginSensor,
    EffektvaktProjisertSensor,
    EffektvaktRisikoSensor,
    EffektvaktTilgjengeligKuttSensor,
    EffektvaktTopp3Sensor,
)


@pytest.fixture
def coord_mock():
    coord = MagicMock()
    coord.entry.entry_id = "test_entry"
    coord.data = {
        "projected_avg_kw": 5.5,
        "margin_kw": 4.5,
        "topp_3_snitt_denne_maned_kw": 4.2,
        "risiko_niva": "naermer_seg_terskel",
        "maal_terskel_kw": 10.0,
        "maal_trinn_kr": 415,
        "dagstak_kw": 10.0,
        "time_tak_kw": 10.0,
        "dagens_maks_kw": 4.2,
        "topp_2_andre_dager_kw": 8.4,
        "kutt_anbefalt_kw": 0.0,
        "kan_legge_paa_kw": 4.5,
        "kan_legge_paa_resten_av_timen_kw": 9.0,
        "elapsed_minutes_in_hour": 30,
        "minutter_igjen_av_timen": 30,
        "actual_kwh_this_hour": 2.5,
        "current_kw": 5.5,
        "last_update": "2026-05-25T14:30:00",
        "kostnad_neste_trinn_kr": 185,
        "trinn_na_kr": 415,
        "trinn_na_ovre_grense_kw": 10.0,
        "trinn_neste_kr": 600,
        "besparelse_trinn_under_kr": 165,
        "trinn_under_terskel_kw": 5.0,
        "trinn_under_oppnaelig": True,
        "trinn_under_realistisk": True,
        "kostnad_denne_timen_kr": 0,
        "topp_3_projisert_kw": 8.4,
        "minste_mulige_topp_3_kw": 4.2,
        "hoyeste_trinn": False,
        "topp_3_dager": [
            {"dato": "2026-05-23", "kw": 6.1},
            {"dato": "2026-05-24", "kw": 4.3},
            {"dato": "2026-05-25", "kw": 2.2},
        ],
        "topp_3_inkluderer_i_dag": True,
        "dag_som_ryker": None,
    }
    coord.kapasitetstrinn = [
        (2.0, 155),
        (5.0, 250),
        (10.0, 415),
        (15.0, 600),
        (float("inf"), 6900),
    ]
    return coord


def test_projisert_sensor_native_value(coord_mock):
    s = EffektvaktProjisertSensor(coord_mock)
    assert s.native_value == 5.5
    assert s.native_unit_of_measurement == "kW"


def test_margin_sensor_viser_hva_den_maales_mot(coord_mock):
    """Referansen flytter seg gjennom måneden, så den står i attributtene.

    Uten dem er marginen et tall uten nevner: 4,5 kW til gode mot hva?
    """
    s = EffektvaktMarginSensor(coord_mock)
    assert s.native_value == 4.5
    attrs = s.extra_state_attributes
    assert attrs["kutt_anbefalt_kw"] == 0.0
    assert attrs["kan_legge_paa_kw"] == 4.5
    assert attrs["maal_terskel_kw"] == 10.0
    assert attrs["maal_trinn_kr"] == 415
    assert attrs["dagstak_kw"] == 10.0
    assert attrs["time_tak_kw"] == 10.0
    assert attrs["dagens_maks_kw"] == 4.2
    assert attrs["topp_2_andre_dager_kw"] == 8.4


def test_topp_3_sensor(coord_mock):
    """Tilstanden er skranken: sum av inntil tre dagsmaks delt på tre.

    Samme tall som attributtet minste_mulige_topp_3_kw på kostnadssensoren, og
    det er med vilje: det skal ikke finnes to konkurrerende topp-3 i huset.
    """
    s = EffektvaktTopp3Sensor(coord_mock)
    assert s.native_value == 4.2
    assert (
        EffektvaktKostnadNesteTrinnSensor(coord_mock).extra_state_attributes["minste_mulige_topp_3_kw"]
        == s.native_value
    )


def test_topp_3_sensor_viser_hvilke_dager_snittet_bestaar_av(coord_mock):
    """Snittet alene sier ikke om timen betyr noe. Dagene bak det gjoer det."""
    attrs = EffektvaktTopp3Sensor(coord_mock).extra_state_attributes
    assert attrs["topp_3_dager"][0] == {"dato": "2026-05-23", "kw": 6.1}
    assert attrs["topp_3_inkluderer_i_dag"] is True
    assert attrs["dag_som_ryker"] is None
    # Fellesattributtene staar fortsatt
    assert attrs["current_kw"] == 5.5


def test_alle_sensorer_svarer_paa_hvor_mye_som_kan_slaas_paa_naa(coord_mock):
    """Spoersmaalet er «kan jeg sette paa vaskemaskinen», og det er et fellesattributt."""
    for klasse in (EffektvaktProjisertSensor, EffektvaktMarginSensor, EffektvaktKostnadNesteTrinnSensor):
        attrs = klasse(coord_mock).extra_state_attributes
        assert attrs["minutter_igjen_av_timen"] == 30
        assert attrs["kan_legge_paa_resten_av_timen_kw"] == 9.0


def test_risiko_sensor_native_value(coord_mock):
    s = EffektvaktRisikoSensor(coord_mock)
    assert s.native_value == "naermer_seg_terskel"


def test_risiko_sensor_options(coord_mock):
    s = EffektvaktRisikoSensor(coord_mock)
    assert s.options == RISIKO_LEVELS


@pytest.mark.parametrize(
    "klasse,noekkel",
    [
        (EffektvaktProjisertSensor, "projisert_time_snitt"),
        (EffektvaktMarginSensor, "margin_til_neste_trinn"),
        (EffektvaktTopp3Sensor, "topp_3_snitt_denne_maned"),
        (EffektvaktRisikoSensor, "risiko_niva"),
        (EffektvaktTilgjengeligKuttSensor, "tilgjengelig_kutt"),
        (EffektvaktKostnadNesteTrinnSensor, "kostnad_neste_trinn"),
    ],
)
def test_sensorene_henter_navnet_fra_oversettelsen(coord_mock, klasse, noekkel):
    """_attr_name slaar oversettelsen i HA, saa den skal ikke finnes."""
    s = klasse(coord_mock)
    assert s._attr_translation_key == noekkel
    assert not hasattr(s, "_attr_name")


@pytest.mark.parametrize(
    "klasse,noekkel",
    [
        (EffektvaktProjisertSensor, "projisert_time_snitt"),
        (EffektvaktMarginSensor, "margin_til_neste_trinn"),
        (EffektvaktTopp3Sensor, "topp_3_snitt_denne_maned"),
        (EffektvaktRisikoSensor, "risiko_niva"),
        (EffektvaktTilgjengeligKuttSensor, "tilgjengelig_kutt"),
        (EffektvaktKostnadNesteTrinnSensor, "kostnad_neste_trinn"),
    ],
)
def test_entitets_id_ene_staar_fast(coord_mock, klasse, noekkel):
    """Docs, blueprintene og kortet navngir disse id-ene. Utledet av navnet
    ville de blitt engelske for nye installasjoner."""
    s = klasse(coord_mock)
    assert s.entity_id == f"sensor.effektvakt_{noekkel}"
    assert s._attr_unique_id == f"test_entry_{noekkel}"


def test_tilgjengelig_kutt_sensor(coord_mock):
    coord_mock.data["tilgjengelig_kutt_kw"] = 2.5
    s = EffektvaktTilgjengeligKuttSensor(coord_mock)
    assert s.native_value == 2.5
    assert s.native_unit_of_measurement == "kW"


def test_kostnad_sensor_viser_timens_kostnad(coord_mock):
    """Tilstanden er kronene timen låser inn, ikke hoppet som står fast hele måneden.

    Hoppet ligger i attributtene. En sensor som viser 185 i 30 døgn er en
    attributtpose, ikke en måling.
    """
    s = EffektvaktKostnadNesteTrinnSensor(coord_mock)
    assert s.native_value == 0
    assert s.native_unit_of_measurement == "kr/mnd"

    coord_mock.data["kostnad_denne_timen_kr"] = 165
    assert s.native_value == 165


def test_kostnad_sensor_har_hoppet_som_attributt(coord_mock):
    attrs = EffektvaktKostnadNesteTrinnSensor(coord_mock).extra_state_attributes
    assert attrs["kostnad_neste_trinn_kr"] == 185


def test_kostnad_sensor_har_ingen_device_class(coord_mock):
    """MONETARY krever ISO-valuta og total-state_class, så satsen står uten device_class."""
    s = EffektvaktKostnadNesteTrinnSensor(coord_mock)
    assert s.device_class is None


def test_kostnad_sensor_attributter(coord_mock):
    attrs = EffektvaktKostnadNesteTrinnSensor(coord_mock).extra_state_attributes
    assert attrs["trinn_na_kr"] == 415
    assert attrs["trinn_na_ovre_grense_kw"] == 10.0
    assert attrs["trinn_neste_kr"] == 600
    assert attrs["besparelse_trinn_under_kr"] == 165
    assert attrs["trinn_under_terskel_kw"] == 5.0
    assert attrs["trinn_under_oppnaelig"] is True
    assert attrs["trinn_under_realistisk"] is True
    assert attrs["kostnad_denne_timen_kr"] == 0
    assert attrs["topp_3_projisert_kw"] == 8.4
    assert attrs["minste_mulige_topp_3_kw"] == 4.2


def test_kostnad_sensor_beholder_fellesattributtene(coord_mock):
    attrs = EffektvaktKostnadNesteTrinnSensor(coord_mock).extra_state_attributes
    assert attrs["current_kw"] == 5.5
    assert attrs["last_update"] == "2026-05-25T14:30:00"


def test_kapasitetstrinn_serialiserer_inf_som_null(coord_mock):
    """inf er ugyldig JSON og knekker recorder og websocket."""
    attrs = EffektvaktKostnadNesteTrinnSensor(coord_mock).extra_state_attributes
    assert attrs["kapasitetstrinn"] == [
        [2.0, 155],
        [5.0, 250],
        [10.0, 415],
        [15.0, 600],
        [None, 6900],
    ]
    json.dumps(attrs["kapasitetstrinn"])


def test_kapasitetstrinn_hele_attributtsettet_er_json_serialiserbart(coord_mock):
    attrs = EffektvaktKostnadNesteTrinnSensor(coord_mock).extra_state_attributes
    assert json.loads(json.dumps(attrs))["kapasitetstrinn"][-1] == [None, 6900]


def test_kostnad_sensor_uten_kjente_trinn(coord_mock):
    """Ukjent nettselskap gir None på alle kostnadsnøklene, og tom trinn-liste."""
    for nokkel in (
        "kostnad_neste_trinn_kr",
        "trinn_na_kr",
        "trinn_na_ovre_grense_kw",
        "trinn_neste_kr",
        "besparelse_trinn_under_kr",
        "trinn_under_terskel_kw",
        "trinn_under_oppnaelig",
        "trinn_under_realistisk",
        "kostnad_denne_timen_kr",
        "topp_3_projisert_kw",
        "minste_mulige_topp_3_kw",
        "hoyeste_trinn",
    ):
        coord_mock.data[nokkel] = None
    coord_mock.kapasitetstrinn = []

    s = EffektvaktKostnadNesteTrinnSensor(coord_mock)
    assert s.native_value is None
    attrs = s.extra_state_attributes
    assert attrs["kapasitetstrinn"] == []
    assert attrs["trinn_neste_kr"] is None


def test_kostnad_sensor_uten_coordinator_data(coord_mock):
    coord_mock.data = None
    s = EffektvaktKostnadNesteTrinnSensor(coord_mock)
    assert s.native_value is None
    assert s.extra_state_attributes is None
