"""Målehull og faktiske timer over begge norske sommertidsskifter."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from custom_components.effektvakt.avlesning import read_power_kw
from custom_components.effektvakt.binary_sensor import EffektvaktKuttNedAnbefaltBinarySensor
from custom_components.effektvakt.const import RISIKO_GOD_MARGIN, RISIKO_LIKE_UNDER, RISIKO_OVER_TERSKEL
from custom_components.effektvakt.coordinator import EffektvaktCoordinator, is_coordinator_stale
from custom_components.effektvakt.hysterese import HystereseState, apply_hysteresis
from custom_components.effektvakt.timeregnskap import Timeregnskap, integrer_effekt, tidsandeler, timer_mellom
from tests.conftest import make_entry, make_hass_with_states, make_state

OSLO = ZoneInfo("Europe/Oslo")
NOW_PATH = "custom_components.effektvakt.coordinator.dt_util_now"


def lokal(iso):
    return datetime.fromisoformat(iso).astimezone(OSLO)


SKIFTER = [
    (lokal("2026-03-29T01:59:30+01:00"), lokal("2026-03-29T03:00:30+02:00")),
    (lokal("2026-10-25T02:59:30+02:00"), lokal("2026-10-25T02:00:30+01:00")),
]


@pytest.mark.parametrize("fra,til", SKIFTER)
def test_effektintegrasjon_deler_en_faktisk_minutt_paa_to_timer(fra, til):
    skifte = til.replace(minute=0, second=0)
    assert timer_mellom(fra, til) == pytest.approx(1 / 60)
    energi = integrer_effekt(forrige_ts=fra, forrige_kw=6, na=til, na_kw=6, timeskifte=skifte)
    assert energi.foer_timeskiftet_kwh == pytest.approx(0.05)
    assert energi.etter_timeskiftet_kwh == pytest.approx(0.05)


@pytest.mark.parametrize("fra,til", SKIFTER)
def test_maalerens_time_havner_paa_forrige_faktiske_time(fra, til):
    start = fra.replace(minute=0, second=0)
    slutt = til.replace(minute=0, second=0)
    andeler = tidsandeler(fra=start, til=slutt, time_start=slutt, forrige_time_start=start)
    assert andeler.forrige_time == pytest.approx(1)
    assert andeler.denne_timen == pytest.approx(0)
    regnskap = Timeregnskap(current_month=start.strftime("%Y-%m"))
    regnskap.akkumuler(now=start, power_kw=0)
    regnskap.avstem_mot_maaler(energy_now=100, now=start, maaler_ts_raa=start)
    regnskap.akkumuler(now=slutt, power_kw=0)
    regnskap.avstem_mot_maaler(energy_now=106, now=slutt, maaler_ts_raa=slutt)
    assert regnskap.daily_max_kw[start.date()] == pytest.approx(6)
    assert regnskap.current_hour_kwh == 0


@pytest.mark.parametrize("fra,til", SKIFTER)
@pytest.mark.parametrize("restart", [False, True])
def test_regnskap_og_kort_restart_bevarer_halvminuttene(fra, til, restart):
    regnskap = Timeregnskap(current_month=fra.strftime("%Y-%m"))
    regnskap.akkumuler(now=fra, power_kw=6)
    if restart:
        regnskap = Timeregnskap.fra_lagring(regnskap.til_lagring(), now=til)
    regnskap.akkumuler(now=til, power_kw=6)
    assert regnskap.ventende_time.kwh == pytest.approx(0.05)
    assert regnskap.current_hour_kwh == pytest.approx(0.05)
    assert regnskap.current_hour_start.utcoffset() == til.utcoffset()
    assert regnskap.current_month == til.strftime("%Y-%m")


@pytest.mark.parametrize("fra,til", SKIFTER)
def test_watchdog_bruker_varighet_ikke_lokal_klokke(fra, til):
    assert not is_coordinator_stale(last_successful_update=fra, now=til)
    assert is_coordinator_stale(
        last_successful_update=fra, now=lokal((til.astimezone(ZoneInfo("UTC")) + timedelta(minutes=2)).isoformat())
    )


@pytest.mark.parametrize("fra,til", SKIFTER)
def test_hysterese_tar_ett_trinn_etter_faktisk_holdetid(fra, til):
    state = HystereseState(nivå=RISIKO_OVER_TERSKEL)
    apply_hysteresis(state, rå_nivå=RISIKO_GOD_MARGIN, now=fra, holdetid=timedelta(minutes=2))
    apply_hysteresis(state, rå_nivå=RISIKO_GOD_MARGIN, now=til, holdetid=timedelta(minutes=2))
    assert state.nivå == RISIKO_OVER_TERSKEL
    senere = lokal((til.astimezone(ZoneInfo("UTC")) + timedelta(minutes=1)).isoformat())
    apply_hysteresis(state, rå_nivå=RISIKO_GOD_MARGIN, now=senere, holdetid=timedelta(minutes=2))
    assert state.nivå == RISIKO_LIKE_UNDER


def coordinator(states):
    with patch("custom_components.effektvakt.coordinator.Store"):
        coord = EffektvaktCoordinator(make_hass_with_states(states), make_entry())
    coord._store = MagicMock()
    coord._store.async_load = AsyncMock(return_value=None)
    coord._store.async_save = AsyncMock()
    return coord


@pytest.mark.parametrize("verdi", ["unavailable", "unknown", "NaN", "inf", "ugyldig"])
@pytest.mark.asyncio
async def test_ugyldig_effekt_gir_ukjente_raad_og_bevarer_maalt_energi(verdi):
    now = lokal("2026-10-09T14:30:00+02:00")
    states = {"sensor.power": make_state("6000", unit="W")}
    coord = coordinator(states)
    with patch(NOW_PATH, return_value=now):
        await coord._async_update_data()
    with patch(NOW_PATH, return_value=now + timedelta(minutes=1)):
        kjent = await coord._async_update_data()
    assert kjent["actual_kwh_this_hour"] == pytest.approx(0.1)
    states["sensor.power"] = make_state(verdi, unit="W")
    with patch(NOW_PATH, return_value=now + timedelta(minutes=2)):
        data = await coord._async_update_data()
    coord.data = data
    assert data["actual_kwh_this_hour"] == pytest.approx(0.1)
    assert not data["maalegrunnlag_gyldig"]
    for key in (
        "current_kw",
        "projected_avg_kw",
        "margin_kw",
        "kan_legge_paa_resten_av_timen_kw",
        "risiko_niva",
        "kostnad_denne_timen_kr",
    ):
        assert data[key] is None
    assert EffektvaktKuttNedAnbefaltBinarySensor(coord).is_on is None
    assert not is_coordinator_stale(
        last_successful_update=coord._last_successful_update, now=now + timedelta(minutes=2)
    )
    states["sensor.power"] = make_state("6000", unit="W")
    with patch(NOW_PATH, return_value=now + timedelta(minutes=3)):
        frisk = await coord._async_update_data()
    assert frisk["maalegrunnlag_gyldig"]
    # Ingen integrasjon over vinduet uten kjent effekt.
    assert frisk["actual_kwh_this_hour"] == pytest.approx(0.1)


@pytest.mark.parametrize("alder,gyldig", [(0, True), (120, True), (121, False), (-1, False)])
@pytest.mark.parametrize("felt", ["last_reported", "last_updated"])
def test_rapportpuls_er_fersk_selv_om_verdi_ikke_endrer_seg(alder, gyldig, felt):
    now = lokal("2026-10-09T14:30:00+02:00")
    state = make_state("0", unit="W", last_changed=now - timedelta(days=1))
    setattr(state, felt, now - timedelta(seconds=alder))
    hass = make_hass_with_states({"sensor.power": state})
    assert (read_power_kw(hass, "sensor.power", now=now) == 0) is gyldig


@pytest.mark.asyncio
async def test_frosset_tall_er_ukjent_men_ny_rapport_med_samme_tall_er_gyldig():
    now = lokal("2026-10-09T14:30:00+02:00")
    state = make_state("500", unit="W", last_changed=now - timedelta(days=1))
    state.last_reported = now - timedelta(seconds=121)
    coord = coordinator({"sensor.power": state})
    with patch(NOW_PATH, return_value=now):
        ukjent = await coord._async_update_data()
        state.last_reported = now
        frisk = await coord._async_update_data()
    assert ukjent["projected_avg_kw"] is None
    assert ukjent["kan_legge_paa_kw"] is None
    assert frisk["current_kw"] == 0.5
    assert frisk["maalegrunnlag_gyldig"]
