"""Vokter at relative lenker og bildestier i dokumentasjonen peker på noe som finnes.

Bakgrunnen er konkret. Doktabellen i `AGENTS.md` pekte på `docs/strategi.md`
lenge etter at filen var slettet, og suiten var grønn hele veien. Det tok tre
agenter og en dom før noen klikket på lenken.

Testen dømmer bare eksistens: at filen lenken peker på ligger der. Eksterne
URL-er og rene ankere (`#et-avsnitt`) er utenfor, fordi de krever nett eller en
overskriftsparser og er en annen klasse feil.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# Dokumentene et menneske faktisk klikker seg gjennom.
DOKUMENTER = (REPO / "README.md", REPO / "AGENTS.md", *sorted((REPO / "docs").rglob("*.md")))

# `[tekst](sti)` og `![alt](sti)`, med valgfri tittel etter stien.
MARKDOWN_LENKE = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)>\s]+)>?(?:\s+[\"'][^\"']*[\"'])?\s*\)")

# README har HTML-blokker med merker og bilder.
HTML_LENKE = re.compile(r"<(?:img[^>]*\ssrc|a[^>]*\shref)=[\"']([^\"']+)[\"']")

# Alt som ikke er en sti i treet: eksterne skjemaer, protokollrelative URL-er,
# og lenker som bare peker på et avsnitt i samme fil.
UTENFOR = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//|#)")


def _lenker(fil: Path) -> list[str]:
    tekst = fil.read_text(encoding="utf-8")
    treff = [m.group(1) for m in MARKDOWN_LENKE.finditer(tekst)]
    treff += [m.group(1) for m in HTML_LENKE.finditer(tekst)]
    return [lenke for lenke in treff if not UTENFOR.match(lenke)]


@pytest.mark.parametrize("fil", DOKUMENTER, ids=lambda fil: str(fil.relative_to(REPO)))
def test_relative_lenker_peker_paa_noe_som_finnes(fil: Path) -> None:
    brutte = []
    for lenke in _lenker(fil):
        sti = lenke.split("#", 1)[0].split("?", 1)[0]
        if not sti:
            continue
        if not (fil.parent / sti).exists():
            brutte.append(lenke)

    assert not brutte, f"{fil.relative_to(REPO)} peker på filer som ikke finnes: {', '.join(brutte)}"


def test_dokumentlisten_fanger_opp_docs() -> None:
    """Uten denne kan globben stille slutte å finne noe, og suiten blir grønn på null lenker."""
    assert len(DOKUMENTER) > 10
    assert sum(len(_lenker(fil)) for fil in DOKUMENTER) > 20
