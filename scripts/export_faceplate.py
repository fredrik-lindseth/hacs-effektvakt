#!/usr/bin/env python3
"""Eksporter skiven til SVG for trykk og CAD.

Skiven er 100 mm i faktisk størrelse: viewBox 1000x1000 der én enhet er 0,1 mm,
så filen kan tas rett inn i CAD med kjent skala. Teksten ligger som ekte tekst,
ikke baner, så den må konverteres til baner i CAD eller hos trykkeriet.

Bruk:
    python3 scripts/export_faceplate.py --liste
    python3 scripts/export_faceplate.py --dso bkk --out bkk.svg
    python3 scripts/export_faceplate.py --dso bkk --png
    python3 scripts/export_faceplate.py --dso sygnir --maks-kw 30 --variant card
    python3 scripts/export_faceplate.py --dso bkk --stil gossen

Stilene ligger i faceplate.STILER, saa en ny skive dukker opp i --hjelp av seg selv.
"""

from __future__ import annotations

import argparse
import difflib
import importlib.util
import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parent.parent
PAKKE = REPO_ROOT / "custom_components" / "effektvakt"
DSO_MODUL = PAKKE / "dso.py"
FACEPLATE_MODUL = PAKKE / "faceplate.py"

# Skiven er 100 mm bred. 300 dpi er det trykkeriene ber om for korrektur.
PLATE_MM = 100.0
PNG_DPI = 300
MM_PER_TOMME = 25.4


def _feil(*linjer: str) -> None:
    for linje in linjer:
        print(linje, file=sys.stderr)


def _last_modul(navn: str, sti: Path) -> ModuleType:
    """Last en enkelt modulfil uten å importere effektvakt-pakken.

    Pakkens __init__.py drar inn Home Assistant, som ikke er installert her.
    Både dso.py og faceplate.py er rene stdlib-moduler, så de kan lastes hver
    for seg.
    """
    spec = importlib.util.spec_from_file_location(navn, sti)
    if spec is None or spec.loader is None:
        raise SystemExit(f"FEIL: Kunne ikke laste {sti}")
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def last_moduler() -> tuple[dict, ModuleType]:
    """Hent DSO-tabellen og faceplate-modulen fra arbeidskopien."""
    for sti in (DSO_MODUL, FACEPLATE_MODUL):
        if not sti.exists():
            raise SystemExit(f"FEIL: Finner ikke {sti}")
    dso = _last_modul("effektvakt_dso", DSO_MODUL)
    faceplate = _last_modul("effektvakt_faceplate", FACEPLATE_MODUL)
    return dso.KAPASITETSTRINN_PER_DSO, faceplate


def finn_dso(tabell: dict, nokkel: str) -> str | None:
    """Slå opp en DSO på id eller på nettselskapets navn, uten hensyn til store bokstaver."""
    kandidat = nokkel.strip().lower()
    if kandidat in tabell:
        return kandidat
    for dso_id, info in tabell.items():
        if info["navn"].lower() == kandidat:
            return dso_id
    return None


def forslag(tabell: dict, nokkel: str) -> list[str]:
    """Nærmeste id-er for en skrivefeil.

    Delstrengtreff først, siden de er et sterkere signal enn ren tegnlikhet:
    «bkk-nett» og «bkkk» skal begge lande på bkk.
    """
    kandidat = nokkel.strip().lower()
    treff: list[str] = []
    if len(kandidat) >= 3:
        for dso_id, info in sorted(tabell.items()):
            if kandidat in dso_id or dso_id in kandidat or kandidat in info["navn"].lower():
                treff.append(dso_id)
    for naer in difflib.get_close_matches(kandidat, list(tabell), n=3, cutoff=0.5):
        if naer not in treff:
            treff.append(naer)
    return treff[:3]


def skriv_liste(tabell: dict) -> None:
    """Skriv alle DSO-id-er med navn, prisområde og antall terskler."""
    bredde = max(len(dso_id) for dso_id in tabell)
    print(f"{len(tabell)} nettselskap:")
    for dso_id, info in sorted(tabell.items()):
        terskler = len(info["kapasitetstrinn"])
        print(f"  {dso_id:<{bredde}}  {info['navn']} ({info['prisomrade']}, {terskler} trinn)")


def standard_filnavn(dso_id: str, variant: str, stilnavn: str = "geha-meter") -> Path:
    return Path(f"{stilnavn.lower()}-{dso_id}-{variant}.svg")


def til_png(svg_sti: Path) -> Path:
    """Render SVG-en til PNG med rsvg-convert, i 300 dpi ved 100 mm."""
    verktoy = shutil.which("rsvg-convert")
    if verktoy is None:
        raise SystemExit(
            "FEIL: Finner ikke rsvg-convert, så PNG kan ikke lages.\n"
            "Installer den med: brew install librsvg\n"
            "SVG-en er skrevet, så du kan også åpne den i nettleser eller CAD."
        )
    piksler = round(PLATE_MM / MM_PER_TOMME * PNG_DPI)
    png_sti = svg_sti.with_suffix(".png")
    resultat = subprocess.run(
        [verktoy, "-w", str(piksler), "-h", str(piksler), str(svg_sti), "-o", str(png_sti)],
        capture_output=True,
        text=True,
    )
    if resultat.returncode != 0:
        melding = resultat.stderr.strip() or f"rsvg-convert avsluttet med kode {resultat.returncode}"
        raise SystemExit(f"FEIL: rsvg-convert klarte ikke å rendre {svg_sti}:\n{melding}")
    return png_sti


def _bygg_parser(stiler: dict[str, str]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="export_faceplate.py",
        description="Eksporter skiven til SVG for trykk og CAD.",
        epilog="SVG-en er 100 mm i faktisk størrelse. Konverter tekst til baner før trykk.",
    )
    parser.add_argument("--dso", help="DSO-id, for eksempel bkk. Se --liste.")
    parser.add_argument(
        "--maks-kw",
        type=float,
        default=15.0,
        help="Skalaens toppverdi (standard 15). Løftes til nærmeste skalatopp som gir hele hovedtall, "
        "for eksempel 10, 12, 15, 20, 25 eller 30",
    )
    parser.add_argument(
        "--variant",
        choices=["print", "card"],
        default="print",
        help="print gir flate farger uten visere (standard), card gir visere og plastdeksel",
    )
    stilhjelp = ", ".join(f"{nokkel} ({navn})" for nokkel, navn in stiler.items())
    parser.add_argument(
        "--stil",
        choices=list(stiler),
        default=next(iter(stiler)),
        help=f"Skivevariant: {stilhjelp}",
    )
    parser.add_argument("--out", type=Path, help="Sti til SVG-filen (standard <stil>-<dso>-<variant>.svg)")
    parser.add_argument("--liste", action="store_true", help="Vis tilgjengelige DSO-id-er og avslutt")
    parser.add_argument("--png", action="store_true", help="Render også en PNG med rsvg-convert")
    return parser


def main(argv: list[str] | None = None) -> int:
    tabell, faceplate = last_moduler()
    parser = _bygg_parser(faceplate.tilgjengelige_stiler())
    args = parser.parse_args(argv)

    if args.liste:
        skriv_liste(tabell)
        return 0

    if not args.dso:
        _feil("FEIL: Mangler --dso. Se tilgjengelige id-er med --liste.")
        return 2

    dso_id = finn_dso(tabell, args.dso)
    if dso_id is None:
        _feil(f"FEIL: Ukjent DSO-id {args.dso!r}.")
        naere = forslag(tabell, args.dso)
        if naere:
            forslagstekst = ", ".join(f"{kandidat} ({tabell[kandidat]['navn']})" for kandidat in naere)
            _feil(f"Mente du: {forslagstekst}?")
        _feil("Hele listen: python3 scripts/export_faceplate.py --liste")
        return 2

    if args.maks_kw <= 0 or not math.isfinite(args.maks_kw):
        _feil(f"FEIL: --maks-kw må være et positivt tall, fikk {args.maks_kw}.")
        return 2

    info = tabell[dso_id]
    maks = faceplate.normaliser_maks_kw(args.maks_kw)
    svg = faceplate.generate_faceplate(
        kapasitetstrinn=info["kapasitetstrinn"],
        maks_kw=maks,
        variant=args.variant,
        dso_navn=info["navn"],
        stil=args.stil,
    )

    stilnavn = faceplate.tilgjengelige_stiler()[args.stil]
    ut = args.out or standard_filnavn(dso_id, args.variant, stilnavn)
    ut.parent.mkdir(parents=True, exist_ok=True)
    ut.write_text(svg, encoding="utf-8")

    synlige = sum(1 for terskel, _ in info["kapasitetstrinn"] if terskel <= maks)
    print(f"Skrev {ut} ({info['navn']}, {stilnavn}, {maks:g} kW, {args.variant}, {synlige} terskler på skiven)")
    if maks != args.maks_kw:
        print(f"Skalaen ble løftet fra {args.maks_kw:g} til {maks:g} kW for at hovedtallene skal bli hele.")

    if args.png:
        png_sti = til_png(ut)
        print(f"Rendret {png_sti} ({PNG_DPI} dpi ved {PLATE_MM:g} mm)")

    print(f"{PLATE_MM:g} mm i faktisk størrelse. Konverter tekst til baner i CAD eller hos trykkeriet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
