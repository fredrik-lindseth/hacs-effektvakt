"""Tester for at time-akkumulatoren overlever en omstart.

Feilen disse dekker: lagret current_hour_kwh og energy_at_hour_start ble lest
inn ved oppstart og kastet igjen to linjer senere, fordi ingen visste hvilken
time de hørte til. Resten av timen talte integrasjonen bare fra omstarten, og
projisert time-snitt ble for lavt. For lavt gir ingen risiko, ingen varsel og
ingen kutt, så retningen på feilen er den farlige.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.effektvakt.coordinator import (
    EffektvaktCoordinator,
    apply_energy_reading,
    hour_state_is_current,
)
from tests.conftest import make_entry, make_hass_with_states, make_state

NOW_PATH = "custom_components.effektvakt.coordinator.dt_util_now"

CET = timezone(timedelta(hours=1))
CEST = timezone(timedelta(hours=2))


def _states(*, power_w: str = "500", energy_kwh: str | None = "100.0"):
    states: dict[str, object] = {"sensor.power": make_state(power_w, unit="W")}
    if energy_kwh is not None:
        states["sensor.energy"] = make_state(energy_kwh, unit="kWh")
    return states


def _make_coordinator(now: datetime, *, stored: dict | None = None) -> EffektvaktCoordinator:
    """Coordinator som om HA nettopp startet, med det gitte innholdet i Store."""
    with (
        patch("custom_components.effektvakt.coordinator.Store"),
        patch(NOW_PATH, return_value=now),
    ):
        coord = EffektvaktCoordinator(make_hass_with_states({}), make_entry())
    coord._store = MagicMock()
    coord._store.async_load = AsyncMock(return_value=stored)
    coord._store.async_save = AsyncMock()
    return coord


async def _tick(coord: EffektvaktCoordinator, now: datetime, states: dict) -> dict:
    coord.hass = make_hass_with_states(states)
    with patch(NOW_PATH, return_value=now):
        return await coord._async_update_data()


def _lagret(coord: EffektvaktCoordinator) -> dict:
    """Siste payload coordinatoren skrev til Store, altså det en omstart leser."""
    return coord._store.async_save.call_args[0][0]


def _lagret_time(
    *,
    hour_start: str | None = "2026-05-25T14:00:00",
    kwh: float = 2.5,
    energy_at_hour_start: float | None = 100.0,
    daily_max: dict[str, float] | None = None,
    current_month: str = "2026-05",
) -> dict:
    """Håndskrevet Store-innhold, for tilstand som er eldre enn testen selv."""
    return {
        "data": {
            "current_month": current_month,
            "daily_max_kw": daily_max or {},
            "current_hour_kwh": kwh,
            "current_hour_start": hour_start,
            "energy_at_hour_start": energy_at_hour_start,
        }
    }


async def _kjor_en_time_til_1445() -> EffektvaktCoordinator:
    """En coordinator som har talt 2,5 kWh i timen 14, og lagret det."""
    coord = _make_coordinator(datetime(2026, 5, 25, 14, 30))
    await _tick(coord, datetime(2026, 5, 25, 14, 30), _states(energy_kwh="100.0"))
    await _tick(coord, datetime(2026, 5, 25, 14, 45), _states(energy_kwh="102.5"))
    assert coord._current_hour_kwh == pytest.approx(2.5)
    return coord


@pytest.mark.asyncio
async def test_timen_lagres_med_tidspunktet_sitt():
    coord = await _kjor_en_time_til_1445()
    data = _lagret(coord)["data"]
    assert data["current_hour_start"] == "2026-05-25T14:00:00"
    assert data["current_hour_kwh"] == pytest.approx(2.5)
    assert data["energy_at_hour_start"] == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_omstart_midt_i_timen_fortsetter_der_den_slapp():
    """Omstart 14:50 skal ikke sette actual_kwh_this_hour tilbake til null."""
    forrige = await _kjor_en_time_til_1445()

    coord = _make_coordinator(datetime(2026, 5, 25, 14, 50), stored=_lagret(forrige))
    data = await _tick(coord, datetime(2026, 5, 25, 14, 50), _states(energy_kwh="103.0"))

    assert data["actual_kwh_this_hour"] == pytest.approx(3.0)
    assert coord._energy_at_hour_start == pytest.approx(100.0)
    # 3,0 kWh brukt pluss 0,5 kW i de ti minuttene som står igjen.
    assert data["projected_avg_kw"] == pytest.approx(3.083, abs=0.001)


@pytest.mark.asyncio
async def test_omstart_midt_i_timen_mister_ikke_timen_om_maaleren_star_stille():
    """Ingen forbruk mellom siste tick og omstarten er ikke det samme som ingen time."""
    forrige = await _kjor_en_time_til_1445()

    coord = _make_coordinator(datetime(2026, 5, 25, 14, 50), stored=_lagret(forrige))
    data = await _tick(coord, datetime(2026, 5, 25, 14, 50), _states(energy_kwh="102.5"))

    assert data["actual_kwh_this_hour"] == pytest.approx(2.5)


@pytest.mark.asyncio
async def test_omstart_etter_timeskifte_laaser_inn_den_gamle_timen():
    forrige = await _kjor_en_time_til_1445()

    coord = _make_coordinator(datetime(2026, 5, 25, 15, 5), stored=_lagret(forrige))
    data = await _tick(coord, datetime(2026, 5, 25, 15, 5), _states(energy_kwh="103.0"))

    assert data["actual_kwh_this_hour"] == 0.0
    assert coord._energy_at_hour_start == pytest.approx(103.0)
    assert coord._daily_max_kw[date(2026, 5, 25)] == pytest.approx(2.5)


@pytest.mark.asyncio
async def test_timen_kan_ikke_telles_to_ganger_i_daily_max():
    """To omstarter over det samme timeskiftet skal gi den samme dagsverdien.

    Kræsjer HA igjen før den rakk å lagre, leses den samme timen inn på nytt.
    _finalize_hour setter dagsverdien med max, så den kan bare gjentas.
    """
    forrige = await _kjor_en_time_til_1445()
    payload = _lagret(forrige)

    forste = _make_coordinator(datetime(2026, 5, 25, 15, 5), stored=payload)
    await _tick(forste, datetime(2026, 5, 25, 15, 5), _states(energy_kwh="103.0"))

    andre = _make_coordinator(datetime(2026, 5, 25, 15, 10), stored=payload)
    await _tick(andre, datetime(2026, 5, 25, 15, 10), _states(energy_kwh="103.4"))

    assert andre._daily_max_kw[date(2026, 5, 25)] == pytest.approx(2.5)

    # Og en omstart etter at timen er låst inn rører den heller ikke.
    tredje = _make_coordinator(datetime(2026, 5, 25, 15, 20), stored=_lagret(forste))
    await _tick(tredje, datetime(2026, 5, 25, 15, 20), _states(energy_kwh="103.8"))
    assert tredje._daily_max_kw[date(2026, 5, 25)] == pytest.approx(2.5)
    assert tredje._current_hour_kwh == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_omstart_etter_lang_nedetid_forkaster_timen():
    """Tre døgn nede, og klokka er tilfeldigvis 14 igjen. Timen er ikke vår."""
    stored = _lagret_time(hour_start="2026-05-22T14:00:00", kwh=2.5, energy_at_hour_start=100.0)

    coord = _make_coordinator(datetime(2026, 5, 25, 14, 10), stored=stored)
    data = await _tick(coord, datetime(2026, 5, 25, 14, 10), _states(energy_kwh="130.0"))

    assert data["actual_kwh_this_hour"] == 0.0
    assert coord._energy_at_hour_start == pytest.approx(130.0)
    # Timen som faktisk ble målt hører hjemme på sin egen dag, ikke på i dag.
    assert coord._daily_max_kw[date(2026, 5, 22)] == pytest.approx(2.5)
    assert date(2026, 5, 25) not in coord._daily_max_kw


@pytest.mark.asyncio
async def test_lagret_time_uten_tidspunkt_forkastes():
    """Store skrevet av en versjon som ikke lagret timen. Da vet vi ingenting."""
    stored = _lagret_time(hour_start=None, kwh=2.5, energy_at_hour_start=100.0)

    coord = _make_coordinator(datetime(2026, 5, 25, 14, 10), stored=stored)
    data = await _tick(coord, datetime(2026, 5, 25, 14, 10), _states(energy_kwh="102.5"))

    assert data["actual_kwh_this_hour"] == 0.0
    assert coord._daily_max_kw == {}


@pytest.mark.asyncio
async def test_maaler_nullstilt_under_nedetid_gir_ikke_negativ_kwh():
    """Måleren står på 0,4 kWh der den sto på 102,5. Den er byttet eller nullstilt."""
    stored = _lagret_time(kwh=2.5, energy_at_hour_start=100.0)

    coord = _make_coordinator(datetime(2026, 5, 25, 14, 50), stored=stored)
    data = await _tick(coord, datetime(2026, 5, 25, 14, 50), _states(energy_kwh="0.4"))

    assert data["actual_kwh_this_hour"] == pytest.approx(2.5)

    # Og tellingen fortsetter fra den nye standen, den fryser ikke.
    data = await _tick(coord, datetime(2026, 5, 25, 14, 55), _states(energy_kwh="0.9"))
    assert data["actual_kwh_this_hour"] == pytest.approx(3.0)


@pytest.mark.asyncio
async def test_absurd_hopp_i_maalerstand_teller_ikke_med():
    """En helt annen måler med høyere total skal ikke bli til 5900 kWh på én time."""
    stored = _lagret_time(kwh=2.5, energy_at_hour_start=100.0)

    coord = _make_coordinator(datetime(2026, 5, 25, 14, 50), stored=stored)
    data = await _tick(coord, datetime(2026, 5, 25, 14, 50), _states(energy_kwh="6000.0"))

    assert data["actual_kwh_this_hour"] == pytest.approx(2.5)

    data = await _tick(coord, datetime(2026, 5, 25, 14, 55), _states(energy_kwh="6000.5"))
    assert data["actual_kwh_this_hour"] == pytest.approx(3.0)


@pytest.mark.asyncio
async def test_omstart_i_ny_maaned_ruller_over_maaneden():
    """Var HA nede over et månedsskifte, må dagsverdiene fra forrige måned ut."""
    stored = _lagret_time(
        hour_start="2026-04-30T23:00:00",
        kwh=0.0,
        energy_at_hour_start=None,
        daily_max={"2026-04-28": 6.0, "2026-04-29": 4.0},
        current_month="2026-04",
    )

    coord = _make_coordinator(datetime(2026, 5, 2, 10, 5), stored=stored)
    await _tick(coord, datetime(2026, 5, 2, 10, 5), _states(energy_kwh="100.0"))

    assert coord._daily_max_kw == {}
    assert coord._previous_month_top_3_snitt_kw == pytest.approx(5.0)
    assert coord._previous_month_name == "2026-04"
    assert coord._current_month == "2026-05"


@pytest.mark.asyncio
async def test_omstart_uten_energisensor_starter_timen_paa_nytt():
    """Uten energy-sensor finnes ingen akkumulator å redde, og den skal ikke late som."""
    stored = _lagret_time(kwh=2.5, energy_at_hour_start=100.0)

    coord = _make_coordinator(datetime(2026, 5, 25, 14, 50), stored=stored)
    data = await _tick(coord, datetime(2026, 5, 25, 14, 50), _states(energy_kwh=None))

    # Timen består, men uten avlesning er det ingenting nytt å legge til.
    assert data["actual_kwh_this_hour"] == pytest.approx(2.5)
    assert coord._energy_at_hour_start == pytest.approx(100.0)


@pytest.mark.parametrize(
    "hour_start,now,ventet",
    [
        (None, datetime(2026, 5, 25, 14, 10), False),
        (datetime(2026, 5, 25, 14, 0), datetime(2026, 5, 25, 14, 0), True),
        (datetime(2026, 5, 25, 14, 0), datetime(2026, 5, 25, 14, 59, 59), True),
        (datetime(2026, 5, 25, 14, 0), datetime(2026, 5, 25, 15, 0), False),
        (datetime(2026, 5, 22, 14, 0), datetime(2026, 5, 25, 14, 10), False),
        (datetime(2026, 5, 25, 15, 0), datetime(2026, 5, 25, 14, 50), False),
    ],
)
def test_hour_state_is_current(hour_start, now, ventet):
    assert hour_state_is_current(hour_start=hour_start, now=now) is ventet


def test_hour_state_is_current_skiller_de_to_gangene_klokka_er_02():
    """Natta timen settes tilbake er 02:00 to forskjellige timer."""
    forste = datetime(2026, 10, 25, 2, 0, tzinfo=CEST)
    andre_naa = datetime(2026, 10, 25, 2, 30, tzinfo=CET)
    assert hour_state_is_current(hour_start=forste, now=andre_naa) is False
    assert hour_state_is_current(hour_start=forste, now=datetime(2026, 10, 25, 2, 30, tzinfo=CEST)) is True


def test_hour_state_is_current_taaler_blanding_av_naiv_og_tidssone():
    """En lagret tid uten tidssone kan ikke sammenlignes, og skal ikke kaste."""
    naiv = datetime(2026, 5, 25, 14, 0)
    med_sone = datetime(2026, 5, 25, 14, 10, tzinfo=CEST)
    assert hour_state_is_current(hour_start=naiv, now=med_sone) is False


@pytest.mark.parametrize(
    "energy_now,start,kwh,ventet_kwh,ventet_start",
    [
        (100.0, None, 0.0, 0.0, 100.0),
        (102.5, 100.0, 0.0, 2.5, 100.0),
        (102.5, 100.0, 2.5, 2.5, 100.0),
        (103.0, 100.0, 2.5, 3.0, 100.0),
        (0.4, 100.0, 2.5, 2.5, -2.1),
        (6000.0, 100.0, 2.5, 2.5, 5997.5),
    ],
)
def test_apply_energy_reading(energy_now, start, kwh, ventet_kwh, ventet_start):
    ny_kwh, ny_start = apply_energy_reading(
        energy_now=energy_now,
        energy_at_hour_start=start,
        current_hour_kwh=kwh,
    )
    assert ny_kwh == pytest.approx(ventet_kwh)
    assert ny_start == pytest.approx(ventet_start)
