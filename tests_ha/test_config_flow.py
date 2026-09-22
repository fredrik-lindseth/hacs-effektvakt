"""Oppsettsflyten gjennom HA sin egen flytmotor.

``tests/`` tester hjelperne i ``config_flow.py`` som funksjoner: hvilke felt
skjemaet faar, hvordan lagrede verdier flettes. Det som bare finnes her er
motoren rundt dem, altsaa at stegene henger sammen, at selectorene validerer
det de skal, at ``_abort_if_unique_id_configured`` faktisk avbryter, og at
entryen flyten skriver er en HA kan laste etterpaa. Den siste er poenget:
en flyt kan vaere aldri saa riktig og likevel lage en entry som ikke gaar opp.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType, InvalidData

from custom_components.effektvakt.const import (
    CONF_DSO,
    CONF_ENERGY_SENSOR,
    CONF_KAPASITETSTRINN_CUSTOM,
    CONF_LAST_BRYTER,
    CONF_LAST_EFFEKT_SENSOR,
    CONF_LAST_NAVN,
    CONF_LAST_TERSKEL_W,
    CONF_LASTER,
    CONF_MIN_RISIKO_FOR_KUTT,
    CONF_POWER_SENSOR,
    CONF_RISIKO_HOLDETID_MINUTTER,
    CONF_SAFETY_BUFFER_KW,
    DOMAIN,
    ENTRY_VERSION,
)

from .conftest import (
    ALLE_ENTITETER,
    ENERGY_SENSOR,
    LAST_BRYTER,
    LAST_SENSOR,
    POWER_SENSOR,
    lag_entry,
)

TILGJENGELIG_KUTT = "sensor.effektvakt_tilgjengelig_kutt"
INNSTILLINGER = {
    CONF_SAFETY_BUFFER_KW: 2.0,
    CONF_MIN_RISIKO_FOR_KUTT: "over_terskel",
    CONF_RISIKO_HOLDETID_MINUTTER: 10,
}


if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _meny(hass: HomeAssistant, entry: MockConfigEntry, steg: str) -> dict:
    """Aapne Configure og velg ett av menyvalgene."""
    resultat = await hass.config_entries.options.async_init(entry.entry_id)
    assert resultat["type"] is FlowResultType.MENU
    assert resultat["step_id"] == "init"
    return await hass.config_entries.options.async_configure(resultat["flow_id"], {"next_step_id": steg})


async def _start_flyt(hass: HomeAssistant, dso: str = "bkk") -> dict:
    """Foerste steg: velg nettselskap, faa sensorskjemaet."""
    resultat = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert resultat["type"] is FlowResultType.FORM
    assert resultat["step_id"] == "user"

    resultat = await hass.config_entries.flow.async_configure(resultat["flow_id"], {CONF_DSO: dso})
    assert resultat["step_id"] == "sensors"
    return resultat


def _svaret_dialogen_viser(skjema: vol.Schema) -> dict[str, Any]:
    """Det Home Assistant sender tilbake naar brukeren bare trykker lagre.

    Frontenden fyller hvert felt med ``default``, eller med ``suggested_value``
    der det ikke finnes noen default, og sender verdiene tilbake som de staar.
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


async def test_hele_flyten_gir_en_entry_home_assistant_kan_laste(hass: HomeAssistant, maalere: None) -> None:
    """Fra tom HA til seks sensorer i drift, uten en eneste snarvei."""
    resultat = await _start_flyt(hass)
    resultat = await hass.config_entries.flow.async_configure(
        resultat["flow_id"],
        {CONF_POWER_SENSOR: POWER_SENSOR, CONF_ENERGY_SENSOR: ENERGY_SENSOR},
    )

    assert resultat["type"] is FlowResultType.CREATE_ENTRY
    assert resultat["data"][CONF_DSO] == "bkk"
    await hass.async_block_till_done()

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.state is ConfigEntryState.LOADED
    assert entry.version == ENTRY_VERSION
    # Oppsettet spoer ikke om kuttbare laster, saa den sensoren finnes ikke enda.
    for entity_id in [e for e in ALLE_ENTITETER if e != TILGJENGELIG_KUTT]:
        assert hass.states.get(entity_id) is not None, entity_id
    assert hass.states.get(TILGJENGELIG_KUTT) is None


async def test_tittelen_blir_nettselskapet(hass: HomeAssistant, maalere: None) -> None:
    """Brukeren ser nettselskapet i integrasjonslisten, ikke «Effektvakt»."""
    resultat = await _start_flyt(hass, dso="elvia")
    resultat = await hass.config_entries.flow.async_configure(resultat["flow_id"], {CONF_POWER_SENSOR: POWER_SENSOR})

    assert resultat["type"] is FlowResultType.CREATE_ENTRY
    assert resultat["title"] and resultat["title"] != "Effektvakt"


@pytest.mark.parametrize(
    ("enhet", "felt", "feil"),
    [
        ("A", CONF_POWER_SENSOR, "power_unit_invalid"),
        ("Wh", CONF_POWER_SENSOR, "power_unit_invalid"),
    ],
)
async def test_effektsensor_med_feil_enhet_avvises(
    hass: HomeAssistant, maalere: None, enhet: str, felt: str, feil: str
) -> None:
    """Enheten leses fra den ekte tilstandsmaskinen, ikke fra en fake."""
    hass.states.async_set("sensor.rar_maaler", "5", {"unit_of_measurement": enhet})

    resultat = await _start_flyt(hass)
    resultat = await hass.config_entries.flow.async_configure(
        resultat["flow_id"], {CONF_POWER_SENSOR: "sensor.rar_maaler"}
    )

    assert resultat["type"] is FlowResultType.FORM
    assert resultat["errors"] == {felt: feil}


async def test_ukjent_sensor_avvises(hass: HomeAssistant, maalere: None) -> None:
    resultat = await _start_flyt(hass)
    resultat = await hass.config_entries.flow.async_configure(
        resultat["flow_id"], {CONF_POWER_SENSOR: "sensor.finnes_ikke"}
    )

    assert resultat["errors"] == {CONF_POWER_SENSOR: "sensor_not_found"}


async def test_energisensor_med_feil_enhet_avvises(hass: HomeAssistant, maalere: None) -> None:
    hass.states.async_set("sensor.rar_energi", "5", {"unit_of_measurement": "kW"})

    resultat = await _start_flyt(hass)
    resultat = await hass.config_entries.flow.async_configure(
        resultat["flow_id"],
        {CONF_POWER_SENSOR: POWER_SENSOR, CONF_ENERGY_SENSOR: "sensor.rar_energi"},
    )

    assert resultat["errors"] == {CONF_ENERGY_SENSOR: "energy_unit_invalid"}


async def test_peak_sensor_advares_om_en_gang_og_kan_bekreftes(hass: HomeAssistant, maalere: None) -> None:
    """En time-maks-sensor som effektkilde gir tall som ser rolige ut hele timen.

    Advarselen skal komme, bekreftelsesboksen skal dukke opp i skjemaet
    etterpaa, og et bekreftet valg skal gaa gjennom. Rekkefoelgen er det
    flytmotoren eier.
    """
    hass.states.async_set("sensor.hus_max_power", "4000", {"unit_of_measurement": "W", "friendly_name": "Hus max"})

    resultat = await _start_flyt(hass)
    resultat = await hass.config_entries.flow.async_configure(
        resultat["flow_id"], {CONF_POWER_SENSOR: "sensor.hus_max_power"}
    )
    assert resultat["errors"] == {CONF_POWER_SENSOR: "peak_sensor_warning"}
    assert "confirm_peak_sensor" in str(resultat["data_schema"].schema)

    resultat = await hass.config_entries.flow.async_configure(
        resultat["flow_id"],
        {CONF_POWER_SENSOR: "sensor.hus_max_power", "confirm_peak_sensor": True},
    )
    assert resultat["type"] is FlowResultType.CREATE_ENTRY


async def test_samme_effektsensor_to_ganger_avbrytes(hass: HomeAssistant, oppsett: MockConfigEntry) -> None:
    """unique_id er domenet pluss effektsensoren, og HA haandhever den."""
    resultat = await _start_flyt(hass)
    resultat = await hass.config_entries.flow.async_configure(resultat["flow_id"], {CONF_POWER_SENSOR: POWER_SENSOR})

    assert resultat["type"] is FlowResultType.ABORT
    assert resultat["reason"] == "already_configured"


async def test_selectoren_avviser_noe_som_ikke_er_en_entitets_id(hass: HomeAssistant, maalere: None) -> None:
    """EntitySelector er HA sin validering, og den kjoerer foer vaar egen.

    Uten flytmotoren ville hjelperne vaare faatt strengen rett inn og lagret
    soppel i config entryen.
    """
    resultat = await _start_flyt(hass)
    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(resultat["flow_id"], {CONF_POWER_SENSOR: "ikke en entitet"})


async def test_ukjent_nettselskap_avvises_av_skjemaet(hass: HomeAssistant, maalere: None) -> None:
    """Nettselskapene er en lukket liste, og valget er en noekkel i config entryen."""
    resultat = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    with pytest.raises((InvalidData, vol.Invalid)):
        await hass.config_entries.flow.async_configure(resultat["flow_id"], {CONF_DSO: "finnes-ikke-nett"})


async def test_egendefinerte_trinn_gaar_via_prisstegt(hass: HomeAssistant, maalere: None) -> None:
    """«Egendefinert» aapner et ekstra steg, og trinnene havner i entryen."""
    resultat = await _start_flyt(hass, dso="custom")
    resultat = await hass.config_entries.flow.async_configure(resultat["flow_id"], {CONF_POWER_SENSOR: POWER_SENSOR})
    assert resultat["step_id"] == "pricing"

    resultat = await hass.config_entries.flow.async_configure(
        resultat["flow_id"], {CONF_KAPASITETSTRINN_CUSTOM: "[[5, 100], [10, 200], [null, 400]]"}
    )

    assert resultat["type"] is FlowResultType.CREATE_ENTRY
    assert len(resultat["data"][CONF_KAPASITETSTRINN_CUSTOM]) == 3
    await hass.async_block_till_done()
    assert hass.config_entries.async_entries(DOMAIN)[0].state is ConfigEntryState.LOADED


async def test_ugyldige_egendefinerte_trinn_blir_staaende_i_skjemaet(hass: HomeAssistant, maalere: None) -> None:
    resultat = await _start_flyt(hass, dso="custom")
    resultat = await hass.config_entries.flow.async_configure(resultat["flow_id"], {CONF_POWER_SENSOR: POWER_SENSOR})
    resultat = await hass.config_entries.flow.async_configure(
        resultat["flow_id"], {CONF_KAPASITETSTRINN_CUSTOM: "{ikke json"}
    )

    assert resultat["type"] is FlowResultType.FORM
    assert resultat["errors"] == {CONF_KAPASITETSTRINN_CUSTOM: "kapasitetstrinn_invalid"}


async def test_innstillingene_lagres_og_laster_oppsettet_paa_nytt(
    hass: HomeAssistant, oppsett: MockConfigEntry
) -> None:
    """Configure skriver til entry.data, og oppdateringslytteren tar resten."""
    resultat = await _meny(hass, oppsett, "innstillinger")
    assert resultat["step_id"] == "innstillinger"

    resultat = await hass.config_entries.options.async_configure(resultat["flow_id"], INNSTILLINGER)
    await hass.async_block_till_done()

    # Lagringen foerer tilbake til menyen: dialogen lukkes foerst paa «Ferdig».
    assert resultat["type"] is FlowResultType.MENU
    assert oppsett.data[CONF_SAFETY_BUFFER_KW] == 2.0
    assert oppsett.state is ConfigEntryState.LOADED
    assert oppsett.runtime_data.safety_buffer_kw == 2.0


async def test_ferdig_lukker_dialogen(hass: HomeAssistant, oppsett: MockConfigEntry) -> None:
    resultat = await _meny(hass, oppsett, "ferdig")
    assert resultat["type"] is FlowResultType.CREATE_ENTRY


async def test_innstillingsskjemaet_avviser_en_margin_utenfor_skalaen(
    hass: HomeAssistant, oppsett: MockConfigEntry
) -> None:
    """NumberSelector holder 0,1 til 5 kW, og det er HA som haandhever det."""
    resultat = await _meny(hass, oppsett, "innstillinger")

    with pytest.raises((InvalidData, vol.Invalid)):
        await hass.config_entries.options.async_configure(
            resultat["flow_id"], {**INNSTILLINGER, CONF_SAFETY_BUFFER_KW: 50}
        )


async def test_en_tur_innom_configure_uten_endringer_lar_alt_staa(hass: HomeAssistant, maalere: None) -> None:
    """Dialogen aapnes, svares paa med det den viser, og lagres.

    ``tests/`` proever den samme runden mot skjemafunksjonene. Her gaar den
    gjennom flytmotoren, saa selectorenes egen validering av defaultene er med:
    en default utenfor sitt eget valg ville felt nettopp her.
    """
    entry = lag_entry(
        safety_buffer_kw=2.5,
        min_risiko_for_kutt="over_terskel",
        risiko_holdetid_minutter=12,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    foer = dict(entry.data)

    resultat = await _meny(hass, entry, "innstillinger")
    resultat = await hass.config_entries.options.async_configure(
        resultat["flow_id"], _svaret_dialogen_viser(resultat["data_schema"])
    )
    await hass.async_block_till_done()

    assert resultat["type"] is FlowResultType.MENU
    assert dict(entry.data) == foer


async def test_gammelt_lagret_risikonivaa_holder_skjemaet_gyldig(hass: HomeAssistant, maalere: None) -> None:
    """De gamle verdiene ligger i folks config entries og maa ikke velte dialogen.

    ``medium`` er ikke lenger et gyldig valg i dropdownen, saa hadde det
    staatt som default, ville HA avvist sitt eget skjema.
    """
    entry = lag_entry(min_risiko_for_kutt="medium")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    resultat = await _meny(hass, entry, "innstillinger")

    assert resultat["data_schema"]({})[CONF_MIN_RISIKO_FOR_KUTT] == "like_under_terskel"


# --- kuttbare laster --------------------------------------------------------


async def test_en_ny_last_lagres_og_gir_sensoren_for_tilgjengelig_kutt(hass: HomeAssistant, maalere: None) -> None:
    """Uten laster finnes ikke sensoren. Legger du inn en, dukker den opp."""
    entry = lag_entry(laster=None)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(TILGJENGELIG_KUTT) is None

    resultat = await _meny(hass, entry, "legg_til_last")
    assert resultat["step_id"] == "legg_til_last"
    resultat = await hass.config_entries.options.async_configure(
        resultat["flow_id"],
        {
            CONF_LAST_EFFEKT_SENSOR: LAST_SENSOR,
            CONF_LAST_NAVN: "Bereder",
            CONF_LAST_BRYTER: LAST_BRYTER,
            CONF_LAST_TERSKEL_W: 1000,
        },
    )
    await hass.async_block_till_done()

    assert resultat["type"] is FlowResultType.MENU
    assert entry.data[CONF_LASTER] == [
        {
            CONF_LAST_EFFEKT_SENSOR: LAST_SENSOR,
            CONF_LAST_TERSKEL_W: 1000.0,
            CONF_LAST_NAVN: "Bereder",
            CONF_LAST_BRYTER: LAST_BRYTER,
        }
    ]
    tilstand = hass.states.get(TILGJENGELIG_KUTT)
    assert tilstand is not None
    assert float(tilstand.state) == pytest.approx(1.8)
    assert tilstand.attributes["kutt_kilder"][0]["bryter"] == LAST_BRYTER


async def test_menyen_tilbyr_ikke_redigering_foer_det_finnes_en_last(hass: HomeAssistant, maalere: None) -> None:
    entry = lag_entry(laster=None)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    resultat = await hass.config_entries.options.async_init(entry.entry_id)
    assert set(resultat["menu_options"]) == {"innstillinger", "legg_til_last", "ferdig"}


async def test_menyen_tilbyr_redigering_naar_en_last_finnes(hass: HomeAssistant, oppsett: MockConfigEntry) -> None:
    resultat = await hass.config_entries.options.async_init(oppsett.entry_id)
    assert set(resultat["menu_options"]) == {"innstillinger", "legg_til_last", "velg_last", "ferdig"}


async def test_lasten_kan_endres(hass: HomeAssistant, oppsett: MockConfigEntry) -> None:
    resultat = await _meny(hass, oppsett, "velg_last")
    assert resultat["step_id"] == "velg_last"
    resultat = await hass.config_entries.options.async_configure(
        resultat["flow_id"], {CONF_LAST_EFFEKT_SENSOR: LAST_SENSOR}
    )
    assert resultat["step_id"] == "rediger_last"

    resultat = await hass.config_entries.options.async_configure(
        resultat["flow_id"],
        {CONF_LAST_EFFEKT_SENSOR: LAST_SENSOR, CONF_LAST_NAVN: "Varmtvannsbereder", CONF_LAST_TERSKEL_W: 1500},
    )
    await hass.async_block_till_done()

    assert resultat["type"] is FlowResultType.MENU
    (last,) = oppsett.data[CONF_LASTER]
    assert last[CONF_LAST_NAVN] == "Varmtvannsbereder"
    assert last[CONF_LAST_TERSKEL_W] == 1500.0
    # Bryteren ble toemt i svaret, og da skal den vekk framfor aa overleve.
    assert CONF_LAST_BRYTER not in last


async def test_lasten_kan_fjernes_og_sensoren_forsvinner_med_den(hass: HomeAssistant, oppsett: MockConfigEntry) -> None:
    assert hass.states.get(TILGJENGELIG_KUTT) is not None

    resultat = await _meny(hass, oppsett, "velg_last")
    resultat = await hass.config_entries.options.async_configure(
        resultat["flow_id"], {CONF_LAST_EFFEKT_SENSOR: LAST_SENSOR}
    )
    resultat = await hass.config_entries.options.async_configure(
        resultat["flow_id"],
        {CONF_LAST_EFFEKT_SENSOR: LAST_SENSOR, CONF_LAST_TERSKEL_W: 1000, "slett": True},
    )
    await hass.async_block_till_done()

    assert resultat["type"] is FlowResultType.MENU
    assert CONF_LASTER not in oppsett.data
    assert hass.states.get(TILGJENGELIG_KUTT) is None


async def test_en_last_som_peker_paa_en_sensor_som_ikke_finnes_avvises(
    hass: HomeAssistant, oppsett: MockConfigEntry
) -> None:
    resultat = await _meny(hass, oppsett, "legg_til_last")
    resultat = await hass.config_entries.options.async_configure(
        resultat["flow_id"], {CONF_LAST_EFFEKT_SENSOR: "sensor.finnes_ikke", CONF_LAST_TERSKEL_W: 100}
    )
    assert resultat["type"] is FlowResultType.FORM
    assert resultat["errors"] == {CONF_LAST_EFFEKT_SENSOR: "sensor_not_found"}


async def test_en_last_med_feil_enhet_avvises(hass: HomeAssistant, oppsett: MockConfigEntry) -> None:
    hass.states.async_set("sensor.rar_last", "5", {"unit_of_measurement": "A"})

    resultat = await _meny(hass, oppsett, "legg_til_last")
    resultat = await hass.config_entries.options.async_configure(
        resultat["flow_id"], {CONF_LAST_EFFEKT_SENSOR: "sensor.rar_last", CONF_LAST_TERSKEL_W: 100}
    )
    assert resultat["errors"] == {CONF_LAST_EFFEKT_SENSOR: "power_unit_invalid"}


async def test_to_laster_kan_ikke_dele_effektsensor(hass: HomeAssistant, oppsett: MockConfigEntry) -> None:
    resultat = await _meny(hass, oppsett, "legg_til_last")
    resultat = await hass.config_entries.options.async_configure(
        resultat["flow_id"], {CONF_LAST_EFFEKT_SENSOR: LAST_SENSOR, CONF_LAST_TERSKEL_W: 100}
    )
    assert resultat["errors"] == {CONF_LAST_EFFEKT_SENSOR: "last_finnes_allerede"}


# --- migrering fra entry-versjon 1 ------------------------------------------


async def test_fredriks_oppsett_migreres_til_to_laster(hass: HomeAssistant, maalere: None) -> None:
    """Det ekte tilfellet: vvb_pluss_ekstra med bereder og varmekabler.

    Dette er testen som maa staa i en ekte Home Assistant. En stubbet
    migrering beviser bare at funksjonen regner riktig; her gaar entryen
    faktisk gjennom HA sin `async_migrate_entry` og lastes etterpaa.
    """
    hass.states.async_set(
        "sensor.varmekabler_bad_effekt",
        "550",
        {"unit_of_measurement": "W", "device_class": "power", "friendly_name": "Varmekabler bad"},
    )
    entry = lag_entry(
        version=1,
        laster=None,
        kutt_strategi="vvb_pluss_ekstra",
        vvb_power_sensor=LAST_SENSOR,
        ekstra_power_sensors=["sensor.varmekabler_bad_effekt"],
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.version == ENTRY_VERSION
    assert entry.state is ConfigEntryState.LOADED
    assert entry.data[CONF_LASTER] == [
        {CONF_LAST_EFFEKT_SENSOR: LAST_SENSOR, CONF_LAST_TERSKEL_W: 1000.0},
        {CONF_LAST_EFFEKT_SENSOR: "sensor.varmekabler_bad_effekt", CONF_LAST_TERSKEL_W: 100.0},
    ]
    for noekkel in ("kutt_strategi", "vvb_power_sensor", "ekstra_power_sensors"):
        assert noekkel not in entry.data

    # 1800 W over 1000 W-terskelen pluss 550 W over 100 W-terskelen.
    assert float(hass.states.get(TILGJENGELIG_KUTT).state) == pytest.approx(2.35)


async def test_migrert_oppsett_kan_redigeres_i_configure(hass: HomeAssistant, maalere: None) -> None:
    """Migreringen setter ingen bryter. Den legges til her, og da ser vakten kuttene."""
    entry = lag_entry(version=1, laster=None, kutt_strategi="vvb_status", vvb_power_sensor=LAST_SENSOR)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    resultat = await _meny(hass, entry, "velg_last")
    resultat = await hass.config_entries.options.async_configure(
        resultat["flow_id"], {CONF_LAST_EFFEKT_SENSOR: LAST_SENSOR}
    )
    resultat = await hass.config_entries.options.async_configure(
        resultat["flow_id"],
        {CONF_LAST_EFFEKT_SENSOR: LAST_SENSOR, CONF_LAST_BRYTER: LAST_BRYTER, CONF_LAST_TERSKEL_W: 1000},
    )
    await hass.async_block_till_done()

    assert entry.data[CONF_LASTER][0][CONF_LAST_BRYTER] == LAST_BRYTER
    kilder = hass.states.get(TILGJENGELIG_KUTT).attributes["kutt_kilder"]
    assert kilder[0]["bryter_paa"] is True


async def test_et_oppsett_uten_sensorer_migreres_uten_laster(hass: HomeAssistant, maalere: None) -> None:
    """blind uten sensorer: ingen laster, og ingen sensor for tilgjengelig kutt."""
    entry = lag_entry(version=1, laster=None, kutt_strategi="blind")
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.version == ENTRY_VERSION
    assert CONF_LASTER not in entry.data
    assert hass.states.get(TILGJENGELIG_KUTT) is None
