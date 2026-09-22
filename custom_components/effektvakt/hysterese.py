"""Hysterese på risiko-nivået: demper svingninger fra en støyete effektsensor.

Ansvar i en setning: oppgang er umiddelbar, nedgang krever holdetid, og flere
trinn ned tas ett om gangen med ny timer per trinn.

Ren modul uten Home Assistant-import. `HystereseState` er tilstand, men den er
selvstendig: `apply_hysteresis` muterer den og leser ingenting annet.
Koordinatoren eier instansen, persisterer den og gir den hit ved hvert tick.

Asymmetrien er hele poenget. Å melde fare for sent koster et kapasitetstrinn,
mens å melde fare for lenge bare koster litt komfort, så oppgang slår inn med
en gang og nedgang må stå seg. Uten holdetiden slår varmtvannsberederen av og
på i takt med støyen på sensoren.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .const import RISIKO_LEVELS, RISIKO_RANK

if TYPE_CHECKING:
    from datetime import datetime, timedelta


@dataclass
class HystereseState:
    """Stateful hysterese-tilstand."""

    nivå: str
    pending_nivå: str | None = None
    pending_since: datetime | None = None


def _nivå_ett_under(nivå: str) -> str:
    """Returner risiko-nivået ett trinn under det gitte. Laveste nivå returnerer seg selv."""
    idx = RISIKO_RANK[nivå]
    if idx == 0:
        return nivå
    return RISIKO_LEVELS[idx - 1]


def apply_hysteresis(
    state: HystereseState,
    *,
    rå_nivå: str,
    now: datetime,
    holdetid: timedelta,
) -> None:
    """Oppdater hysterese-state in-place.

    Oppgang er umiddelbar. Nedgang krever holdetid. Multi-step nedgang
    skjer ett trinn av gangen med ny timer per trinn. Se spec for full
    policy.
    """
    rå_rank = RISIKO_RANK[rå_nivå]
    cur_rank = RISIKO_RANK[state.nivå]

    if rå_rank >= cur_rank:
        state.nivå = rå_nivå
        state.pending_nivå = None
        state.pending_since = None
        return

    if state.pending_nivå != rå_nivå:
        state.pending_nivå = rå_nivå
        state.pending_since = now
        return

    if state.pending_since is None:
        state.pending_since = now
        return

    if (now - state.pending_since) >= holdetid:
        ett_under = _nivå_ett_under(state.nivå)
        state.nivå = ett_under
        if RISIKO_RANK[state.nivå] > rå_rank:
            state.pending_since = now
        else:
            state.pending_nivå = None
            state.pending_since = None
