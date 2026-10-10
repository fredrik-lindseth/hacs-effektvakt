#!/usr/bin/env python3
"""Analyser lokal JSON med punkter, uten aa kontakte Home Assistant.

Format: {"punkter": [{"tid": "2026-01-01T00:00:00+01:00", "watt": 0}, ...],
"vinduer": [["2026-01-01T10:00:00+01:00", "2026-01-01T11:00:00+01:00"]]}.
Vinduer er valgfrie. Enheter skal vaere normalisert til W foer innlesning.
Rapporten inneholder ingen entitetsnavn og gir ingen anbefaling om lastkutt.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fil", type=Path)
    parser.add_argument("--start", type=datetime.fromisoformat, required=True)
    parser.add_argument("--slutt", type=datetime.fromisoformat, required=True)
    parser.add_argument("--terskel-w", type=float, required=True)
    parser.add_argument("--maks-hold-sekunder", type=float)
    parser.add_argument("--allerede-paa-minutter", type=float, default=0)
    parser.add_argument("--minst-videre-minutter", type=float, default=15)
    args = parser.parse_args()
    sti = Path(__file__).resolve().parent.parent / "custom_components" / "effektvakt" / "lastprofil.py"
    spec = importlib.util.spec_from_file_location("effektvakt_lastprofil", sti)
    if spec is None or spec.loader is None:
        parser.error("Kunne ikke laste lastprofilmodulen")
    modul = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modul
    spec.loader.exec_module(modul)
    data = json.loads(args.fil.read_text())
    profil = modul.analyser_lastprofil(
        [modul.Effektpunkt(datetime.fromisoformat(p["tid"]), p["watt"]) for p in data["punkter"]],
        start=args.start,
        slutt=args.slutt,
        terskel_w=args.terskel_w,
        maks_hold=timedelta(seconds=args.maks_hold_sekunder) if args.maks_hold_sekunder is not None else None,
    )

    def oppsummer(grunnlag):
        return asdict(grunnlag) | {
            "dekning": grunnlag.dekning,
            "aktiv_andel": grunnlag.aktiv_andel,
            "middel_w": grunnlag.middel_w,
            "middel_aktiv_w": grunnlag.middel_aktiv_w,
        }

    rapport = {
        "forutsetninger": [
            "Historiske tilstander holdes fram til neste rapport, med valgfri maksimal holdetid.",
            "Ukjent eller ugyldig effekt utelates fra kjent energi og aktiv andel; se dekningen.",
            "Restvarighet bruker bare hele sykluser; sensurering kan skjevfordele mot korte sykluser.",
            "Historisk aktiv andel er ikke maalbar kuttkapasitet naa eller garanti om framtidig drift.",
        ],
        "terskel_w": args.terskel_w,
        "maks_hold_sekunder": args.maks_hold_sekunder,
        "tidsgrunnlag": oppsummer(profil.tidsgrunnlag),
        "hele_varigheter_minutter": [s / 60 for s in profil.hele_varigheter_s],
        "venstre_sensurerte_antall": sum(p.venstre_sensurert for p in profil.aktive_perioder),
        "hoyre_sensurerte_antall": sum(p.hoyre_sensurert for p in profil.aktive_perioder),
        "restvarighet": asdict(
            modul.anslaa_restvarighet(
                profil,
                allerede_paa_s=args.allerede_paa_minutter * 60,
                minst_videre_s=args.minst_videre_minutter * 60,
            )
        ),
        "allerede_paa_minutter": args.allerede_paa_minutter,
        "minst_videre_minutter": args.minst_videre_minutter,
    }
    if data.get("vinduer"):
        vinduer = [(datetime.fromisoformat(start), datetime.fromisoformat(slutt)) for start, slutt in data["vinduer"]]
        rapport["valgte_vinduer"] = oppsummer(modul.oppsummer_vinduer(profil, vinduer))
    print(json.dumps(rapport, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
