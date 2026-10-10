"""Forventet restenergi, betinget drift og skillet mellom maaling og plan."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.effektvakt.lastprofil import Effektpunkt, analyser_lastprofil
from custom_components.effektvakt.profilestimat import beregn_kuttenergi

START = datetime(2026, 1, 1, tzinfo=UTC)


def _profil(*, ekskluderte=None):
    # To hele sykluser paa 10 og 30 min. Begge omkranses av kjent avtilstand.
    return analyser_lastprofil(
        [Effektpunkt(START + timedelta(minutes=t), w) for t, w in [(0, 0), (10, 2000), (20, 0), (30, 2000), (60, 0)]],
        start=START,
        slutt=START + timedelta(minutes=70),
        terskel_w=100,
        ekskluderte_vinduer=ekskluderte,
    )


def test_kjent_alder_integrerer_resterende_tid_ikke_bare_sluttsannsynlighet():
    # Etter 5 min har syklusene 5 og 25 min igjen; innen 20 min er snittet12.5.
    estimat = beregn_kuttenergi(maalt_w=2000, profil=_profil(), allerede_paa_s=300, resttid_s=1200)
    assert estimat.forventet_drift_s == 750
    assert estimat.kwh == pytest.approx(2 * 12.5 / 60)
    assert estimat.stoette_antall == 2
    assert estimat.sensurerte_antall == 0
    assert estimat.kilde == "empirisk"
    assert estimat.datagrunnlag == "lavt"
    assert not estimat.planleggingsestimat


def test_bare_sykluser_som_varte_til_observert_alder_teller():
    estimat = beregn_kuttenergi(maalt_w=2000, profil=_profil(), allerede_paa_s=1200, resttid_s=1200)
    assert estimat.stoette_antall == 1
    assert estimat.forventet_drift_s == 600
    assert estimat.kwh == pytest.approx(1 / 3)


def test_ukjent_alder_tidsvekter_sykluser_og_fase():
    # 10-minsyklus bidrar50 min², 30-minsyklus400 min²; delt paa40 min=>11.25min.
    estimat = beregn_kuttenergi(maalt_w=2000, profil=_profil(), resttid_s=1200)
    assert estimat.forventet_drift_s == 675
    assert estimat.kwh == pytest.approx(0.375)
    assert estimat.kilde == "empirisk_ukjent_alder"
    assert estimat.datagrunnlag == "lavt"


def test_maksimal_avtid_begrenser_hver_syklus_foer_gjennomsnittet():
    estimat = beregn_kuttenergi(maalt_w=2000, profil=_profil(), allerede_paa_s=300, resttid_s=3600, maks_kutt_s=600)
    assert estimat.vindu_s == 600
    assert estimat.forventet_drift_s == 450
    assert estimat.kwh == pytest.approx(0.25)


def test_manuel_gulvvarme_2300_w_15_prosent_er_planleggingsestimat():
    estimat = beregn_kuttenergi(maalt_w=None, nominell_w=2300, duty=0.15, resttid_s=1800)
    assert estimat.kwh == pytest.approx(0.1725)
    assert estimat.forventet_drift_s == 270
    assert estimat.kilde == "manuell_duty"
    assert estimat.datagrunnlag == "manuelt"
    assert estimat.planleggingsestimat


def test_maalt_av_overstyrer_manuell_antakelse_om_drift():
    estimat = beregn_kuttenergi(maalt_w=0, nominell_w=2300, duty=0.15, resttid_s=3600)
    assert estimat.kwh == 0
    assert estimat.kilde == "maalt_av"
    assert not estimat.planleggingsestimat


def test_standby_under_profilterskelen_er_ikke_aktiv_varming():
    estimat = beregn_kuttenergi(maalt_w=5, profil=_profil(), resttid_s=3600)
    assert estimat.kwh == 0
    assert estimat.kilde == "maalt_av"


def test_egen_kuttet_last_er_ikke_nytt_tilgjengelig_kutt():
    estimat = beregn_kuttenergi(maalt_w=None, nominell_w=2300, duty=0.15, resttid_s=3600, egen_kuttet=True)
    assert estimat.kwh == 0
    assert estimat.kilde == "egen_kuttet"
    assert not estimat.planleggingsestimat


def test_maalt_aktiv_ganges_ikke_med_ubetinget_duty():
    estimat = beregn_kuttenergi(maalt_w=2300, nominell_w=2300, duty=0.15, resttid_s=3600)
    assert estimat.kwh is None
    assert estimat.forventet_drift_s is None
    assert estimat.kilde == "ukjent_varighet"


def test_manuell_paatid_bruker_maalt_effekt_og_kjent_alder():
    estimat = beregn_kuttenergi(
        maalt_w=2100, nominell_w=2300, duty=0.15, typisk_paa_minutter=20, allerede_paa_s=300, resttid_s=3600
    )
    assert estimat.kwh == pytest.approx(0.525)
    assert estimat.forventet_drift_s == 900
    assert estimat.kilde == "manuell_paatid"


def test_manuell_paatid_med_ukjent_alder_bruker_tilfeldig_fase():
    estimat = beregn_kuttenergi(maalt_w=2000, typisk_paa_minutter=20, resttid_s=3600)
    assert estimat.forventet_drift_s == 600
    assert estimat.kwh == pytest.approx(1 / 3)
    assert estimat.kilde == "manuell_paatid_ukjent_alder"


def test_allerede_lengre_enn_typisk_paatid_er_ukjent_ikke_sikkert_slutt():
    estimat = beregn_kuttenergi(maalt_w=2000, typisk_paa_minutter=20, allerede_paa_s=1800, resttid_s=3600)
    assert estimat.kwh is None
    assert estimat.kilde == "ukjent_varighet"


def test_historisk_duty_uten_live_maaling_er_bare_planlegging():
    estimat = beregn_kuttenergi(maalt_w=None, profil=_profil(), resttid_s=3600)
    assert estimat.kwh == pytest.approx(2 * 40 / 70)
    assert estimat.kilde == "historisk_duty"
    assert estimat.planleggingsestimat


def test_historisk_bare_av_gir_null_men_ingen_maaledekning_er_ukjent():
    args = {"start": START, "slutt": START + timedelta(hours=1), "terskel_w": 100}
    av = analyser_lastprofil([Effektpunkt(START, 0)], **args)
    ukjent = analyser_lastprofil([], **args)
    assert beregn_kuttenergi(maalt_w=None, profil=av, resttid_s=3600).kwh == 0
    assert beregn_kuttenergi(maalt_w=None, profil=ukjent, resttid_s=3600).kwh is None


def test_sensurerte_og_styrte_sykluser_brukes_ikke_som_naturlig_paatid():
    profil = _profil(ekskluderte=[(START + timedelta(minutes=15), START + timedelta(minutes=17))])
    assert profil.hele_varigheter_s == (1800,)
    estimat = beregn_kuttenergi(maalt_w=2000, profil=profil, allerede_paa_s=300, resttid_s=3600)
    assert estimat.stoette_antall == 1
    assert estimat.sensurerte_antall == 2
    assert estimat.forventet_drift_s == 1500
    assert estimat.kwh == pytest.approx(5 / 6)


def test_for_lang_observert_alder_har_ikke_historisk_stoette():
    estimat = beregn_kuttenergi(maalt_w=2000, profil=_profil(), allerede_paa_s=3600, resttid_s=3600)
    assert estimat.kwh is None
    assert estimat.stoette_antall == 0


@pytest.mark.parametrize("maalt", [None, float("nan"), float("inf"), -1])
def test_ukjent_maaling_uten_profil_er_ukjent(maalt):
    estimat = beregn_kuttenergi(maalt_w=maalt, resttid_s=3600)
    assert estimat.kwh is None
    assert estimat.kilde == "ukjent"


@pytest.mark.parametrize("begrensning", [{"resttid_s": 0}, {"resttid_s": 3600, "maks_kutt_s": 0}])
def test_ingen_tilgjengelig_tid_gir_null(begrensning):
    assert beregn_kuttenergi(maalt_w=None, **begrensning).kwh == 0


@pytest.mark.parametrize(
    "felt,verdi",
    [
        ("resttid_s", -1),
        ("maks_kutt_s", float("inf")),
        ("allerede_paa_s", -1),
        ("duty", 15),
        ("duty", -0.1),
        ("duty", float("nan")),
        ("nominell_w", 0),
        ("typisk_paa_minutter", 0),
    ],
)
def test_ugyldige_forutsetninger_avvises(felt, verdi):
    with pytest.raises(ValueError):
        beregn_kuttenergi(**{"maalt_w": None, "resttid_s": 3600, felt: verdi})
