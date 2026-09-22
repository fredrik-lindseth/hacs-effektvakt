"""Kuttbare laster: hva som kan kuttes akkurat nå, og hva som faktisk ble kuttet.

Ren modul uten Home Assistant-import. Kalleren leser sensorene og bryterne og
sender avlesningene hit; her står bare regelen for hva som teller med, hvor mye
summen blir, og når en last gikk av mens Effektvakt ba om kutt. Det gjør
reglene testbare uten stubber, og det holder `avlesning.py` som eneste sted
HA-flaten ligger.

En last er tre ting: en effektsensor, en valgfri bryter, og en terskel for når
sensoren regnes som «varmer nå». Integrasjonen kjenner ingen apparattyper. En
varmtvannsbereder, en varmepumpe, en billader og et sett varmekabler er den
samme saken her, de har bare ulike terskler.

Bryteren er det nye av de tre. Uten den kunne integrasjonen bare gjette på hva
som ble kuttet, siden det er blueprintene og ikke integrasjonen som slår av
last. Med den kan et kutt observeres: går bryteren av mens kutt er anbefalt,
er det vårt kutt, og `kuttet_siden` er tidspunktet. Det er grunnlaget
hendelsesloggen og sparesensoren regner videre på.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .const import (
    CONF_LAST_BRYTER,
    CONF_LAST_EFFEKT_SENSOR,
    CONF_LAST_NAVN,
    CONF_LAST_TERSKEL_W,
    CONF_LASTER,
    DEFAULT_LAST_TERSKEL_W,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime


@dataclass(frozen=True)
class LastOppsett:
    """En kuttbar last slik den står i config entryen.

    `navn` er valgfritt: står det tomt, brukes sensorens eget friendly_name.
    Da slipper brukeren å skrive det samme navnet to steder, og lasten heter
    det den heter ellers i Home Assistant.
    """

    effekt_sensor: str
    navn: str | None = None
    bryter: str | None = None
    terskel_w: float = DEFAULT_LAST_TERSKEL_W


@dataclass(frozen=True)
class LastAvlesning:
    """Rå avlesning av en last: hva sensoren sier, og hvor bryteren står.

    `effekt_w` er None når sensoren er unavailable, unknown eller ulesbar. Det
    er noe annet enn 0 W: da vet vi ikke hva lasten trekker. `bryter_paa` er
    None både når lasten ikke har bryter og når bryteren ikke svarer.
    """

    oppsett: LastOppsett
    effekt_w: float | None
    bryter_paa: bool | None = None
    friendly_name: str | None = None


@dataclass
class KuttSporing:
    """Det coordinatoren husker om en last fra ett tick til det neste.

    Mutabel med vilje: dette er tilstand over tid, ikke en avlesning. Nøkkelen
    i sporingsdicten er effektsensoren, som er unik per last.
    """

    forrige_bryter_paa: bool | None = None
    siste_effekt_paa_w: float | None = None
    kuttet_siden: datetime | None = None
    kuttet_effekt_w: float | None = None


@dataclass(frozen=True)
class KuttKilde:
    """En kuttbar last slik den ser ut akkurat nå.

    Feltnavnene er nøklene i attributtet `kutt_kilder`, og er kontrakt mot
    dashbordet, kortet og varsel-blueprinten.
    """

    entity_id: str
    navn: str | None
    effekt_w: float | None
    teller_med: bool
    terskel_w: float
    bryter: str | None
    bryter_paa: bool | None
    kuttet: bool
    kuttet_siden: str | None


# --- konfigurasjon ----------------------------------------------------------


def _terskel(raa: Any) -> float:
    """Terskelen i W, med defaulten når feltet mangler eller er søppel."""
    try:
        verdi = float(raa)
    except (TypeError, ValueError):
        return DEFAULT_LAST_TERSKEL_W
    return verdi if verdi >= 0 else DEFAULT_LAST_TERSKEL_W


def _tekst(raa: Any) -> str | None:
    """En streng med innhold, eller None. Tomt felt og manglende felt er det samme."""
    if not isinstance(raa, str):
        return None
    strippet = raa.strip()
    return strippet or None


def les_laster(raa: object) -> list[LastOppsett]:
    """Lastelisten fra config entryen, som `LastOppsett`.

    Oppføringer uten effektsensor hoppes over framfor å velte oppsettet: en
    last uten sensor har ingenting å bidra med, og en config entry skal kunne
    leses selv om noe har blitt skrevet feil inn i den.
    """
    if not isinstance(raa, list):
        return []
    laster: list[LastOppsett] = []
    for post in raa:
        if not isinstance(post, dict):
            continue
        sensor = _tekst(post.get(CONF_LAST_EFFEKT_SENSOR))
        if sensor is None:
            continue
        laster.append(
            LastOppsett(
                effekt_sensor=sensor,
                navn=_tekst(post.get(CONF_LAST_NAVN)),
                bryter=_tekst(post.get(CONF_LAST_BRYTER)),
                terskel_w=_terskel(post.get(CONF_LAST_TERSKEL_W)),
            )
        )
    return laster


def last_til_lagring(last: LastOppsett) -> dict[str, Any]:
    """`LastOppsett` som den skal stå i config entryen.

    Tomme valgfrie felt utelates framfor å lagres som null, slik at en entry
    ikke bærer på spøkelser av felt brukeren har tømt.
    """
    post: dict[str, Any] = {
        CONF_LAST_EFFEKT_SENSOR: last.effekt_sensor,
        CONF_LAST_TERSKEL_W: last.terskel_w,
    }
    if last.navn:
        post[CONF_LAST_NAVN] = last.navn
    if last.bryter:
        post[CONF_LAST_BRYTER] = last.bryter
    return post


# --- migrering fra strategi-oppsettet ---------------------------------------
#
# Disse tre nøklene og de to tersklene er det som stod i config entries fram til
# entry-versjon 2. De bor her og ikke i const.py fordi de bare finnes for
# migreringens skyld: ingen kode skal lese dem, og ingen ny entry skal få dem.

LEGACY_CONF_VVB_POWER_SENSOR = "vvb_power_sensor"
LEGACY_CONF_EKSTRA_POWER_SENSORS = "ekstra_power_sensors"
LEGACY_CONF_KUTT_STRATEGI = "kutt_strategi"

LEGACY_VVB_TERSKEL_W = 1000.0
LEGACY_EKSTRA_TERSKEL_W = 100.0


def migrer_til_laster(data: Mapping[str, Any]) -> dict[str, Any]:
    """Entry-data fra versjon 1 om til en lasteliste.

    Strategien leses ikke. Den styrte bare hvilke av de konfigurerte sensorene
    `tilgjengelig_kutt` talte med, og en sensor brukeren faktisk har pekt på er
    en last han har, uansett hva dropdownen stod på. Hadde vi latt strategien
    bestemme, ville en bruker med `blind` mistet sensorene sine i migreringen.

    Terskelen følger den rollen sensoren hadde: 1000 W for den som stod som
    VVB-sensor, 100 W for ekstra-sensorene. Da regner `tilgjengelig_kutt`
    akkurat det samme etterpå som før.

    Navn settes ikke. Det gamle oppsettet hadde ingen, og et navn utledet av
    entitets-id-en hadde vært verre enn sensorens eget friendly_name.
    Bryteren settes heller ikke: den fantes ikke å migrere fra, og må legges
    til under Configure av den som vil at integrasjonen skal se kuttene sine.
    """
    ny = dict(data)
    for noekkel in (LEGACY_CONF_VVB_POWER_SENSOR, LEGACY_CONF_EKSTRA_POWER_SENSORS, LEGACY_CONF_KUTT_STRATEGI):
        ny.pop(noekkel, None)

    laster: list[dict[str, Any]] = list(ny.get(CONF_LASTER) or [])
    kjent = {post.get(CONF_LAST_EFFEKT_SENSOR) for post in laster}

    def legg_til(sensor: object, terskel: float) -> None:
        navn = _tekst(sensor)
        if navn is None or navn in kjent:
            return
        kjent.add(navn)
        laster.append({CONF_LAST_EFFEKT_SENSOR: navn, CONF_LAST_TERSKEL_W: terskel})

    legg_til(data.get(LEGACY_CONF_VVB_POWER_SENSOR), LEGACY_VVB_TERSKEL_W)
    for sensor in data.get(LEGACY_CONF_EKSTRA_POWER_SENSORS) or []:
        legg_til(sensor, LEGACY_EKSTRA_TERSKEL_W)

    if laster:
        ny[CONF_LASTER] = laster
    return ny


# --- hva som teller nå ------------------------------------------------------


def teller_med(*, effekt_w: float | None, terskel_w: float) -> bool:
    """Om lasten bidrar til tilgjengelig kutt akkurat nå.

    To ting må stemme: sensoren må ha en lesbar verdi, og verdien må ligge
    over lastens egen terskel. Nøyaktig på terskelen holder ikke.
    """
    return effekt_w is not None and effekt_w > terskel_w


def visningsnavn(avlesning: LastAvlesning) -> str | None:
    """Navnet brukeren gav lasten, ellers sensorens eget friendly_name."""
    return avlesning.oppsett.navn or avlesning.friendly_name


def build_kutt_kilder(
    *,
    avlesninger: list[LastAvlesning],
    sporing: Mapping[str, KuttSporing] | None = None,
) -> list[KuttKilde]:
    """Gjør avlesningene om til `kutt_kilder`-oppføringer.

    Alle konfigurerte laster er med, også de som ikke teller akkurat nå.
    Forskjellen mellom «finnes ikke» og «teller ikke nå» er nettopp det som er
    verdt å se på et dashbord.
    """
    spor = sporing or {}
    kilder = []
    for a in avlesninger:
        s = spor.get(a.oppsett.effekt_sensor)
        kuttet_siden = None if s is None else s.kuttet_siden
        kilder.append(
            KuttKilde(
                entity_id=a.oppsett.effekt_sensor,
                navn=visningsnavn(a),
                effekt_w=None if a.effekt_w is None else round(a.effekt_w, 1),
                teller_med=teller_med(effekt_w=a.effekt_w, terskel_w=a.oppsett.terskel_w),
                terskel_w=a.oppsett.terskel_w,
                bryter=a.oppsett.bryter,
                bryter_paa=a.bryter_paa,
                kuttet=kuttet_siden is not None,
                kuttet_siden=None if kuttet_siden is None else kuttet_siden.isoformat(),
            )
        )
    return kilder


def compute_tilgjengelig_kutt_kw(avlesninger: list[LastAvlesning]) -> float | None:
    """Summen av lastene som teller med akkurat nå, i kW.

    None når ingen laster er konfigurert. Da finnes det ikke noe svar, og et
    tall ville vært et anslag ingen har bedt om: fram til september 2026 stod
    sensoren på 0,3 kW for alle som ikke hadde valgt en strategi, og det tallet
    var en antagelse om en varmtvannsbereder ingen visste om brukeren hadde.

    Summen går over nøyaktig de lastene som får `teller_med` i `kutt_kilder`,
    så de to tallene kan ikke drifte fra hverandre.
    """
    if not avlesninger:
        return None
    total_w = sum(
        a.effekt_w
        for a in avlesninger
        if a.effekt_w is not None and teller_med(effekt_w=a.effekt_w, terskel_w=a.oppsett.terskel_w)
    )
    return total_w / 1000.0


# --- hva som faktisk ble kuttet ---------------------------------------------


@dataclass(frozen=True)
class KuttObservasjon:
    """En last som nettopp gikk av, eller nettopp kom tilbake.

    `effekt_w` er det lasten trakk sist den stod på, altså hva kuttet er verdt.
    `varighet_s` er satt bare på `gjenopptatt`.
    """

    entity_id: str
    navn: str | None
    kuttet: bool
    effekt_w: float | None = None
    varighet_s: float | None = None


def oppdater_kuttsporing(
    *,
    sporing: dict[str, KuttSporing],
    avlesninger: list[LastAvlesning],
    kutt_anbefalt: bool,
    now: datetime,
) -> list[KuttObservasjon]:
    """Oppdater sporingen og si fra om lastene som skiftet stilling.

    Regelen for at et kutt er vårt: bryteren gikk fra på til av i et tick der
    kutt var anbefalt. Går den av mens Effektvakt melder god margin, var det
    noen andre, og da skal verken hendelsesloggen eller sparesensoren senere
    regne det som en innsparing.

    En bryter som ikke svarer (`bryter_paa` er None) endrer ingenting. Da vet
    vi ikke hva som skjedde, og å gjette ville gitt et kutt eller en
    gjenopptakelse som aldri fant sted. Laster uten bryter spores ikke: der er
    det ingenting å observere.
    """
    levende = {a.oppsett.effekt_sensor for a in avlesninger if a.oppsett.bryter}
    for noekkel in [k for k in sporing if k not in levende]:
        del sporing[noekkel]

    observasjoner: list[KuttObservasjon] = []
    for a in avlesninger:
        if not a.oppsett.bryter:
            continue
        s = sporing.setdefault(a.oppsett.effekt_sensor, KuttSporing())
        if a.bryter_paa is None:
            continue

        if a.bryter_paa:
            if s.kuttet_siden is not None:
                observasjoner.append(
                    KuttObservasjon(
                        entity_id=a.oppsett.effekt_sensor,
                        navn=visningsnavn(a),
                        kuttet=False,
                        effekt_w=s.kuttet_effekt_w,
                        varighet_s=(now - s.kuttet_siden).total_seconds(),
                    )
                )
            s.kuttet_siden = None
            s.kuttet_effekt_w = None
            if a.effekt_w is not None:
                s.siste_effekt_paa_w = a.effekt_w
        elif s.forrige_bryter_paa and kutt_anbefalt and s.kuttet_siden is None:
            s.kuttet_siden = now
            s.kuttet_effekt_w = s.siste_effekt_paa_w
            observasjoner.append(
                KuttObservasjon(
                    entity_id=a.oppsett.effekt_sensor,
                    navn=visningsnavn(a),
                    kuttet=True,
                    effekt_w=s.kuttet_effekt_w,
                )
            )

        s.forrige_bryter_paa = a.bryter_paa

    return observasjoner
