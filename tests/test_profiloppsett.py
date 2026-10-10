"""Validering og bakoverkompatibel lagring av manuelle og automatiske profiler."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from custom_components.effektvakt.config_flow import valider_last
from custom_components.effektvakt.laster import LastAvlesning, LastOppsett, last_til_lagring, les_laster
from custom_components.effektvakt.lastprofiler import Lastprofiler


def _manuell():
    return {"navn": "Gulv", "profil": "manuell", "nominell_w": 2300, "arbeidssyklus_pct": 15}


def test_manuell_uten_sensor_roundtrip_bevarer_forutsetningene():
    last, feil = valider_last(_manuell(), lagrede=[])
    assert not feil
    assert last.effekt_sensor == ""
    assert last.noekkel == "manuell:Gulv"
    assert les_laster([last_til_lagring(last)]) == [last]


@pytest.mark.parametrize("profil", ["av", "auto"])
def test_sensor_kreves_naar_profilen_ikke_er_manuell(profil):
    _, feil = valider_last({"navn": "Gulv", "profil": profil}, lagrede=[])
    assert "effekt_sensor" in feil


@pytest.mark.parametrize("felt", ["navn", "nominell_w", "arbeidssyklus_pct"])
def test_manuell_sensorloes_last_krever_navn_og_begge_forutsetninger(felt):
    svar = _manuell()
    del svar[felt]
    last, feil = valider_last(svar, lagrede=[])
    assert last is None
    assert felt in feil


@pytest.mark.parametrize("verdi", [-1, 101, float("nan"), float("inf"), True])
def test_duty_prosent_avvises_utenfor_gyldig_omraade(verdi):
    last, feil = valider_last(_manuell() | {"arbeidssyklus_pct": verdi}, lagrede=[])
    assert last is None
    assert "arbeidssyklus_pct" in feil


@pytest.mark.parametrize("verdi", [0, 100])
def test_null_og_hundre_prosent_er_gyldige_forutsetninger(verdi):
    last, feil = valider_last(_manuell() | {"arbeidssyklus_pct": verdi}, lagrede=[])
    assert not feil
    assert last.arbeidssyklus_pct == verdi


def test_duplikate_manuelle_navn_og_aktuatorer_avvises():
    lagret, _ = valider_last(_manuell() | {"bryter": "climate.gulv"}, lagrede=[])
    assert valider_last(_manuell(), lagrede=[lagret])[1]
    assert valider_last(_manuell() | {"navn": "Annet", "bryter": "climate.gulv"}, lagrede=[lagret])[1]
    assert not valider_last(_manuell(), lagrede=[lagret], erstatter=lagret.noekkel)[1]


def test_gammelt_oppsett_far_ingen_profil_eller_nye_lagringsfelter():
    post = {"effekt_sensor": "sensor.varme", "terskel_w": 100}
    last = les_laster([post])[0]
    assert last.profil == "av"
    assert last.noekkel == "sensor.varme"
    assert last_til_lagring(last) == post


def test_auto_med_null_nominell_effekt_skal_ikke_kunne_krasje_estimater():
    last, feil = valider_last({"effekt_sensor": "sensor.varme", "profil": "auto", "nominell_w": 0}, lagrede=[])
    assert last is None
    assert "nominell_w" in feil


@pytest.mark.parametrize("felt", ["nominell_w", "typisk_paa_minutter"])
def test_lagret_null_i_positive_felt_skal_ikke_krasje_koordinator(felt):
    laster = les_laster([{"effekt_sensor": "sensor.varme", "profil": "auto", felt: 0}])
    data = Lastprofiler().beregn(
        [LastAvlesning(last, 2000) for last in laster],
        now=datetime(2026, 1, 1, tzinfo=UTC),
        resttid_s=1800,
        profiler={},
    )
    assert data["profilraad_energi_kwh"] == 0


def test_sensorbasert_manuell_og_auto_kan_ikke_duplisere_maalt_last():
    lagret = LastOppsett("sensor.varme", profil="auto")
    _, feil = valider_last(_manuell() | {"effekt_sensor": "sensor.varme"}, lagrede=[lagret])
    assert feil["effekt_sensor"] == "last_finnes_allerede"
