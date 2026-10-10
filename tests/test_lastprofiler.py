"""Samlet raadenergi skiller maaling, planlegging, alder og eget eierskap."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.effektvakt.laster import LastAvlesning, LastOppsett, compute_tilgjengelig_kutt_kw
from custom_components.effektvakt.lastprofil import Effektpunkt, analyser_lastprofil
from custom_components.effektvakt.lastprofiler import Lastprofiler

NOW = datetime(2026, 1, 2, 12, tzinfo=UTC)


def _historikk(*, slutt=None):
    start = slutt - timedelta(minutes=70) if slutt is not None else NOW - timedelta(days=1)
    return analyser_lastprofil(
        [Effektpunkt(start + timedelta(minutes=t), w) for t, w in [(0, 0), (10, 2000), (20, 0), (30, 2000), (60, 0)]],
        start=start,
        slutt=start + timedelta(minutes=70),
        terskel_w=100,
    )


def _auto():
    return LastOppsett("sensor.varme", profil="auto", terskel_w=100)


def _manuell(**kwargs):
    return LastOppsett("", navn="Gulv", profil="manuell", nominell_w=2300, arbeidssyklus_pct=15, **kwargs)


def _beregn(laster, *, teller=None, now=NOW, profiler=None, **kwargs):
    return (teller or Lastprofiler()).beregn(laster, now=now, resttid_s=1200, profiler=profiler or {}, **kwargs)


def test_manuell_last_uten_sensor_har_planleggingsenergi_men_ingen_raadenergi():
    last = _manuell()
    avlesninger = [LastAvlesning(last, None)]
    data = Lastprofiler().beregn(avlesninger, now=NOW, resttid_s=1800, profiler={})
    assert data["estimert_kuttenergi_resten_av_timen_kwh"] == pytest.approx(0.1725)
    assert data["profilraad_energi_kwh"] == 0
    kilde = data["lastprofiler"][last.noekkel]
    assert kilde["planleggingsestimat"]
    assert kilde["kilde"] == "manuell_duty"
    assert kilde["arbeidssyklus_pct"] == 15


def test_manuell_planlegging_er_ikke_maalt_null_kw():
    assert compute_tilgjengelig_kutt_kw([LastAvlesning(_manuell(), None)]) is None


def test_aktiv_ved_oppstart_har_ukjent_syklusalder():
    last = _auto()
    data = _beregn([LastAvlesning(last, 2000)], profiler={last.effekt_sensor: _historikk()})
    assert data["profilraad_energi_kwh"] == pytest.approx(0.375)
    assert data["lastprofiler"][last.noekkel]["kilde"] == "empirisk_ukjent_alder"


def test_wattendringer_mens_paa_nullstiller_ikke_alderen():
    last = _auto()
    teller = Lastprofiler()
    profiler = {last.effekt_sensor: _historikk()}
    _beregn([LastAvlesning(last, 0)], teller=teller, profiler=profiler)
    _beregn([LastAvlesning(last, 2000)], teller=teller, profiler=profiler, now=NOW + timedelta(minutes=1))
    data = _beregn([LastAvlesning(last, 2100)], teller=teller, profiler=profiler, now=NOW + timedelta(minutes=6))
    assert data["profilraad_energi_kwh"] == pytest.approx(2.1 * 12.5 / 60)
    assert data["lastprofiler"][last.noekkel]["kilde"] == "empirisk"
    assert data["lastprofiler"][last.noekkel]["forventet_drift_minutter"] == 12.5


def test_maalehull_fjerner_kjent_syklusalder():
    last = _auto()
    teller = Lastprofiler()
    profiler = {last.effekt_sensor: _historikk()}
    for minutt, watt in [(0, 0), (1, 2000), (2, None)]:
        _beregn([LastAvlesning(last, watt)], teller=teller, profiler=profiler, now=NOW + timedelta(minutes=minutt))
    data = _beregn([LastAvlesning(last, 2000)], teller=teller, profiler=profiler, now=NOW + timedelta(minutes=3))
    assert data["lastprofiler"][last.noekkel]["kilde"] == "empirisk_ukjent_alder"
    assert data["profilraad_energi_kwh"] == pytest.approx(0.375)


def test_eget_kutt_er_ikke_observert_naturlig_start_ved_restore():
    last = _auto()
    teller = Lastprofiler()
    profiler = {last.effekt_sensor: _historikk()}
    _beregn([LastAvlesning(last, 2000)], teller=teller, profiler=profiler)
    _beregn(
        [LastAvlesning(last, 0)],
        teller=teller,
        profiler=profiler,
        now=NOW + timedelta(minutes=1),
        egne_kutt={last.noekkel},
    )
    data = _beregn([LastAvlesning(last, 2000)], teller=teller, profiler=profiler, now=NOW + timedelta(minutes=2))
    assert data["lastprofiler"][last.noekkel]["kilde"] == "empirisk_ukjent_alder"


@pytest.mark.parametrize("felt", ["egne_kutt", "sperret"])
def test_eierskap_og_minste_paatid_hindrer_nytt_kutt(felt):
    last = _auto()
    data = _beregn([LastAvlesning(last, 2000)], profiler={last.effekt_sensor: _historikk()}, **{felt: {last.noekkel}})
    assert data["profilraad_energi_kwh"] == 0
    assert data["estimert_kuttenergi_resten_av_timen_kwh"] == 0


def test_aktiv_manuell_last_uten_paatid_faar_ikke_ubetinget_duty_som_restenergi():
    last = LastOppsett("sensor.gulv", profil="manuell", nominell_w=2300, arbeidssyklus_pct=15)
    data = _beregn([LastAvlesning(last, 2300)])
    assert data["estimert_kuttenergi_resten_av_timen_kwh"] is None
    assert data["profilraad_energi_kwh"] == 0
    assert data["profiler_ukjente"] == 1


def test_manglende_historikk_er_ukjent_ikke_antatt_fulltime():
    data = _beregn([LastAvlesning(_auto(), 2000)])
    assert data["estimert_kuttenergi_resten_av_timen_kwh"] is None
    assert data["profilraad_energi_kwh"] == 0


def test_sikkert_av_gir_null_ogsaa_uten_historikk():
    data = _beregn([LastAvlesning(_auto(), 0)])
    assert data["estimert_kuttenergi_resten_av_timen_kwh"] == 0
    assert data["profiler_ukjente"] == 0


def test_egen_aktivterskel_brukes_foer_estimater():
    last = LastOppsett("sensor.varme", profil="auto", terskel_w=500)
    data = _beregn([LastAvlesning(last, 200)], profiler={last.effekt_sensor: _historikk()})
    assert data["profilraad_energi_kwh"] == 0
    assert data["estimert_kuttenergi_resten_av_timen_kwh"] == 0


def test_ukjent_del_gjoer_summen_ukjent_men_kjent_del_kan_gi_raad():
    kjent = _auto()
    ukjent = LastOppsett("sensor.annen", profil="auto")
    data = _beregn(
        [LastAvlesning(kjent, 2000), LastAvlesning(ukjent, None)], profiler={kjent.effekt_sensor: _historikk()}
    )
    assert data["estimert_kuttenergi_resten_av_timen_kwh"] is None
    assert data["profiler_antall"] == 2
    assert data["profiler_ukjente"] == 1
    assert data["profilraad_energi_kwh"] == pytest.approx(0.375)


def test_eldre_laster_beholder_standardraad_uten_aa_utgi_seg_for_profil():
    data = _beregn([LastAvlesning(LastOppsett("sensor.gammel"), 2000)])
    assert data["profilraad_energi_kwh"] == pytest.approx(2 / 3)
    assert data["profiler_antall"] == 0
    assert data["laster_uten_profil"] == 1
    assert data["estimert_kuttenergi_resten_av_timen_kwh"] is None


def test_23_timer_gammel_profil_brukes_til_forventet_energi():
    last = _auto()
    oppdatert = NOW - timedelta(hours=23)
    profil = _historikk(slutt=oppdatert)
    data = _beregn(
        [LastAvlesning(last, 2000)],
        profiler={last.effekt_sensor: profil},
        oppdatert=oppdatert,
        status="historikk_feilet",
    )
    assert data["profilraad_energi_kwh"] == pytest.approx(0.375)
    assert data["estimert_kuttenergi_resten_av_timen_kwh"] == pytest.approx(0.375)
    kilde = data["lastprofiler"][last.noekkel]
    assert kilde["kilde"] == "empirisk_ukjent_alder"
    assert kilde["historikk_status"] == "historikk_feilet"
    assert kilde["oppdatert"] == oppdatert.isoformat()


def test_25_timer_gammel_profil_vises_men_gir_ikke_raad_eller_kjent_sensorsum():
    last = _auto()
    oppdatert = NOW - timedelta(hours=25)
    profil = _historikk(slutt=oppdatert)
    data = _beregn(
        [LastAvlesning(last, 2000)],
        profiler={last.effekt_sensor: profil},
        oppdatert=oppdatert,
        status="historikk_feilet",
    )
    assert data["profilraad_energi_kwh"] == 0
    assert data["estimert_kuttenergi_resten_av_timen_kwh"] is None
    assert data["profiler_ukjente"] == 1
    kilde = data["lastprofiler"][last.noekkel]
    assert kilde["historikk_status"] == "historikk_utdatert"
    assert kilde["kilde"] == "ukjent_varighet"
    assert kilde["estimert_kuttenergi_kwh"] is None
    assert kilde["periode_start"] == profil.intervaller[0].start.isoformat()
    assert kilde["periode_slutt"] == oppdatert.isoformat()
    assert kilde["hele_sykluser"] == 2
    assert kilde["aktiv_effekt_w"] == 2000
    assert kilde["dekning_pct"] == 100


def test_flere_laster_summerer_forventet_energi_men_ikke_planlegging_eller_sperrede_laster():
    auto = _auto()
    uten_profil = LastOppsett("sensor.annen", terskel_w=100)
    sperret = LastOppsett("sensor.sperret", terskel_w=100)
    data = _beregn(
        [
            LastAvlesning(auto, 2000),
            LastAvlesning(uten_profil, 600),
            LastAvlesning(sperret, 1000),
            LastAvlesning(_manuell(), None),
        ],
        profiler={auto.effekt_sensor: _historikk()},
        sperret={sperret.noekkel},
    )
    # 0.375 kWh forventet aktivsyklus + 0.6 kW i 1/3 time =0.575 kWh.
    assert data["profilraad_energi_kwh"] == pytest.approx(0.575)
    # Ved 40 minutter er samme energimengde 1.725 kW resten av timen.
    ekvivalent_kw = data["profilraad_energi_kwh"] / (1 - 40 / 60)
    assert ekvivalent_kw == pytest.approx(1.725)
    assert ekvivalent_kw * (1 - 40 / 60) == pytest.approx(0.575)
