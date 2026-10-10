"""Haandregnede tidsvinduer, sensurering og empirisk restvarighet."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from custom_components.effektvakt.lastprofil import (
    Effektpunkt,
    analyser_lastprofil,
    anslaa_restvarighet,
    oppsummer_vinduer,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def _tid(minutt):
    return START + timedelta(minutes=minutt)


def _profil(punkter, *, start=0, slutt=60, terskel=100, maks_hold=None):
    return analyser_lastprofil(
        [Effektpunkt(_tid(t), w) for t, w in punkter],
        start=_tid(start),
        slutt=_tid(slutt),
        terskel_w=terskel,
        maks_hold=maks_hold,
    )


def test_ujevne_samples_tidsvektes_i_stedet_for_aa_telles():
    profil = _profil([(0, 0), (10, 600), (11, 1200), (30, 0)])
    grunnlag = profil.tidsgrunnlag
    assert grunnlag.kjent_s == 3600
    assert grunnlag.aktiv_s == 1200
    assert grunnlag.kjent_wh == pytest.approx(390)
    assert grunnlag.aktiv_andel == pytest.approx(1 / 3)
    assert grunnlag.middel_w == pytest.approx(390)
    assert grunnlag.middel_aktiv_w == pytest.approx(1170)
    assert grunnlag.dekning == 1
    assert profil.hele_varigheter_s == (1200,)


def test_foerste_og_siste_aktive_periode_er_sensurert():
    profil = _profil([(0, 600), (10, 0), (20, 600), (30, 0), (40, 600)])
    assert [(p.venstre_sensurert, p.hoyre_sensurert) for p in profil.aktive_perioder] == [
        (True, False),
        (False, False),
        (False, True),
    ]
    assert profil.hele_varigheter_s == (600,)


def test_ukjent_bryter_syklus_og_teller_ikke_som_null():
    profil = _profil([(0, 0), (10, 600), (20, None), (30, 600), (40, 0)])
    grunnlag = profil.tidsgrunnlag
    assert grunnlag.dekning == pytest.approx(50 / 60)
    assert grunnlag.aktiv_andel == pytest.approx(20 / 50)
    assert grunnlag.kjent_wh == pytest.approx(200)
    assert not profil.hele_varigheter_s
    assert [(p.venstre_sensurert, p.hoyre_sensurert) for p in profil.aktive_perioder] == [
        (False, True),
        (True, False),
    ]


def test_sparse_recorder_tilstander_holdes_som_standard():
    profil = _profil([(0, 600)], slutt=120)
    assert profil.tidsgrunnlag.dekning == 1
    assert profil.tidsgrunnlag.kjent_wh == pytest.approx(1200)
    assert not profil.hele_varigheter_s
    periode = profil.aktive_perioder[0]
    assert periode.venstre_sensurert and periode.hoyre_sensurert


def test_valgfri_holdetid_gir_hull_og_regnes_fra_originalt_sample():
    profil = _profil([(-5, 600), (20, 0)], maks_hold=timedelta(minutes=10))
    assert profil.tidsgrunnlag.kjent_s == 15 * 60
    assert profil.tidsgrunnlag.aktiv_s == 5 * 60
    assert profil.tidsgrunnlag.kjent_wh == pytest.approx(50)
    assert not profil.hele_varigheter_s


@pytest.mark.parametrize("verdi", [None, -10, float("nan"), float("inf"), -float("inf")])
def test_ugyldig_effekt_er_ukjent(verdi):
    profil = _profil([(0, verdi), (30, 600)])
    assert profil.tidsgrunnlag.dekning == 0.5
    assert profil.tidsgrunnlag.aktiv_andel == 1
    assert profil.tidsgrunnlag.kjent_wh == 300
    assert not profil.hele_varigheter_s


def test_manglende_eller_sen_foerste_maaling_fyller_ikke_fortiden():
    tom = _profil([])
    assert tom.tidsgrunnlag.dekning == 0
    assert tom.tidsgrunnlag.aktiv_andel is None
    assert tom.tidsgrunnlag.middel_w is None
    assert tom.tidsgrunnlag.middel_aktiv_w is None
    sen = _profil([(30, 600)])
    assert sen.tidsgrunnlag.dekning == 0.5
    assert sen.tidsgrunnlag.kjent_wh == 300


def test_grenselik_effekt_er_ikke_aktiv_og_enheter_er_watt():
    profil = _profil([(0, 100), (30, 101)])
    assert profil.tidsgrunnlag.aktiv_s == 1800
    assert profil.tidsgrunnlag.kjent_wh == pytest.approx(100.5)
    assert profil.tidsgrunnlag.middel_aktiv_w == 101


def test_betinget_restvarighet_bruker_bare_sykluser_som_varte_lenge_nok():
    profil = _profil([(0, 0), (10, 600), (30, 0), (40, 600), (80, 0), (90, 600), (100, 0)], slutt=110)
    assert profil.hele_varigheter_s == (20 * 60, 40 * 60, 10 * 60)
    anslag = anslaa_restvarighet(profil, allerede_paa_s=15 * 60, minst_videre_s=10 * 60)
    assert anslag.stoette_antall == 2
    assert anslag.minst_saa_lenge_antall == 1
    assert anslag.sannsynlighet == 0.5
    assert anslag.datagrunnlag == "lavt"
    assert anslag.sensurerte_antall == 0
    tom = anslaa_restvarighet(profil, allerede_paa_s=41 * 60, minst_videre_s=60)
    assert tom.sannsynlighet is None
    assert tom.stoette_antall == 0
    assert tom.datagrunnlag == "ingen"


def test_lang_sensurert_periode_blir_ikke_en_kort_hel_syklus():
    profil = _profil([(0, 600), (30, 0), (40, 600), (41, 0), (50, 600)])
    anslag = anslaa_restvarighet(profil, allerede_paa_s=2 * 60, minst_videre_s=60)
    assert anslag.stoette_antall == 0
    assert anslag.sannsynlighet is None
    assert anslag.sensurerte_antall == 2


def test_stoerre_utvalg_er_beskrivende_ikke_garanti():
    punkter = [(i, 600 if i % 2 else 0) for i in range(42)]
    profil = _profil(punkter, slutt=43)
    anslag = anslaa_restvarighet(profil, allerede_paa_s=30, minst_videre_s=30)
    assert anslag.stoette_antall == 20
    assert anslag.sannsynlighet == 1
    assert anslag.datagrunnlag == "beskrivende"


def test_topptimer_klippes_og_ukjent_tid_svekker_dekningen():
    profil = _profil([(0, 0), (10, 600), (30, 0)])
    topp = oppsummer_vinduer(profil, [(_tid(15), _tid(35)), (_tid(55), _tid(65))])
    assert topp.varighet_s == 30 * 60
    assert topp.kjent_s == 25 * 60
    assert topp.aktiv_s == 15 * 60
    assert topp.kjent_wh == 150
    assert topp.dekning == pytest.approx(25 / 30)
    assert topp.aktiv_andel == pytest.approx(15 / 25)


def test_overlappende_vinduer_avvises_saa_energi_ikke_telles_dobbelt():
    profil = _profil([(0, 600)])
    with pytest.raises(ValueError, match="overlappe"):
        oppsummer_vinduer(profil, [(_tid(0), _tid(20)), (_tid(10), _tid(30))])


def test_ekskluderte_styringsvinduer_kan_overlappe_uten_dobbelt_tap_av_dekning():
    profil = analyser_lastprofil(
        [Effektpunkt(START, 600)],
        start=START,
        slutt=_tid(60),
        terskel_w=100,
        ekskluderte_vinduer=[(_tid(10), _tid(30)), (_tid(20), _tid(40)), (_tid(90), _tid(100))],
    )
    assert profil.tidsgrunnlag.dekning == 0.5
    assert profil.tidsgrunnlag.kjent_wh == 300
    assert not profil.hele_varigheter_s


def test_ekskludert_vindu_maa_ha_positiv_varighet():
    with pytest.raises(ValueError, match="Ekskluderte"):
        analyser_lastprofil([], start=START, slutt=_tid(60), terskel_w=100, ekskluderte_vinduer=[(_tid(10), _tid(5))])


def test_dst_bruker_faktisk_forloepte_sekunder():
    oslo = ZoneInfo("Europe/Oslo")
    start = datetime(2026, 3, 29, 1, tzinfo=oslo)
    slutt = datetime(2026, 3, 29, 4, tzinfo=oslo)
    profil = analyser_lastprofil([Effektpunkt(start, 1000)], start=start, slutt=slutt, terskel_w=100)
    assert profil.tidsgrunnlag.varighet_s == 2 * 3600
    assert profil.tidsgrunnlag.kjent_wh == 2000


@pytest.mark.parametrize("punkter", [[(10, 0), (0, 600)], [(0, 0), (0, 600)]])
def test_rekkefolge_og_duplikater_avvises(punkter):
    with pytest.raises(ValueError, match="kronologiske"):
        _profil(punkter)


@pytest.mark.parametrize("felt,verdi", [("terskel", -1), ("slutt", 0), ("maks_hold", timedelta(0))])
def test_ugyldige_analysegrenser_avvises(felt, verdi):
    with pytest.raises(ValueError):
        _profil([], **{felt: verdi})


def test_tidssone_er_paakrevd():
    with pytest.raises(ValueError, match="tidssone"):
        analyser_lastprofil([], start=START.replace(tzinfo=None), slutt=_tid(60), terskel_w=100)


@pytest.mark.parametrize(
    "felt,verdi", [("allerede_paa_s", -1), ("minst_videre_s", float("inf")), ("minste_stoette", 0)]
)
def test_ugyldige_restvarigheter_avvises(felt, verdi):
    valg = {"allerede_paa_s": 0, "minst_videre_s": 60, felt: verdi}
    with pytest.raises(ValueError):
        anslaa_restvarighet(_profil([]), **valg)


def test_cli_analyserer_lokal_fil_uten_aa_gjengi_entitetsnavn(tmp_path):
    fil = tmp_path / "last.json"
    fil.write_text(
        json.dumps(
            {
                "entity_id": "sensor.syntetisk_privat_last",
                "punkter": [{"tid": _tid(t).isoformat(), "watt": w} for t, w in [(0, 0), (10, 600), (30, 0)]],
                "vinduer": [[_tid(15).isoformat(), _tid(35).isoformat()]],
            }
        )
    )
    script = Path(__file__).resolve().parent.parent / "scripts" / "analyser_lastprofil.py"
    prosess = subprocess.run(
        [
            sys.executable,
            str(script),
            str(fil),
            "--start",
            START.isoformat(),
            "--slutt",
            _tid(60).isoformat(),
            "--terskel-w",
            "100",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    rapport = json.loads(prosess.stdout)
    assert rapport["tidsgrunnlag"]["kjent_wh"] == 200
    assert rapport["hele_varigheter_minutter"] == [20]
    assert rapport["restvarighet"]["datagrunnlag"] == "lavt"
    assert rapport["restvarighet"]["sannsynlighet"] == 1
    assert rapport["valgte_vinduer"]["aktiv_andel"] == 0.75
    assert "syntetisk_privat_last" not in prosess.stdout
