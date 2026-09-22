#!/usr/bin/env python3
"""Generer custom_components/effektvakt/dso.py fra kraftsystemet/fri-nettleie.

fri-nettleie (CC-BY-4.0) er en dugnadsbasert samling av norske nettleie-tariffer
i YAML, og er allerede den kilden hacs-strømkalkulator validerer satsene sine
mot. Effektvakt henter derfor rett fra samme sted i stedet for å gå via et annet
repo på disk.

Nøklene i dso.py ligger i brukernes config entries og kan ikke endres. Derfor er
det `scripts/dso_kilder.json` som styrer hvilke nettselskap som finnes: den
holder nøkkel, visningsnavn, prisområde, hvilken fri-nettleie-fil satsene hentes
fra, og om husholdninger i området har mva-fritak. Scriptet henter bare prisene.

Kjøringen er pinnet til en commit i `_meta.commit` og en tariff-dato i
`_meta.tariff_dato`, slik at `--check` gir samme svar i dag som om et år. Nye
satser tas inn ved å flytte de to feltene og kjøre scriptet på nytt.

Bruk:
    python3 scripts/generer_dso_fra_fri_nettleie.py            # regenerer
    python3 scripts/generer_dso_fra_fri_nettleie.py --check    # feiler ved diff
    python3 scripts/generer_dso_fra_fri_nettleie.py --kilde ~/src/fri-nettleie

Uten --kilde lastes tariffene ned fra GitHub på den pinnede commiten. Har du
en utsjekk liggende, peker $FRI_NETTLEIE_ROOT på den én gang for alle.

Data fra https://github.com/kraftsystemet/fri-nettleie (CC-BY-4.0).
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import sys
import tarfile
import urllib.request
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
KILDER = REPO_ROOT / "scripts" / "dso_kilder.json"
DSO_PY = REPO_ROOT / "custom_components" / "effektvakt" / "dso.py"

TARBALL = "https://codeload.github.com/kraftsystemet/fri-nettleie/tar.gz/{commit}"

# Fastledd-metodene i fri-nettleie som faktisk er kW-trinn. TRE_DØGNMAX_MND er
# NVE-modellen effektvakt regner etter. MND_MAX og UKJENT har samme tabellform
# (kW inn, kr/mnd ut), men slår opp trinnet på et annet tall, så de tas med og
# listes. OV_TREFASE har ampere på tersklene og FEM_VEKTET_ÅR har ingen trinn i
# det hele tatt; begge ville gitt tull i tabellen vår og holdes utenfor.
NVE_METODE = "TRE_DØGNMAX_MND"
KW_TRINN_METODER = frozenset({NVE_METODE, "MND_MAX", "UKJENT"})


class Kildefeil(RuntimeError):
    """Kilden ga ikke det vi trenger for å generere tabellen."""


def les_kilder() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Les scripts/dso_kilder.json og returner (meta, nettselskap)."""
    data = json.loads(KILDER.read_text(encoding="utf-8"))
    return data["_meta"], data["nettselskap"]


def last_ned_tariffer(commit: str) -> dict[str, dict[str, Any]]:
    """Hent tariffer/*.yml fra fri-nettleie på en pinnet commit."""
    url = TARBALL.format(commit=commit)
    with urllib.request.urlopen(url, timeout=60) as svar:
        raa = svar.read()
    ut: dict[str, dict[str, Any]] = {}
    with tarfile.open(fileobj=io.BytesIO(raa), mode="r:gz") as tar:
        for medlem in tar.getmembers():
            deler = Path(medlem.name).parts
            if len(deler) != 3 or deler[1] != "tariffer" or not deler[2].endswith(".yml"):
                continue
            fil = tar.extractfile(medlem)
            if fil is None:
                continue
            ut[deler[2].removesuffix(".yml")] = yaml.safe_load(fil.read())
    if not ut:
        raise Kildefeil(f"Fant ingen tariffer/*.yml i {url}")
    return ut


def les_lokale_tariffer(kilde: Path) -> dict[str, dict[str, Any]]:
    """Les tariffer/*.yml fra en utsjekk av fri-nettleie på disk."""
    katalog = kilde if kilde.name == "tariffer" else kilde / "tariffer"
    if not katalog.is_dir():
        raise Kildefeil(f"Fant ikke {katalog}. Pek --kilde på en utsjekk av fri-nettleie.")
    filer = sorted(katalog.glob("*.yml"))
    if not filer:
        raise Kildefeil(f"{katalog} inneholder ingen *.yml")
    return {p.stem: yaml.safe_load(p.read_text(encoding="utf-8")) for p in filer}


def aktiv_tariff(data: dict[str, Any], paa: date, kundegruppe: str = "husholdning") -> dict[str, Any] | None:
    """Finn tariffen som gjelder for en kundegruppe på en gitt dato."""
    for tariff in data.get("tariffer", []):
        if kundegruppe not in tariff.get("kundegrupper", []):
            continue
        if date.fromisoformat(tariff["gyldig_fra"]) > paa:
            continue
        if "gyldig_til" in tariff and date.fromisoformat(tariff["gyldig_til"]) <= paa:
            continue
        return tariff
    return None


def kr_mnd(aar_eks_mva: float, mva: float) -> int:
    """kr/år eks. mva til kr/mnd inkl. mva, slik dso.py lagrer det.

    Halve kroner rundes opp. Innebygd round() gjør bankers rounding og ville
    gitt 232 der prislisten sier 233.
    """
    maaned = Decimal(str(aar_eks_mva)) / 12 * (1 + Decimal(str(mva)))
    return int(maaned.quantize(Decimal(1), ROUND_HALF_UP))


def trinn_fra_tariff(tariff: dict[str, Any], mva: float) -> list[tuple[float, int]]:
    """Gjør fri-nettleies fastledd om til våre (øvre kW-grense, kr/mnd inkl. mva).

    De oppgir nedre kW-grense og kr/år eks. mva. Øvre grense for trinn i er nedre
    grense for trinn i+1, og siste trinn er uendelig.
    """
    fastledd = tariff.get("fastledd") or {}
    metode = str(fastledd.get("metode", ""))
    if metode not in KW_TRINN_METODER:
        raise Kildefeil(f"fastledd-metode {metode or '(mangler)'} er ikke kW-trinn")
    terskler = fastledd.get("terskler")
    if not terskler:
        raise Kildefeil(f"fastledd-metode {metode} uten terskler")
    trinn: list[tuple[float, int]] = []
    for i, rad in enumerate(terskler):
        oevre = float(terskler[i + 1]["terskel"]) if i + 1 < len(terskler) else math.inf
        trinn.append((oevre, kr_mnd(rad["pris"], mva)))
    return trinn


def _trinn_literal(kw: float) -> str:
    return 'float("inf")' if math.isinf(kw) else f"{kw}"


def generer(meta: dict[str, Any], rader: dict[str, dict[str, Any]]) -> str:
    """Skriv ut dso.py slik ruff format ville formatert den."""
    linjer = [
        "# AUTOGENERERT fra kraftsystemet/fri-nettleie. Se docs/dso.md.",
        "# Kjør scripts/generer_dso_fra_fri_nettleie.py for å regenerere.",
        "# Manuell redigering blir overskrevet.",
        "",
        '"""Kapasitetstrinn per nettselskap.',
        "",
        f"Satser fra {meta['kilde']} (CC-BY-4.0),",
        f"commit {meta['commit']}, tariff gyldig {meta['tariff_dato']}.",
        "",
        "Nøkler, navn og prisområde kommer fra scripts/dso_kilder.json.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Final, TypedDict",
        "",
        "",
        "class DSOInfo(TypedDict):",
        '    """Kapasitetstrinn-data for et nettselskap."""',
        "",
        "    navn: str",
        "    prisomrade: str",
        "    kapasitetstrinn: list[tuple[float, int]]  # (kW-terskel, kr/mnd)",
        "",
        "",
        "KAPASITETSTRINN_PER_DSO: Final[dict[str, DSOInfo]] = {",
    ]
    for nokkel in sorted(rader):
        rad = rader[nokkel]
        linjer.append(f'    "{nokkel}": {{')
        linjer.append(f'        "navn": "{rad["navn"]}",')
        linjer.append(f'        "prisomrade": "{rad["prisomrade"]}",')
        linjer.append('        "kapasitetstrinn": [')
        for kw, pris in rad["kapasitetstrinn"]:
            linjer.append(f"            ({_trinn_literal(kw)}, {pris}),")
        linjer.append("        ],")
        linjer.append("    },")
    linjer.append("}")
    linjer.append("")
    return "\n".join(linjer)


def bygg_rader(
    nettselskap: dict[str, dict[str, Any]],
    tariffer: dict[str, dict[str, Any]],
    paa: date,
) -> tuple[dict[str, dict[str, Any]], list[str], list[str]]:
    """Regn ut trinn for hvert nettselskap. Returnerer (rader, utelatt, ikke_nve)."""
    rader: dict[str, dict[str, Any]] = {}
    utelatt: list[str] = []
    ikke_nve: list[str] = []
    for nokkel, kilde in sorted(nettselskap.items()):
        slug = kilde["slug"]
        data = tariffer.get(slug)
        if data is None:
            utelatt.append(f"{nokkel}: fri-nettleie har ingen {slug}.yml")
            continue
        tariff = aktiv_tariff(data, paa)
        if tariff is None:
            utelatt.append(f"{nokkel}: ingen husholdningstariff gyldig {paa}")
            continue
        try:
            trinn = trinn_fra_tariff(tariff, float(kilde["mva"]))
        except Kildefeil as feil:
            utelatt.append(f"{nokkel}: {feil}")
            continue
        metode = str((tariff.get("fastledd") or {}).get("metode", ""))
        if metode != NVE_METODE:
            ikke_nve.append(f"{nokkel} ({metode})")
        rader[nokkel] = {
            "navn": kilde["navn"],
            "prisomrade": kilde["prisomrade"],
            "kapasitetstrinn": trinn,
        }
    return rader, utelatt, ikke_nve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generer dso.py fra fri-nettleie")
    parser.add_argument("--check", action="store_true", help="Feil hvis dso.py avviker")
    parser.add_argument(
        "--kilde",
        type=Path,
        default=Path(kilde_env) if (kilde_env := os.environ.get("FRI_NETTLEIE_ROOT")) else None,
        help="Utsjekk av fri-nettleie på disk (default: $FRI_NETTLEIE_ROOT, ellers nedlasting)",
    )
    parser.add_argument("--dato", help="Overstyr tariff-dato (YYYY-MM-DD)")
    parser.add_argument("--commit", help="Overstyr pinnet commit ved nedlasting")
    args = parser.parse_args(argv)

    meta, nettselskap = les_kilder()
    paa = date.fromisoformat(args.dato or meta["tariff_dato"])

    try:
        if args.kilde:
            tariffer = les_lokale_tariffer(args.kilde)
        else:
            tariffer = last_ned_tariffer(args.commit or meta["commit"])
    except (Kildefeil, OSError) as feil:
        print(f"FEIL: fikk ikke tak i tariffene: {feil}", file=sys.stderr)
        return 2

    rader, utelatt, ikke_nve = bygg_rader(nettselskap, tariffer, paa)
    if utelatt:
        print(f"FEIL: {len(utelatt)} nettselskap mangler satser:", file=sys.stderr)
        for linje in utelatt:
            print(f"  - {linje}", file=sys.stderr)
        print("Nøklene ligger i brukernes config entries og kan ikke bare forsvinne.", file=sys.stderr)
        return 2

    generert = generer(meta, rader)

    if args.check:
        if not DSO_PY.exists():
            print(f"FEIL: {DSO_PY} finnes ikke. Kjør uten --check først.", file=sys.stderr)
            return 1
        if DSO_PY.read_text(encoding="utf-8") != generert:
            print("FEIL: dso.py stemmer ikke med fri-nettleie på pinnet commit.", file=sys.stderr)
            print("Kjør: python3 scripts/generer_dso_fra_fri_nettleie.py", file=sys.stderr)
            return 1
        print(f"OK: dso.py er i takt med fri-nettleie ({len(rader)} nettselskap).")
        return 0

    DSO_PY.write_text(generert, encoding="utf-8")
    print(f"Skrev {DSO_PY} ({len(rader)} nettselskap, tariff gyldig {paa}).")
    if ikke_nve:
        print(f"Annen fastledd-metode enn {NVE_METODE}: {', '.join(ikke_nve)}")
    ukjente = sorted(set(tariffer) - {k["slug"] for k in nettselskap.values()})
    if ukjente:
        print(f"I fri-nettleie, men ikke i dso_kilder.json: {', '.join(ukjente)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
