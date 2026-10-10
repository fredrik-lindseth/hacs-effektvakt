"""Verifiser eksport av HA-historikk, enheter og maalehull uten nettverk."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

from scripts import hent_lastprofil as eksport

SENSOR = "sensor.example_power"
START = datetime(2026, 1, 1, tzinfo=UTC)
SLUTT = datetime(2026, 1, 8, tzinfo=UTC)


def _rad(tid="2026-01-01T00:00:00+00:00", state="300", unit="W", sensor=SENSOR):
    return {
        "entity_id": sensor,
        "last_changed": tid,
        "last_updated": tid,
        "state": state,
        "attributes": {"unit_of_measurement": unit, "friendly_name": "Privat navn"},
    }


def test_full_respons_beholder_initialtilstand_enheter_og_ukjent_tid_i_utc_rekkefolge():
    data = [
        [
            _rad("2026-01-01T01:30:00+01:00", "unknown"),
            _rad("2026-01-01T01:00:00+01:00", "0.3", "kW"),
            _rad("2026-01-01T00:45:00+00:00", "500"),
        ],
        [_rad(state="9000", sensor="sensor.annen")],
    ]
    resultat = eksport.normaliser_historikk(data, SENSOR)
    assert resultat == {
        "punkter": [
            {"tid": "2026-01-01T00:00:00+00:00", "watt": 300},
            {"tid": "2026-01-01T00:30:00+00:00", "watt": None},
            {"tid": "2026-01-01T00:45:00+00:00", "watt": 500},
        ]
    }
    assert SENSOR not in json.dumps(resultat)
    assert "Privat navn" not in json.dumps(resultat)


@pytest.mark.parametrize(
    ("state", "unit"),
    [("unavailable", "W"), ("nan", "W"), ("inf", "W"), ("-1", "W"), ("1e308", "kW"), ("300", None), ("300", "kWh")],
)
def test_ugyldige_verdier_og_enheter_beholdes_som_maalehull(state, unit):
    resultat = eksport.normaliser_historikk([[_rad(state=state, unit=unit)]], SENSOR)
    assert resultat["punkter"][0]["watt"] is None


def test_attributtendring_tidsfestes_med_last_updated():
    rad = _rad()
    rad["last_updated"] = "2026-01-01T00:10:00+00:00"
    assert eksport.normaliser_historikk([[rad]], SENSOR)["punkter"][0]["tid"] == rad["last_updated"]


@pytest.mark.parametrize("tid", ["uten dato", "2026-01-01T00:00:00", None])
def test_ugyldige_tidspunkter_avvises_i_stedet_for_aa_slette_maalehullet(tid):
    with pytest.raises(ValueError):
        eksport.normaliser_historikk([[_rad(tid=tid)]], SENSOR)


def test_tom_historikk_og_annen_entitet_gir_ingen_fiktive_nullpunkter():
    assert eksport.normaliser_historikk([], SENSOR) == {"punkter": []}
    assert eksport.normaliser_historikk([[_rad(sensor="sensor.annen")]], SENSOR) == {"punkter": []}


@pytest.mark.parametrize("data", [{}, [None], [[None]]])
def test_feil_responsformat_avvises(data):
    with pytest.raises(ValueError, match="format"):
        eksport.normaliser_historikk(data, SENSOR)


def _hent(**endringer):
    return eksport.hent_historikk(
        **(
            {
                "url": "https://ha.example",
                "token": "hemmelig-token",
                "sensor": SENSOR,
                "start": START,
                "slutt": SLUTT,
                "timeout": 45,
            }
            | endringer
        )
    )


def test_restkallet_ber_om_full_historikk_med_initialtilstand(monkeypatch):
    class Opener:
        def open(self, request, timeout):
            url = urlsplit(request.full_url)
            assert unquote(url.path) == "/api/history/period/2026-01-01T00:00:00+00:00"
            assert parse_qs(url.query) == {
                "filter_entity_id": [SENSOR],
                "end_time": [SLUTT.isoformat()],
                "significant_changes_only": ["0"],
            }
            assert request.get_header("Authorization") == "Bearer hemmelig-token"
            assert timeout == 45
            return io.BytesIO(json.dumps([[_rad()]]).encode())

    def bygg(handler):
        assert isinstance(handler, eksport.IngenOmdirigering)
        return Opener()

    monkeypatch.setattr(eksport, "build_opener", bygg)
    assert _hent()["punkter"][0]["watt"] == 300


@pytest.mark.parametrize(
    "feil",
    [
        HTTPError("https://hemmelig-token", 401, "hemmelig-token", {}, None),
        URLError("hemmelig-token"),
        TimeoutError("hemmelig-token"),
    ],
)
def test_feiltekst_avslorer_ikke_token_eller_http_body(monkeypatch, feil):
    class Opener:
        def open(self, request, timeout):
            raise feil

    monkeypatch.setattr(eksport, "build_opener", lambda handler: Opener())
    with pytest.raises(ValueError) as err:
        _hent()
    assert "hemmelig-token" not in str(err.value)


def test_omdirigering_avvises_for_aa_holde_token_paa_opprinnelig_vert():
    assert eksport.IngenOmdirigering().redirect_request(None, None, 302, "", {}, "https://annen.example") is None


@pytest.mark.parametrize(
    "url", ["ftp://ha.example", "https://user:pass@ha.example", "https://ha.example/?token=secret"]
)
def test_ugyldig_url_avvises_for_nettverkskall(url):
    with pytest.raises(ValueError, match="HA_URL"):
        _hent(url=url)
