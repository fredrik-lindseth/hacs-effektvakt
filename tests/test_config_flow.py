"""Tester for config_flow.

Skjemaene bygges av rene funksjoner, saa de kan proeves uten en kjoerende
Home Assistant. Det er nok til aa fange feilen som faktisk traff brukerne:
defaults som ikke hentet lagret verdi, og som dermed slettet den.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from custom_components.effektvakt.config_flow import (
    CONF_SLETT_LAST,
    flettet_data,
    innstillinger_skjema,
    last_skjema,
    looks_like_peak_sensor,
    parse_kapasitetstrinn,
    sensor_skjema,
    valider_last,
)
from custom_components.effektvakt.const import (
    CONF_CONFIRM_PEAK_SENSOR,
    CONF_DSO,
    CONF_ENERGY_SENSOR,
    CONF_LAST_BRYTER,
    CONF_LAST_EFFEKT_SENSOR,
    CONF_LAST_NAVN,
    CONF_LAST_TERSKEL_W,
    CONF_LASTER,
    CONF_MIN_RISIKO_FOR_KUTT,
    CONF_POWER_SENSOR,
    CONF_RISIKO_HOLDETID_MINUTTER,
    CONF_SAFETY_BUFFER_KW,
    DEFAULT_LAST_TERSKEL_W,
    DEFAULT_MIN_RISIKO_FOR_KUTT,
    RISIKO_LIKE_UNDER,
)
from custom_components.effektvakt.laster import LastOppsett

if TYPE_CHECKING:
    import voluptuous as vol

LAGRET: dict[str, Any] = {
    CONF_DSO: "bkk",
    CONF_POWER_SENSOR: "sensor.ams_effekt",
    CONF_ENERGY_SENSOR: "sensor.ams_energi",
    CONF_SAFETY_BUFFER_KW: 2.5,
    CONF_MIN_RISIKO_FOR_KUTT: "over_terskel",
    CONF_RISIKO_HOLDETID_MINUTTER: 12,
    CONF_LASTER: [
        {CONF_LAST_EFFEKT_SENSOR: "sensor.bereder", CONF_LAST_TERSKEL_W: 1000.0},
        {CONF_LAST_EFFEKT_SENSOR: "sensor.varmekabler", CONF_LAST_TERSKEL_W: 100.0},
    ],
}


def _svar_uten_endringer(skjema: vol.Schema) -> dict[str, Any]:
    """Det dialogen sender tilbake naar brukeren bare trykker lagre.

    Home Assistant fyller feltene med default, eller med suggested_value der
    det ikke finnes noen default, og sender verdiene tilbake som de staar.
    """
    svar: dict[str, Any] = {}
    for marker in skjema.schema:
        default = getattr(marker, "default", None)
        if callable(default):
            svar[str(marker.schema)] = default()
            continue
        foreslaatt = (marker.description or {}).get("suggested_value")
        if foreslaatt is not None:
            svar[str(marker.schema)] = foreslaatt
    return svar


def _felt(skjema: vol.Schema) -> set[str]:
    return {str(marker.schema) for marker in skjema.schema}


@pytest.mark.parametrize(
    "entity_id,friendly,expected",
    [
        ("sensor.tibber_max_power", "Tibber Max Power", True),
        ("sensor.house_peak_power", "House Peak", True),
        ("sensor.power_max_per_hour", "Power Max Per Hour", True),
        ("sensor.tibber_pulse_power", "Tibber Pulse Power", False),
        ("sensor.house_power", "House Power", False),
        ("sensor.average_power", "Average Power", True),
        ("sensor.power_average_per_hour", "Power Average", True),
    ],
)
def test_looks_like_peak_sensor(entity_id: str, friendly: str, expected: bool):
    assert looks_like_peak_sensor(entity_id, friendly_name=friendly) is expected


def test_configure_beholder_alt_naar_ingenting_endres():
    """Regresjonen: en tur innom Configure skal ikke roere konfigurasjonen.

    Feilen var usynlig fordi ingen test aapnet dialogen og lagret den igjen.
    """
    svar = _svar_uten_endringer(innstillinger_skjema(LAGRET))
    assert flettet_data(LAGRET, svar) == LAGRET


def test_configure_viser_de_lagrede_verdiene():
    svar = _svar_uten_endringer(innstillinger_skjema(LAGRET))
    assert svar[CONF_SAFETY_BUFFER_KW] == 2.5
    assert svar[CONF_RISIKO_HOLDETID_MINUTTER] == 12


def test_configure_endrer_det_brukeren_faktisk_endret():
    svar = _svar_uten_endringer(innstillinger_skjema(LAGRET))
    svar[CONF_SAFETY_BUFFER_KW] = 0.8
    ny = flettet_data(LAGRET, svar)
    assert ny[CONF_SAFETY_BUFFER_KW] == 0.8
    assert ny[CONF_LASTER] == LAGRET[CONF_LASTER]


def test_innstillingsskjemaet_roerer_ikke_lastene():
    """Lastene redigeres i sine egne steg, saa de skal ikke staa i dette skjemaet."""
    assert CONF_LASTER not in _felt(innstillinger_skjema(LAGRET))


def test_configure_tar_defaults_naar_ingenting_er_lagret():
    """Oppsettet spoer ikke lenger om innstillingene, saa Configure fyller dem."""
    tomt = {CONF_DSO: "bkk", CONF_POWER_SENSOR: "sensor.ams_effekt"}
    svar = _svar_uten_endringer(innstillinger_skjema(tomt))
    assert svar[CONF_MIN_RISIKO_FOR_KUTT] == DEFAULT_MIN_RISIKO_FOR_KUTT


def test_configure_oversetter_gammelt_risikonivaa():
    """Entries fra foer omdoepingen lagret 'medium' og skal ikke vises tomt."""
    svar = _svar_uten_endringer(innstillinger_skjema({CONF_MIN_RISIKO_FOR_KUTT: "medium"}))
    assert svar[CONF_MIN_RISIKO_FOR_KUTT] == RISIKO_LIKE_UNDER


# --- kuttbare laster --------------------------------------------------------


def test_lastskjemaet_spoer_om_sensor_navn_bryter_og_terskel():
    assert _felt(last_skjema()) == {
        CONF_LAST_EFFEKT_SENSOR,
        CONF_LAST_NAVN,
        CONF_LAST_BRYTER,
        CONF_LAST_TERSKEL_W,
    }


def test_lastskjemaet_defaulter_terskelen():
    assert _svar_uten_endringer(last_skjema())[CONF_LAST_TERSKEL_W] == DEFAULT_LAST_TERSKEL_W


def test_lastskjemaet_viser_den_lagrede_lasten():
    lagret = {
        CONF_LAST_EFFEKT_SENSOR: "sensor.bereder",
        CONF_LAST_NAVN: "Bereder",
        CONF_LAST_BRYTER: "switch.bereder",
        CONF_LAST_TERSKEL_W: 1000.0,
    }
    svar = _svar_uten_endringer(last_skjema(lagret))
    assert svar == lagret


def test_slettevalget_kommer_bare_naar_lasten_finnes_fra_foer():
    assert CONF_SLETT_LAST not in _felt(last_skjema())
    assert CONF_SLETT_LAST in _felt(last_skjema(kan_slettes=True))


def test_lasten_leses_ut_av_svaret():
    last, feil = valider_last(
        {
            CONF_LAST_EFFEKT_SENSOR: "sensor.bereder",
            CONF_LAST_NAVN: "Bereder",
            CONF_LAST_BRYTER: "switch.bereder",
            CONF_LAST_TERSKEL_W: 1000.0,
        },
        lagrede=[],
    )
    assert feil == {}
    assert last == LastOppsett("sensor.bereder", "Bereder", "switch.bereder", 1000.0)


def test_tomt_navn_og_tom_bryter_blir_ingenting():
    last, _ = valider_last(
        {CONF_LAST_EFFEKT_SENSOR: "sensor.kabler", CONF_LAST_NAVN: "  ", CONF_LAST_BRYTER: ""},
        lagrede=[],
    )
    assert last.navn is None
    assert last.bryter is None


def test_to_laster_kan_ikke_dele_effektsensor():
    """Delte de den, ville tilgjengelig_kutt talt den samme effekten to ganger."""
    last, feil = valider_last(
        {CONF_LAST_EFFEKT_SENSOR: "sensor.bereder"},
        lagrede=[LastOppsett("sensor.bereder")],
    )
    assert last is None
    assert feil == {CONF_LAST_EFFEKT_SENSOR: "last_finnes_allerede"}


def test_lasten_kan_beholde_sin_egen_sensor_naar_den_redigeres():
    last, feil = valider_last(
        {CONF_LAST_EFFEKT_SENSOR: "sensor.bereder", CONF_LAST_NAVN: "Nytt navn"},
        lagrede=[LastOppsett("sensor.bereder")],
        erstatter="sensor.bereder",
    )
    assert feil == {}
    assert last.navn == "Nytt navn"


def test_bekreftelsesboksen_vises_foerst_etter_advarselen():
    uten = sensor_skjema({}, vis_bekreftelse=False)
    med = sensor_skjema({}, vis_bekreftelse=True)
    assert CONF_CONFIRM_PEAK_SENSOR not in _felt(uten)
    assert CONF_CONFIRM_PEAK_SENSOR in _felt(med)


def test_sensorsteget_husker_det_brukeren_skrev():
    """Etter peak-advarselen maa ikke sensorene plukkes paa nytt."""
    forrige = {CONF_POWER_SENSOR: "sensor.tibber_max_power", CONF_ENERGY_SENSOR: "sensor.ams_energi"}
    svar = _svar_uten_endringer(sensor_skjema(forrige, vis_bekreftelse=True))
    assert svar[CONF_POWER_SENSOR] == "sensor.tibber_max_power"
    assert svar[CONF_ENERGY_SENSOR] == "sensor.ams_energi"
    assert svar[CONF_CONFIRM_PEAK_SENSOR] is False


# --- egendefinerte kapasitetstrinn ------------------------------------------


def test_trinnene_leses_som_kw_og_kr_par():
    assert parse_kapasitetstrinn("[[2, 155], [5, 250]]") == [(2.0, 155), (5.0, 250)]


def test_oeverste_trinn_kan_skrives_uten_oevre_grense():
    """null er trinnet uten tak. Uten det melder vakten god margin over hoeyeste tall."""
    assert parse_kapasitetstrinn("[[2, 155], [5, 250], [null, 415]]") == [
        (2.0, 155),
        (5.0, 250),
        (None, 415),
    ]


def test_null_lagres_som_null_og_ikke_som_uendelig():
    """Entry-data skal vaere gyldig JSON. oppsett.les_trinn gjoer null om til inf."""
    json.dumps(parse_kapasitetstrinn("[[2, 155], [null, 415]]"))


@pytest.mark.parametrize(
    "tekst",
    [
        "[[null, 155], [5, 250]]",  # det aapne trinnet maa staa sist
        "[[2, 155], [null, 250], [null, 415]]",  # bare ett aapent trinn
        "[[5, 250], [2, 155]]",  # ikke stigende
        "[[2, 155], [2, 250]]",  # like terskler
        "[]",
        "[[2]]",
        "ikke json",
        '{"2": 155}',
    ],
)
def test_ugyldige_trinn_avvises(tekst: str):
    with pytest.raises((ValueError, TypeError)):
        parse_kapasitetstrinn(tekst)
