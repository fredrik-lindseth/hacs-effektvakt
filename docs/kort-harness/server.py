#!/usr/bin/env python3
"""Prøvebenk for Effektvakt-kortet, uten Home Assistant.

Serverer repoet på 127.0.0.1 og svarer på `faceplates.json` med skiver som
genereres fra `faceplate.py` der og da. Kortet lastes fra den ene ekte filen
under `custom_components/effektvakt/www/`, så benken kan ikke vise noe annet
enn det Home Assistant faktisk serverer.

Bruk:
    python3 docs/kort-harness/server.py
    python3 docs/kort-harness/server.py --dso sygnir --port 8800 --ingen-nettleser

Home Assistant trengs ikke: både dso.py og faceplate.py er rene stdlib-moduler
og lastes rett fra fil, slik eksportscriptet gjør det.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import importlib.util
import json
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
PAKKE = REPO_ROOT / "custom_components" / "effektvakt"
HARNESS_URL = "/docs/kort-harness/"
SKIVE_URL = f"{HARNESS_URL}faceplates.json"

# Skalaene benken skal kunne vise. Kortet ber om en av dem med `maks_kw`.
MAKS_KW_UTVALG = (15.0, 30.0)


def _last_modul(navn: str, sti: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(navn, sti)
    if spec is None or spec.loader is None:
        raise SystemExit(f"FEIL: Kunne ikke laste {sti}")
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def lag_skiver(dso_id: str) -> dict[str, dict[str, Any]]:
    """Alle stiler ganger alle skalaer, nøklet slik kortet spør etter dem."""
    dso = _last_modul("effektvakt_dso", PAKKE / "dso.py")
    fp = _last_modul("effektvakt_faceplate", PAKKE / "faceplate.py")

    info = dso.KAPASITETSTRINN_PER_DSO.get(dso_id)
    if info is None:
        kjente = ", ".join(sorted(dso.KAPASITETSTRINN_PER_DSO))
        raise SystemExit(f"FEIL: Ukjent DSO {dso_id!r}. Velg mellom: {kjente}")

    trinn = list(info["kapasitetstrinn"])
    skiver: dict[str, dict[str, Any]] = {}
    for stil in fp.STILNAVN:
        for maks_kw in MAKS_KW_UTVALG:
            skiver[f"{stil}:{maks_kw:.1f}"] = {
                "svg": fp.generate_faceplate(
                    kapasitetstrinn=trinn,
                    maks_kw=maks_kw,
                    variant="card",
                    dso_navn=info["navn"],
                    stil=stil,
                ),
                "maks_kw": maks_kw,
                "dso_navn": info["navn"],
                "stil": stil,
                "stiler": fp.tilgjengelige_stiler(),
                "palett": {**fp.PALETT, **fp.STILER[stil].palett},
            }
    return skiver


class Handler(http.server.SimpleHTTPRequestHandler):
    """Filserver for repoet, med skivene generert ved forespørsel."""

    def __init__(self, *args: Any, dso_id: str, **kwargs: Any) -> None:
        self._dso_id = dso_id
        super().__init__(*args, directory=str(REPO_ROOT), **kwargs)

    def do_GET(self) -> None:
        if self.path.split("?")[0] == SKIVE_URL:
            self._send_skiver()
            return
        super().do_GET()

    def _send_skiver(self) -> None:
        kropp = json.dumps(lag_skiver(self._dso_id)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(kropp)))
        # Skiven skal regenereres hver gang, ellers viser benken gammel kode.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(kropp)

    def end_headers(self) -> None:
        if self.path.endswith(".js"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dso", default="bkk", help="Nettselskap skivene tegnes for (standard bkk)")
    parser.add_argument("--port", type=int, default=8799, help="Port (standard 8799)")
    parser.add_argument("--ingen-nettleser", action="store_true", help="Ikke åpne nettleser")
    args = parser.parse_args()

    lag_skiver(args.dso)  # feil i faceplate.py skal si fra nå, ikke i nettleseren

    handler = functools.partial(Handler, dso_id=args.dso)
    url = f"http://127.0.0.1:{args.port}{HARNESS_URL}"
    with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        print(f"Prøvebenk for {args.dso}: {url}")
        print("Ctrl-C for å stoppe.")
        if not args.ingen_nettleser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print()


if __name__ == "__main__":
    main()
