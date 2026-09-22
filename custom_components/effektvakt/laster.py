"""Kuttbare laster: hvilke som kan kuttes akkurat nå, og hvor mye de utgjør.

Ren modul uten Home Assistant-import. Kalleren leser sensorene og sender
avlesningene hit; her står bare regelen for hva som teller med og hvor mye
summen blir. Det gjør reglene testbare uten stubber, og det holder
`avlesning.py` som eneste sted HA-flaten ligger.

Alle konfigurerte kilder er med i lista, også de strategien ikke bruker.
Forskjellen mellom «finnes ikke» og «teller ikke nå» er nettopp det som er
verdt å se på et dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass

from .const import (
    BLIND_ASSUMED_KUTT_KW,
    EKSTRA_SENSOR_ACTIVE_THRESHOLD_W,
    STRATEGI_BLIND,
    STRATEGI_VVB_PLUSS_EKSTRA,
    STRATEGI_VVB_STATUS,
    VVB_ACTIVE_THRESHOLD_W,
)

# Rollene en kuttbar last kan ha. Verdiene går ut i attributtet kutt_kilder,
# så de er en del av kontrakten mot dashboards.
ROLLE_VVB = "vvb"
ROLLE_EKSTRA = "ekstra"

TERSKEL_PER_ROLLE: dict[str, float] = {
    ROLLE_VVB: VVB_ACTIVE_THRESHOLD_W,
    ROLLE_EKSTRA: EKSTRA_SENSOR_ACTIVE_THRESHOLD_W,
}

# Hvilke roller som faktisk teller med i summen, per strategi. blind leser ingen
# sensorer i det hele tatt, og ukjent strategi teller ingenting.
ROLLER_PER_STRATEGI: dict[str, frozenset[str]] = {
    STRATEGI_BLIND: frozenset(),
    STRATEGI_VVB_STATUS: frozenset({ROLLE_VVB}),
    STRATEGI_VVB_PLUSS_EKSTRA: frozenset({ROLLE_VVB, ROLLE_EKSTRA}),
}


@dataclass(frozen=True)
class KildeAvlesning:
    """Rå avlesning av en konfigurert kuttkilde, før strategien har sagt sitt.

    `effekt_w` er None når sensoren er unavailable, unknown eller ulesbar. Det
    er noe annet enn 0 W: da vet vi ikke hva lasten trekker.
    """

    entity_id: str
    navn: str | None
    effekt_w: float | None
    rolle: str


@dataclass(frozen=True)
class KuttKilde:
    """En kuttbar last slik den ser ut akkurat nå.

    Feltnavnene er nøklene i attributtet kutt_kilder.
    """

    entity_id: str
    navn: str | None
    effekt_w: float | None
    teller_med: bool
    rolle: str
    terskel_w: float


def teller_med(*, strategi: str, rolle: str, effekt_w: float | None) -> bool:
    """Om en kilde faktisk bidrar til tilgjengelig kutt akkurat nå.

    Tre ting må stemme: strategien må bruke rollen, sensoren må ha en lesbar
    verdi, og verdien må ligge over terskelen for rollen.
    """
    if effekt_w is None:
        return False
    if rolle not in ROLLER_PER_STRATEGI.get(strategi, frozenset()):
        return False
    return effekt_w > TERSKEL_PER_ROLLE[rolle]


def build_kutt_kilder(*, strategi: str, avlesninger: list[KildeAvlesning]) -> list[KuttKilde]:
    """Gjør avlesningene om til kutt_kilder-oppføringer.

    Alle konfigurerte kilder er med, også de strategien ikke bruker. Forskjellen
    mellom "finnes ikke" og "teller ikke nå" er nettopp det som er verdt å se.
    """
    return [
        KuttKilde(
            entity_id=a.entity_id,
            navn=a.navn,
            effekt_w=None if a.effekt_w is None else round(a.effekt_w, 1),
            teller_med=teller_med(strategi=strategi, rolle=a.rolle, effekt_w=a.effekt_w),
            rolle=a.rolle,
            terskel_w=TERSKEL_PER_ROLLE[a.rolle],
        )
        for a in avlesninger
    ]


def compute_tilgjengelig_kutt_kw(
    *,
    strategi: str,
    vvb_power_w: float | None,
    ekstra_power_w: list[float | None] | None = None,
) -> float:
    """Beregn realistisk tilgjengelig kutt i kW basert på valgt strategi.

    blind: antar BLIND_ASSUMED_KUTT_KW
    vvb_status: bruker faktisk VVB-effekt, kun over VVB_ACTIVE_THRESHOLD_W
    vvb_pluss_ekstra: VVB pluss sum av ekstra-sensorer over EKSTRA_SENSOR_ACTIVE_THRESHOLD_W

    Summen går over de samme kildene som får teller_med i kutt_kilder, så de to
    tallene kan ikke drifte fra hverandre. blind er unntaket: der er tilstanden
    en antagelse, ikke en sum av kilder.
    """
    if strategi == STRATEGI_BLIND:
        return BLIND_ASSUMED_KUTT_KW

    total_w = 0.0
    if vvb_power_w is not None and teller_med(strategi=strategi, rolle=ROLLE_VVB, effekt_w=vvb_power_w):
        total_w += vvb_power_w
    for p in ekstra_power_w or []:
        if p is not None and teller_med(strategi=strategi, rolle=ROLLE_EKSTRA, effekt_w=p):
            total_w += p
    return total_w / 1000.0
