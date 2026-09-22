"""Tester for strings.json og oversettelsesfilene.

Filene driver fra hverandre saa snart noen legger til en noekkel i bare den ene,
og hassfest kjoerer bare i CI. Testene her er den lokale fangsten.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.effektvakt.binary_sensor import BINARY_SENSOR_KEY
from custom_components.effektvakt.const import RISIKO_GOD_MARGIN, RISIKO_LEVELS, SWITCH_KEY_AUTOMATIKK

PAKKE = Path(__file__).parent.parent / "custom_components" / "effektvakt"
STRINGS = PAKKE / "strings.json"
SPRAAK = {
    "strings.json": STRINGS,
    "en.json": PAKKE / "translations" / "en.json",
    "nb.json": PAKKE / "translations" / "nb.json",
}

SENSOR_NOEKLER = {
    "projisert_time_snitt",
    "margin_til_neste_trinn",
    "topp_3_snitt_denne_maned",
    "risiko_niva",
    "tilgjengelig_kutt",
    "kostnad_neste_trinn",
}


def _last(sti: Path) -> dict:
    return json.loads(sti.read_text(encoding="utf-8"))


def _noekkelsti(data: object, prefiks: str = "") -> set[str]:
    """Alle loevnoekler som punktseparerte stier, saa strukturen kan sammenlignes."""
    if not isinstance(data, dict):
        return {prefiks}
    stier: set[str] = set()
    for noekkel, verdi in data.items():
        stier |= _noekkelsti(verdi, f"{prefiks}.{noekkel}" if prefiks else noekkel)
    return stier


@pytest.mark.parametrize("navn", sorted(SPRAAK))
def test_filen_er_gyldig_json(navn):
    assert isinstance(_last(SPRAAK[navn]), dict)


@pytest.mark.parametrize("navn", ["en.json", "nb.json"])
def test_samme_noekkelstruktur_som_strings(navn):
    fasit = _noekkelsti(_last(STRINGS))
    faktisk = _noekkelsti(_last(SPRAAK[navn]))
    assert faktisk == fasit, f"{navn} mangler {sorted(fasit - faktisk)}, har ekstra {sorted(faktisk - fasit)}"


@pytest.mark.parametrize("navn", sorted(SPRAAK))
def test_alle_sensorer_har_navn(navn):
    sensorer = _last(SPRAAK[navn])["entity"]["sensor"]
    assert set(sensorer) == SENSOR_NOEKLER
    assert all(s.get("name") for s in sensorer.values())


@pytest.mark.parametrize("navn", sorted(SPRAAK))
def test_binary_sensor_og_switch_har_navn(navn):
    entity = _last(SPRAAK[navn])["entity"]
    assert entity["binary_sensor"][BINARY_SENSOR_KEY]["name"]
    assert entity["switch"][SWITCH_KEY_AUTOMATIKK]["name"]


@pytest.mark.parametrize("navn", sorted(SPRAAK))
def test_risiko_sensoren_har_tekst_for_hvert_niva(navn):
    """Uten dette viser sensoren den raa verdien, som var hele grunnen til jobben."""
    tilstander = _last(SPRAAK[navn])["entity"]["sensor"]["risiko_niva"]["state"]
    assert set(tilstander) == set(RISIKO_LEVELS)
    assert all(tilstander.values())


@pytest.mark.parametrize("navn", sorted(SPRAAK))
def test_selectoren_dekker_nivaaene_brukeren_kan_velge(navn):
    """Dropdownen utelater laveste nivaa, resten maa ha etikett."""
    valg = _last(SPRAAK[navn])["selector"]["min_risiko_for_kutt"]["options"]
    assert set(valg) == {lvl for lvl in RISIKO_LEVELS if lvl != RISIKO_GOD_MARGIN}


@pytest.mark.parametrize("navn", sorted(SPRAAK))
def test_binary_sensoren_har_tekst_for_paa_og_av(navn):
    tilstander = _last(SPRAAK[navn])["entity"]["binary_sensor"][BINARY_SENSOR_KEY]["state"]
    assert set(tilstander) == {"on", "off"}


def test_nb_er_identisk_med_strings():
    """strings.json er den norske kilden. Spriker de, er en av dem glemt."""
    assert _last(SPRAAK["nb.json"]) == _last(STRINGS)
