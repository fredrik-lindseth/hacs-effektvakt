#!/usr/bin/env python3
"""Hent lokal lastprofil fra HA-historikk uten aa lagre token eller entitetsnavn."""

from __future__ import annotations

import argparse
import getpass
import json
import math
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class IngenOmdirigering(HTTPRedirectHandler):
    """Ikke send Authorization videre ved en omdirigering."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def les_tid(verdi: str) -> datetime:
    """Krev tidssone og normaliser til faktisk UTC-tid."""
    try:
        tid = datetime.fromisoformat(verdi)
    except (TypeError, ValueError) as err:
        raise ValueError("Ugyldig tidspunkt") from err
    if tid.tzinfo is None or tid.utcoffset() is None:
        raise ValueError("Tidspunkt maa ha tidssone")
    return tid.astimezone(UTC)


def normaliser_historikk(data: object, sensor: str) -> dict:
    """Behold maalehull; bruk bare etterspurt entitet og eksplisitte W/kW."""
    if not isinstance(data, list):
        raise ValueError("Uventet historikkformat")
    punkter = []
    for serie in data:
        if not isinstance(serie, list):
            raise ValueError("Uventet historikkformat")
        for rad in serie:
            if not isinstance(rad, dict):
                raise ValueError("Uventet historikkformat")
            if rad.get("entity_id") != sensor:
                continue
            tid = les_tid(rad.get("last_updated") or rad.get("last_changed"))
            attrs = rad.get("attributes")
            enhet = attrs.get("unit_of_measurement") if isinstance(attrs, dict) else None
            watt = None
            if enhet in ("W", "kW"):
                try:
                    verdi = float(rad.get("state"))
                    if math.isfinite(verdi) and verdi >= 0:
                        watt = verdi * (1000 if enhet == "kW" else 1)
                        if not math.isfinite(watt):
                            watt = None
                except (TypeError, ValueError):
                    pass
            punkter.append((tid, watt))
    punkter.sort(key=lambda punkt: punkt[0])
    return {"punkter": [{"tid": tid.isoformat(), "watt": watt} for tid, watt in punkter]}


def hent_historikk(*, url: str, token: str, sensor: str, start: datetime, slutt: datetime, timeout: float) -> dict:
    """Full HA-respons beholder enhet og initialtilstand; ingen token i feil."""
    deler = urlsplit(url)
    if (
        deler.scheme not in ("http", "https")
        or not deler.hostname
        or deler.username is not None
        or deler.password is not None
        or deler.query
        or deler.fragment
    ):
        raise ValueError("HA_URL maa vaere en HTTP(S)-adresse uten brukernavn, query eller fragment")
    if not re.fullmatch(r"sensor\.[a-z0-9_]+", sensor):
        raise ValueError("Oppgi en effektsensor som sensor.example_power")
    if start.tzinfo is None or slutt.tzinfo is None or start >= slutt:
        raise ValueError("Start og slutt maa ha tidssone, og slutt maa vaere etter start")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Timeout maa vaere positiv")
    if not token or "\r" in token or "\n" in token:
        raise ValueError("Mangler gyldig HA-token")
    query = urlencode({"filter_entity_id": sensor, "end_time": slutt.isoformat(), "significant_changes_only": "0"})
    api_url = url.rstrip("/") + "/api/history/period/" + quote(start.isoformat(), safe="") + "?" + query
    request = Request(api_url, headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
    try:
        with build_opener(IngenOmdirigering()).open(request, timeout=timeout) as response:
            data = json.load(response)
    except HTTPError as err:
        raise ValueError(f"HA svarte HTTP {err.code}; sjekk adresse, token og tilgang til historikken") from None
    except (URLError, TimeoutError, OSError):
        raise ValueError("Kunne ikke hente HA-historikk; sjekk adresse og forbindelse") from None
    except (ValueError, UnicodeError):
        raise ValueError("HA svarte ikke med gyldig historikk-JSON") from None
    return normaliser_historikk(data, sensor)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.environ.get("HA_URL"))
    parser.add_argument("--sensor", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--slutt", required=True)
    parser.add_argument("--utfil", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()
    if not args.url:
        parser.error("Oppgi --url eller HA_URL")
    token = os.environ.get("HA_TOKEN")
    if not token:
        if not sys.stdin.isatty():
            parser.error("Sett HA_TOKEN eller kjor interaktivt for maskert token-prompt")
        token = getpass.getpass("Home Assistant-token (skjult): ")
    try:
        data = hent_historikk(
            url=args.url,
            token=token,
            sensor=args.sensor,
            start=les_tid(args.start),
            slutt=les_tid(args.slutt),
            timeout=args.timeout,
        )
        if not data["punkter"]:
            raise ValueError("Ingen historikk for sensoren i vinduet; sjekk recorder og tilgang")
        args.utfil.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    except (ValueError, OSError) as err:
        # Nettverksfeil er allerede omskrevet uten URL, respons-body eller token.
        parser.error(str(err) if isinstance(err, ValueError) else "Kunne ikke skrive lokal profilfil")
    print(f"Skrev {len(data['punkter'])} punkter til lokal profilfil")


if __name__ == "__main__":
    main()
