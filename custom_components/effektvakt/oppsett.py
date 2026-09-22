"""Trinn-tabellen et oppsett faktisk faar, og problemene som foelger med den.

Ren modul uten Home Assistant-import, som `modell.py`, `timeregnskap.py`,
`hysterese.py` og `laster.py`. Coordinatoren kaller hit og logger, `__init__.py`
gjoer problemene om til repair-meldinger brukeren ser.

To ting kan vaere galt med tabellen, og begge feilet stille foer september 2026:

1. **Noekkelen finnes ikke.** Synken mot fri-nettleie fjerner og doeper om
   nettselskap, men noeklene ligger i folks config entries og kan ikke slettes
   derfra. Et oppsett som peker paa et fjernet selskap fikk tom tabell, og
   sensorene gikk tomme uten at noe sa fra.
2. **Egendefinert tabell uten et aapent oeverste trinn.** Innebygde tabeller
   slutter paa `(inf, pris)`. Skriver brukeren bare tall, er alt over det
   hoeyeste av dem prisfritt land: terskelen blir uendelig og risikoen
   `god_margin` for alltid. Derfor kan oeverste terskel skrives som `null`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .dso import KAPASITETSTRINN_PER_DSO

if TYPE_CHECKING:
    from .modell import Trinn


@dataclass(frozen=True)
class TrinnOppsett:
    """Kapasitetstrinnene et oppsett gir, og det som er galt med dem."""

    trinn: Trinn
    dso_noekkel: str
    dso_ukjent: bool
    mangler_topptrinn: bool
    hoyeste_terskel_kw: float | None


def les_trinn(*, dso_id: Any, custom: Any) -> TrinnOppsett:
    """Trinn-tabellen for en config entry, med problemene den har.

    Egendefinerte trinn vinner over nettselskapet, slik coordinatoren alltid
    har gjort det.
    """
    if custom:
        return _fra_custom(custom)

    noekkel = str(dso_id) if dso_id else ""
    info = KAPASITETSTRINN_PER_DSO.get(noekkel)
    if info is None:
        return TrinnOppsett(
            trinn=[],
            dso_noekkel=noekkel,
            dso_ukjent=True,
            mangler_topptrinn=False,
            hoyeste_terskel_kw=None,
        )
    return TrinnOppsett(
        trinn=list(info["kapasitetstrinn"]),
        dso_noekkel=noekkel,
        dso_ukjent=False,
        mangler_topptrinn=False,
        hoyeste_terskel_kw=None,
    )


def _fra_custom(custom: Any) -> TrinnOppsett:
    """Egendefinerte trinn fra config entryen.

    `null` som terskel er det oeverste trinnet, det uten oevre grense.
    `float("inf")` kan ikke lagres i stedet: HA serialiserer entry-data med
    orjson, som skriver uendelig som `null` uansett. Da er det aerligere aa
    lagre `null` med vilje og oversette her.
    """
    trinn: Trinn = []
    for rad in custom:
        terskel, pris = rad[0], rad[1]
        trinn.append((math.inf if terskel is None else float(terskel), int(pris)))

    hoyeste = trinn[-1][0] if trinn else None
    mangler = hoyeste is not None and not math.isinf(hoyeste)
    return TrinnOppsett(
        trinn=trinn,
        dso_noekkel="custom",
        dso_ukjent=False,
        mangler_topptrinn=mangler,
        hoyeste_terskel_kw=hoyeste if mangler else None,
    )
