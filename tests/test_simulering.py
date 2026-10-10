"""Energibevaring, kausalitet og grenser for den antatte fleksible lasten."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from custom_components.effektvakt.dso import KAPASITETSTRINN_PER_DSO
from custom_components.effektvakt.simulering import Simuleringstime, Simuleringsvalg, simuler

TRINN = KAPASITETSTRINN_PER_DSO["bkk"]["kapasitetstrinn"]
OSLO = ZoneInfo("Europe/Oslo")
REPO = Path(__file__).resolve().parent.parent


def _timer(verdier, start=None):
    start = start or datetime(2026, 2, 1, tzinfo=OSLO)
    return [
        Simuleringstime((start.astimezone(UTC) + timedelta(hours=i)).astimezone(OSLO), verdi)
        for i, verdi in enumerate(verdier)
    ]


def _simuler(verdier, strategi="maal", start=None, **valg):
    return simuler(
        _timer(verdier, start),
        trinn=TRINN,
        strategi=strategi,
        valg=Simuleringsvalg(kutt_kw=1.0, tilbakefoering_kw=1.0, **valg),
    )


def _energi_bevart(resultat):
    for time in resultat.timer:
        if time.opprinnelig_kwh is not None:
            assert time.styrt_kwh >= 0
            assert time.styrt_kwh == pytest.approx(time.opprinnelig_kwh - time.utsatt_kwh + time.tilbakefoert_kwh)
    assert sum(t.styrt_kwh or 0 for t in resultat.timer) + resultat.restgjeld_kwh == pytest.approx(
        sum(t.opprinnelig_kwh or 0 for t in resultat.timer)
    )


def test_maanedsmaal_bevarer_fem_kw_foer_dagene_laases():
    verdier = [6.0 if i % 24 == 12 else 1.0 for i in range(72)]
    reaktiv = _simuler(verdier, strategi="reaktiv")
    maal = _simuler(verdier)
    assert max(t.styrt_kwh for t in reaktiv.timer) == pytest.approx(6)
    assert max(t.styrt_kwh for t in maal.timer) == pytest.approx(5)
    assert sum(t.utsatt_kwh for t in maal.timer) == pytest.approx(3)
    assert maal.restgjeld_kwh == 0
    assert not maal.ugyldige_maaneder
    _energi_bevart(reaktiv)
    _energi_bevart(maal)


def test_tilbakefoering_kan_lage_en_stoerre_topp():
    resultat = _simuler([6, 5.5, 1])
    assert resultat.timer[0].styrt_kwh == pytest.approx(5)
    assert resultat.timer[1].styrt_kwh == pytest.approx(6.5)
    assert resultat.timer[1].tilbakefoert_kwh == pytest.approx(1)
    assert resultat.restgjeld_kwh == 0
    _energi_bevart(resultat)


def test_kort_avtid_flytter_forbruk_innen_samme_time():
    resultat = _simuler([6, 1], maks_av_minutter=15)
    assert resultat.timer[0].styrt_kwh == pytest.approx(6)
    assert resultat.timer[0].kutt_minutter == 30
    assert resultat.timer[0].utsatt_kwh == pytest.approx(0.5)
    _energi_bevart(resultat)


def test_komfortfrist_reserverer_tid_til_tilbakefoering():
    resultat = _simuler([6, 1], komfortfrist_minutter=30)
    assert resultat.timer[0].styrt_kwh == pytest.approx(6)
    assert resultat.timer[0].gjeld_kwh == 0
    assert resultat.fristbrudd == 0
    _energi_bevart(resultat)


def test_minste_paatid_hindrer_nytt_kutt_etter_betalt_gjeld():
    resultat = _simuler([6, 6, 6, 1], minste_paa_minutter=120)
    assert resultat.timer[0].kutt_minutter == 60
    assert resultat.timer[1].kutt_minutter == 0
    assert resultat.timer[2].kutt_minutter == 0
    _energi_bevart(resultat)


def test_gjeld_overlever_maanedsskiftet_og_mangler_ved_slutten_er_ikke_sparing():
    start = datetime(2026, 1, 31, 23, tzinfo=OSLO)
    kort = _simuler([6], start=start)
    full = _simuler([6, 1], start=start)
    assert kort.restgjeld_kwh == pytest.approx(1)
    assert kort.ugyldige_maaneder == {"2026-01"}
    assert full.timer[1].tilbakefoert_kwh == pytest.approx(1)
    assert not full.ugyldige_maaneder
    _energi_bevart(kort)
    _energi_bevart(full)


def test_maalehull_er_ikke_null_eller_tilbakefoering():
    resultat = _simuler([6, None, 1])
    assert resultat.timer[1].styrt_kwh is None
    assert resultat.timer[1].gjeld_kwh == pytest.approx(1)
    assert resultat.timer[2].tilbakefoert_kwh == pytest.approx(1)
    assert resultat.fristbrudd == 1
    assert resultat.ugyldige_maaneder == {"2026-02"}
    _energi_bevart(resultat)


def test_framtidige_timer_endrer_ikke_tidligere_beslutninger():
    kort = _simuler([6, 1])
    senere_topp = _simuler([6, 1, 30])
    senere_ro = _simuler([6, 1, 0])
    assert kort.timer == senere_topp.timer[:2] == senere_ro.timer[:2]


@pytest.mark.parametrize("start", [datetime(2026, 3, 29, tzinfo=OSLO), datetime(2026, 10, 25, tzinfo=OSLO)])
def test_sommertid_bevarer_fysiske_timer_og_energi(start):
    resultat = _simuler([6, 1, 6, 1, 0], start=start)
    assert len(resultat.timer) == 5
    _energi_bevart(resultat)


@pytest.mark.parametrize("verdi", [-1, float("inf"), float("nan")])
def test_ugyldig_energi_avvises(verdi):
    with pytest.raises(ValueError, match="Energi"):
        _simuler([verdi])


@pytest.mark.parametrize(
    "felt,verdi", [("kutt_kw", 0), ("tilbakefoering_kw", -1), ("tick_minutter", 7), ("tick_minutter", 10)]
)
def test_ugyldige_lastforutsetninger_avvises(felt, verdi):
    valg = {"kutt_kw": 1, "tilbakefoering_kw": 1, felt: verdi}
    with pytest.raises(ValueError):
        Simuleringsvalg(**valg)


def test_manglende_timer_maa_vaere_eksplisitte():
    timer = _timer([1, 2, 3])
    with pytest.raises(ValueError, match="sammenhengende"):
        simuler([timer[0], timer[2]], trinn=TRINN, strategi="maal", valg=Simuleringsvalg(1, 1))


def test_timeskiftet_maa_vaere_eksplisitt():
    with pytest.raises(ValueError, match="timeskiftet"):
        _simuler([1], start=datetime(2026, 2, 1, 0, 30, tzinfo=OSLO))


def test_cli_skiller_ideal_fra_scenario_og_utelater_januar():
    prosess = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "simuler_sparing.py")],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    rapport = json.loads(prosess.stdout)
    assert len(rapport["scenarioer"]) == 4
    for scenario in rapport["scenarioer"]:
        assert len(scenario["maaneder"]) == 9
        januar = next(m for m in scenario["maaneder"] if m["maaned"] == "2026-01")
        assert januar["manglende_timer"] == 105
        assert januar["kapasitetsbesparelse_scenario_kr"] is None
        assert januar["kapasitetsbesparelse_ideal_kr"] is None
        assert all(
            m["kapasitetsbesparelse_scenario_kr"] is not None for m in scenario["maaneder"] if m["maaned"] != "2026-01"
        )
        assert scenario["styrt_kwh"] + scenario["restgjeld_kwh"] == pytest.approx(scenario["opprinnelig_kwh"])
        assert scenario["sum_ideal_kr"] == (330 if scenario["kutt_kw"] == 1 else 0)
        assert scenario["sum_scenario_kr"] == sum(
            m["kapasitetsbesparelse_scenario_kr"] or 0 for m in scenario["maaneder"]
        )
