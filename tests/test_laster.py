"""Tester for laster.py: lastelisten, summen og observasjonen av et kutt.

Ren modul uten HA, så alt her er funksjoner inn og ut. Flaten mot
tilstandsmaskinen ligger i test_kutt_kilder.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from custom_components.effektvakt.const import DEFAULT_LAST_TERSKEL_W
from custom_components.effektvakt.laster import (
    KuttSporing,
    LastAvlesning,
    LastOppsett,
    build_kutt_kilder,
    compute_tilgjengelig_kutt_kw,
    last_til_lagring,
    les_laster,
    migrer_til_laster,
    oppdater_kuttsporing,
    teller_med,
)

NA = datetime(2026, 5, 25, 14, 30, 0)
BEREDER = LastOppsett(effekt_sensor="sensor.bereder_effekt", navn="Bereder", bryter="switch.bereder", terskel_w=1000.0)
KABLER = LastOppsett(effekt_sensor="sensor.varmekabler_bad", navn="Varmekabler bad", terskel_w=100.0)


def _av(oppsett: LastOppsett, effekt_w: float | None, *, bryter_paa: bool | None = None, navn: str | None = None):
    return LastAvlesning(oppsett=oppsett, effekt_w=effekt_w, bryter_paa=bryter_paa, friendly_name=navn)


# --- lesing av config entryen ----------------------------------------------


def test_lastelisten_leses_med_alle_fire_feltene():
    laster = les_laster(
        [
            {
                "effekt_sensor": "sensor.bereder",
                "navn": "Bereder",
                "bryter": "switch.bereder",
                "terskel_w": 1000,
            }
        ]
    )
    assert laster == [LastOppsett("sensor.bereder", "Bereder", "switch.bereder", 1000.0)]


def test_navn_og_bryter_er_valgfrie():
    (last,) = les_laster([{"effekt_sensor": "sensor.kabler"}])
    assert last.navn is None
    assert last.bryter is None
    assert last.terskel_w == DEFAULT_LAST_TERSKEL_W


def test_tomme_strenger_er_det_samme_som_manglende_felt():
    """Et felt brukeren har tømt skal ikke bli til en entitets-id som er tom."""
    (last,) = les_laster([{"effekt_sensor": "sensor.kabler", "navn": "  ", "bryter": ""}])
    assert last.navn is None
    assert last.bryter is None


@pytest.mark.parametrize(
    "raa",
    [None, {}, "sensor.tull", [], [{"navn": "Uten sensor"}], ["ikke en dict"]],
)
def test_soeppel_i_lastelisten_gir_ingen_laster(raa):
    """En config entry skal kunne leses selv om noe er skrevet feil inn i den."""
    assert les_laster(raa) == []


def test_negativ_terskel_faller_tilbake_paa_defaulten():
    (last,) = les_laster([{"effekt_sensor": "sensor.kabler", "terskel_w": -5}])
    assert last.terskel_w == DEFAULT_LAST_TERSKEL_W


def test_lagring_utelater_tomme_felt():
    assert last_til_lagring(LastOppsett("sensor.kabler", terskel_w=100.0)) == {
        "effekt_sensor": "sensor.kabler",
        "terskel_w": 100.0,
    }


def test_lagring_og_lesing_er_hverandres_motsatte():
    assert les_laster([last_til_lagring(BEREDER), last_til_lagring(KABLER)]) == [BEREDER, KABLER]


# --- migrering fra strategi-oppsettet ---------------------------------------


def test_fredriks_oppsett_blir_to_laster_med_hver_sin_terskel():
    """vvb_pluss_ekstra med en Shelly-plugg paa berederen og varmekabler paa badet."""
    ny = migrer_til_laster(
        {
            "dso": "bkk",
            "power_sensor": "sensor.ams_effekt",
            "kutt_strategi": "vvb_pluss_ekstra",
            "vvb_power_sensor": "sensor.shelly_bereder_effekt",
            "ekstra_power_sensors": ["sensor.varmekabler_bad_effekt"],
        }
    )
    assert ny["laster"] == [
        {"effekt_sensor": "sensor.shelly_bereder_effekt", "terskel_w": 1000.0},
        {"effekt_sensor": "sensor.varmekabler_bad_effekt", "terskel_w": 100.0},
    ]
    assert ny["dso"] == "bkk"
    assert ny["power_sensor"] == "sensor.ams_effekt"


@pytest.mark.parametrize("noekkel", ["kutt_strategi", "vvb_power_sensor", "ekstra_power_sensors"])
def test_de_gamle_noeklene_er_borte_etter_migrering(noekkel):
    ny = migrer_til_laster(
        {
            "kutt_strategi": "vvb_status",
            "vvb_power_sensor": "sensor.vvb",
            "ekstra_power_sensors": ["sensor.kabler"],
        }
    )
    assert noekkel not in ny


def test_blind_mister_ikke_sensorene_brukeren_har_pekt_paa():
    """Strategien styrte bare visningen. Sensorene er laster han faktisk har."""
    ny = migrer_til_laster({"kutt_strategi": "blind", "vvb_power_sensor": "sensor.vvb"})
    assert ny["laster"] == [{"effekt_sensor": "sensor.vvb", "terskel_w": 1000.0}]


def test_et_oppsett_uten_sensorer_faar_ingen_lasteliste():
    """Ingen tom liste i entryen: feltet skal bare ikke finnes."""
    ny = migrer_til_laster({"dso": "bkk", "kutt_strategi": "blind"})
    assert "laster" not in ny


def test_migrering_er_idempotent():
    foerste = migrer_til_laster({"kutt_strategi": "vvb_status", "vvb_power_sensor": "sensor.vvb"})
    assert migrer_til_laster(foerste) == foerste


def test_samme_sensor_to_steder_blir_en_last():
    ny = migrer_til_laster({"vvb_power_sensor": "sensor.vvb", "ekstra_power_sensors": ["sensor.vvb", "sensor.kabler"]})
    assert [last["effekt_sensor"] for last in ny["laster"]] == ["sensor.vvb", "sensor.kabler"]


# --- hva som teller naa -----------------------------------------------------


def test_terskelen_er_streng():
    assert teller_med(effekt_w=1000.1, terskel_w=1000.0) is True
    assert teller_med(effekt_w=1000.0, terskel_w=1000.0) is False


def test_ulesbar_sensor_teller_ikke():
    """None er «vet ikke», og det er noe annet enn 0 W."""
    assert teller_med(effekt_w=None, terskel_w=100.0) is False


def test_summen_er_de_som_teller_med():
    kutt = compute_tilgjengelig_kutt_kw([_av(BEREDER, 1800.0), _av(KABLER, 550.0)])
    assert kutt == pytest.approx(2.35)


def test_last_under_egen_terskel_teller_ikke_med():
    """Berederen i pause: 40 W er standby, ikke oppvarming."""
    assert compute_tilgjengelig_kutt_kw([_av(BEREDER, 40.0), _av(KABLER, 550.0)]) == pytest.approx(0.55)


def test_uten_laster_finnes_det_ikke_noe_svar():
    """Ikke 0,3 og ikke 0: None. Sensoren opprettes ikke i det hele tatt."""
    assert compute_tilgjengelig_kutt_kw([]) is None


def test_konfigurert_last_uten_lesbar_sensor_gir_null_kw_ikke_none():
    """Lasten finnes, vi vet bare ikke hva den trekker. Summen er da 0 kW."""
    assert compute_tilgjengelig_kutt_kw([_av(BEREDER, None)]) == 0.0


def test_kilden_har_bryteren_med_selv_uten_kutt():
    (kilde,) = build_kutt_kilder(avlesninger=[_av(BEREDER, 1800.0, bryter_paa=True)])
    assert kilde.bryter == "switch.bereder"
    assert kilde.bryter_paa is True
    assert kilde.kuttet is False
    assert kilde.kuttet_siden is None


def test_last_uten_eget_navn_arver_sensorens():
    (kilde,) = build_kutt_kilder(avlesninger=[_av(LastOppsett("sensor.kabler"), 550.0, navn="Varmekabler bad")])
    assert kilde.navn == "Varmekabler bad"


def test_eget_navn_vinner_over_sensorens():
    (kilde,) = build_kutt_kilder(avlesninger=[_av(KABLER, 550.0, navn="sensor_kabler_power_2")])
    assert kilde.navn == "Varmekabler bad"


def test_alle_laster_er_med_ogsaa_de_som_ikke_teller():
    """Forskjellen mellom «finnes ikke» og «teller ikke nå» er verdt å se."""
    kilder = build_kutt_kilder(avlesninger=[_av(BEREDER, 40.0), _av(KABLER, None)])
    assert [k.teller_med for k in kilder] == [False, False]
    assert [k.effekt_w for k in kilder] == [40.0, None]


# --- observasjon av kutt ----------------------------------------------------


def _spor(sporing, *, bryter_paa, effekt_w=1800.0, kutt_anbefalt=True, now=NA):
    return oppdater_kuttsporing(
        sporing=sporing,
        avlesninger=[_av(BEREDER, effekt_w, bryter_paa=bryter_paa)],
        kutt_anbefalt=kutt_anbefalt,
        now=now,
    )


def test_bryter_av_mens_kutt_er_anbefalt_er_vaart_kutt():
    sporing: dict[str, KuttSporing] = {}
    _spor(sporing, bryter_paa=True)
    (observasjon,) = _spor(sporing, bryter_paa=False, effekt_w=0.0)

    assert observasjon.kuttet is True
    assert observasjon.effekt_w == 1800.0
    assert sporing[BEREDER.effekt_sensor].kuttet_siden == NA


def test_bryter_av_uten_anbefaling_er_noen_andre():
    """Slaar brukeren av berederen selv, er det ikke en innsparing vi kan ta æren for."""
    sporing: dict[str, KuttSporing] = {}
    _spor(sporing, bryter_paa=True)
    assert _spor(sporing, bryter_paa=False, effekt_w=0.0, kutt_anbefalt=False) == []
    assert sporing[BEREDER.effekt_sensor].kuttet_siden is None


def test_bryter_som_alt_stod_av_er_ikke_et_kutt():
    """Uten et skifte fra paa til av har ingenting skjedd."""
    sporing: dict[str, KuttSporing] = {}
    assert _spor(sporing, bryter_paa=False, effekt_w=0.0) == []
    assert _spor(sporing, bryter_paa=False, effekt_w=0.0) == []
    assert sporing[BEREDER.effekt_sensor].kuttet_siden is None


def test_kuttet_staar_til_lasten_kommer_tilbake():
    sporing: dict[str, KuttSporing] = {}
    _spor(sporing, bryter_paa=True)
    _spor(sporing, bryter_paa=False, effekt_w=0.0)
    _spor(sporing, bryter_paa=False, effekt_w=0.0, now=NA + timedelta(minutes=5))
    assert sporing[BEREDER.effekt_sensor].kuttet_siden == NA

    (observasjon,) = _spor(sporing, bryter_paa=True, effekt_w=1800.0, now=NA + timedelta(minutes=12))
    assert observasjon.kuttet is False
    assert observasjon.varighet_s == pytest.approx(12 * 60)
    assert sporing[BEREDER.effekt_sensor].kuttet_siden is None


def test_bryter_uten_svar_endrer_ingenting():
    """«unavailable» er ikke «av». Et gjett hadde blitt et kutt som aldri skjedde."""
    sporing: dict[str, KuttSporing] = {}
    _spor(sporing, bryter_paa=True)
    assert _spor(sporing, bryter_paa=None, effekt_w=None) == []
    assert sporing[BEREDER.effekt_sensor].kuttet_siden is None
    assert sporing[BEREDER.effekt_sensor].forrige_bryter_paa is True


def test_last_uten_bryter_spores_ikke():
    sporing: dict[str, KuttSporing] = {}
    observasjoner = oppdater_kuttsporing(
        sporing=sporing,
        avlesninger=[_av(KABLER, 550.0)],
        kutt_anbefalt=True,
        now=NA,
    )
    assert observasjoner == []
    assert sporing == {}


def test_sporingen_glemmer_laster_som_er_fjernet():
    sporing: dict[str, KuttSporing] = {}
    _spor(sporing, bryter_paa=True)
    oppdater_kuttsporing(sporing=sporing, avlesninger=[], kutt_anbefalt=False, now=NA)
    assert sporing == {}


def test_kuttet_effekt_er_det_lasten_trakk_foer_kuttet():
    """Sensoren viser 0 W i det bryteren gaar av. Verdien av kuttet er det den trakk foer."""
    sporing: dict[str, KuttSporing] = {}
    _spor(sporing, bryter_paa=True, effekt_w=1950.0)
    _spor(sporing, bryter_paa=False, effekt_w=0.0)
    (kilde,) = build_kutt_kilder(
        avlesninger=[_av(BEREDER, 0.0, bryter_paa=False)],
        sporing=sporing,
    )
    assert kilde.kuttet is True
    assert kilde.kuttet_siden == NA.isoformat()
    assert sporing[BEREDER.effekt_sensor].kuttet_effekt_w == 1950.0
