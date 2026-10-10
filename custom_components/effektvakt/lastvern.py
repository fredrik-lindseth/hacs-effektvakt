"""Vedvarende eierskap og fristslipp for lastkutt fra blueprintene.

Automasjoner kan avbrytes og lastes paa nytt. Derfor eier denne vakten
originaltilstand, frist og minste paatid, og skriver dem foer lasten kuttes.
Vakten lever til HA stopper, ogsaa ved reload/fjerning av et config entry:
et allerede overtatt ansvar for gjeninnkobling maa fullfoeres.
"""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, EVENT_STATE_CHANGED
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_point_in_utc_time, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import Event, HomeAssistant, ServiceCall

_LOGGER = logging.getLogger(__name__)
DATA_LASTVERN = f"{DOMAIN}_lastvern"
SERVICE_STYR_LAST = "styr_last"

SKJEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("eier"): cv.entity_id,
        vol.Required("kutt"): cv.boolean,
        vol.Optional("automatikk_switch", default=""): vol.Any("", cv.entity_id),
        vol.Optional("max_off_minutes", default=60): vol.All(vol.Coerce(float), vol.Range(min=1, max=240)),
        vol.Optional("min_on_minutes", default=5): vol.All(vol.Coerce(float), vol.Range(min=1, max=30)),
        vol.Optional("min_temp", default=10): vol.All(vol.Coerce(float), vol.Range(min=5, max=30)),
    }
)


@dataclass
class Lastkutt:
    """Ett overtatt ansvar. Fristene er UTC-sekunder, ogsaa rundt sommertid."""

    eier: str
    frist: float
    min_paatid: float
    original: float | None = None
    kutt_temp: float | None = None
    slipp: bool = False
    start: float | None = None


class Lastvern:
    """Serialiser forespoersler, og behold eierskap til restore er bekreftet."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.store = Store[dict[str, Any]](hass, 1, DATA_LASTVERN)
        self.kutt: dict[str, Lastkutt] = {}
        self.tidligst_kutt: dict[str, float] = {}
        self._profilkutt: dict[str, list[tuple[float, float]]] = {}
        self._laas = asyncio.Lock()
        self._avmeld: list[Callable[[], None]] = []
        self._avmeld_frist: Callable[[], None] | None = None
        self._avmeld_stopp: Callable[[], None] | None = None

    async def async_start(self) -> None:
        """Les eierskap fra disk; etter HA-start slipper vi alle gamle kutt."""
        lagret = await self.store.async_load() or {}
        for entity_id, rad in lagret.get("kutt", {}).items():
            try:
                kutt = Lastkutt(**rad)
                if not math.isfinite(kutt.frist) or not math.isfinite(kutt.min_paatid):
                    raise ValueError("ugyldig frist")
                if kutt.start is not None and not math.isfinite(kutt.start):
                    raise ValueError("ugyldig kuttstart")
                if not entity_id.startswith(("switch.", "climate.")):
                    raise ValueError("ugyldig last")
                kutt.slipp = True
                self.kutt[entity_id] = kutt
            except (TypeError, ValueError):
                _LOGGER.warning("Ignorerer ugyldig lagret lastkutt for %s", entity_id)
        self.tidligst_kutt = {
            entity_id: float(verdi)
            for entity_id, verdi in lagret.get("tidligst_kutt", {}).items()
            if isinstance(verdi, (int, float)) and math.isfinite(verdi)
        }
        for entity_id, vinduer in lagret.get("profilkutt", {}).items():
            if not entity_id.startswith(("switch.", "climate.")) or not isinstance(vinduer, list):
                continue
            for vindu in vinduer:
                if not isinstance(vindu, (list, tuple)) or len(vindu) != 2:
                    continue
                fra, til = vindu
                if (
                    all(isinstance(t, (int, float)) and not isinstance(t, bool) and math.isfinite(t) for t in vindu)
                    and fra < til
                ):
                    self._noter_profilkutt(entity_id, fra, til)
        self._rydd_profilkutt(dt_util.utcnow().timestamp())
        self._avmeld = [
            async_track_time_interval(self.hass, self.async_sjekk, timedelta(seconds=30)),
            self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._async_endret),
        ]
        self._avmeld_stopp = self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._stopp)
        await self.async_sjekk()

    def _stopp(self, _event: Event | None = None) -> None:
        """Fjern callbacks, men behold lagret ansvar til neste oppstart."""
        if self._avmeld_stopp is not None and _event is None:
            self._avmeld_stopp()
        self._avmeld_stopp = None
        for avmeld in self._avmeld:
            avmeld()
        self._avmeld.clear()
        if self._avmeld_frist:
            self._avmeld_frist()
            self._avmeld_frist = None

    def _planlegg_frist(self) -> None:
        if self._avmeld_frist:
            self._avmeld_frist()
            self._avmeld_frist = None
        framtid = [k.frist for k in self.kutt.values() if not k.slipp]
        if framtid:
            self._avmeld_frist = async_track_point_in_utc_time(
                self.hass, self.async_sjekk, datetime.fromtimestamp(min(framtid), UTC)
            )

    def _rydd_profilkutt(self, naa: float) -> None:
        grense = naa - timedelta(days=7).total_seconds()
        self._profilkutt = {
            aktuator: [(max(fra, grense), til) for fra, til in vinduer if til > grense]
            for aktuator, vinduer in self._profilkutt.items()
            if any(til > grense for _, til in vinduer)
        }

    def _noter_profilkutt(self, aktuator: str, start: float, slutt: float) -> None:
        if slutt <= start:
            return
        vinduer = sorted([*self._profilkutt.get(aktuator, []), (start, slutt)])
        sammenslaatt: list[tuple[float, float]] = []
        for fra, til in vinduer:
            if sammenslaatt and fra <= sammenslaatt[-1][1]:
                sammenslaatt[-1] = (sammenslaatt[-1][0], max(til, sammenslaatt[-1][1]))
            else:
                sammenslaatt.append((fra, til))
        self._profilkutt[aktuator] = sammenslaatt

    def profilvinduer(self, aktuator: str, naa: datetime) -> list[tuple[datetime, datetime]]:
        """Egne kutt til profilinnleseren, inkludert uavklart restore.

        Gamle lagrede ansvar mangler start. Da utelates konservativt hele
        syvdagersvinduet fram til restore; fristen brukes aldri som kuttstart.
        """
        if naa.tzinfo is None:
            raise ValueError("Profilvinduer krever tidssone")
        slutt = naa.timestamp()
        self._rydd_profilkutt(slutt)
        grense = slutt - timedelta(days=7).total_seconds()
        vinduer = list(self._profilkutt.get(aktuator, []))
        if (kutt := self.kutt.get(aktuator)) is not None:
            start = max(grense, kutt.start if kutt.start is not None else grense)
            if start < slutt:
                vinduer.append((start, slutt))
        return [
            (datetime.fromtimestamp(fra, UTC), datetime.fromtimestamp(min(til, slutt), UTC))
            for fra, til in vinduer
            if fra < min(til, slutt)
        ]

    async def _lagre(self) -> None:
        self._rydd_profilkutt(dt_util.utcnow().timestamp())
        await self.store.async_save(
            {
                "kutt": {entity_id: asdict(kutt) for entity_id, kutt in self.kutt.items()},
                "tidligst_kutt": self.tidligst_kutt,
                "profilkutt": self._profilkutt,
            }
        )
        self._planlegg_frist()

    async def _async_endret(self, event: Event) -> None:
        if event.data.get("entity_id") in self.kutt:
            await self.async_sjekk()

    async def async_sjekk(self, _now: datetime | None = None) -> None:
        """Fristslipp og nye forsoek naar en utilgjengelig aktuator kommer tilbake."""
        async with self._laas:
            for entity_id, kutt in list(self.kutt.items()):
                if kutt.slipp or dt_util.utcnow().timestamp() >= kutt.frist:
                    kutt.slipp = True
                    await self._slipp(entity_id, kutt)

    async def _slipp(self, entity_id: str, kutt: Lastkutt) -> None:
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return
        domain = entity_id.split(".")[0]
        if domain == "switch":
            ferdig = state.state == "on"
            service = "turn_on"
            data: dict[str, Any] = {"entity_id": entity_id}
        else:
            temperatur = state.attributes.get("temperature")
            if not isinstance(temperatur, (int, float)) or not math.isfinite(temperatur):
                return
            # Et nytt manuelt setpunkt er brukerens valg, ikke noe vi skal angre.
            ferdig = temperatur != kutt.kutt_temp
            service = "set_temperature"
            data = {"entity_id": entity_id, "temperature": kutt.original}
        if not ferdig:
            try:
                await self.hass.services.async_call(domain, service, data, blocking=True)
            except HomeAssistantError as err:
                _LOGGER.warning("Kan ikke gjenopprette %s, proever igjen: %s", entity_id, err)
                return
            state = self.hass.states.get(entity_id)
            ferdig = (
                state is not None
                and state.state not in ("unknown", "unavailable")
                and (
                    state.state == "on" if domain == "switch" else state.attributes.get("temperature") == kutt.original
                )
            )
        if ferdig:
            naa = dt_util.utcnow().timestamp()
            start = kutt.start if kutt.start is not None else naa - timedelta(days=7).total_seconds()
            self._noter_profilkutt(entity_id, start, naa)
            self.tidligst_kutt[entity_id] = dt_util.utcnow().timestamp() + kutt.min_paatid
            del self.kutt[entity_id]
            await self._lagre()

    async def async_styr(self, call: ServiceCall) -> None:
        """Be om kutt eller slipp. Gjentatte kutt forlenger aldri fristen."""
        async with self._laas:
            data = call.data
            entity_id = data["entity_id"]
            eier = data["eier"]
            domain = entity_id.split(".")[0]
            if domain not in ("switch", "climate"):
                raise ServiceValidationError(
                    "Lastvern støtter bare switch og climate",
                    translation_domain=DOMAIN,
                    translation_key="lastvern_ugyldig_last",
                )
            if not eier.startswith("automation."):
                raise ServiceValidationError(
                    "Eier må være automasjonen som ber om kuttet",
                    translation_domain=DOMAIN,
                    translation_key="lastvern_ugyldig_eier",
                )
            kutt = self.kutt.get(entity_id)
            if kutt is not None and kutt.eier != eier:
                raise ServiceValidationError(
                    f"{entity_id} styres allerede av {kutt.eier}",
                    translation_domain=DOMAIN,
                    translation_key="lastvern_opptatt",
                    translation_placeholders={"entity_id": entity_id, "eier": kutt.eier},
                )
            automatikk = data["automatikk_switch"]
            skal_kutte = data["kutt"] and (not automatikk or self.hass.states.is_state(automatikk, "on"))
            naa = dt_util.utcnow()
            if kutt is not None:
                if not skal_kutte or kutt.slipp or naa.timestamp() >= kutt.frist:
                    kutt.slipp = True
                    await self._lagre()
                    await self._slipp(entity_id, kutt)
                return
            if not skal_kutte or naa.timestamp() < self.tidligst_kutt.get(entity_id, 0):
                return
            state = self.hass.states.get(entity_id)
            if state is None or state.state in ("unknown", "unavailable", "off"):
                return
            original = None
            kutt_temp = None
            if domain == "switch" and state.state != "on":
                return
            if domain == "climate":
                original = state.attributes.get("temperature")
                kutt_temp = data["min_temp"]
                if not isinstance(original, (int, float)) or not math.isfinite(original) or original <= kutt_temp:
                    return
            frist = min(
                naa.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1),
                naa + timedelta(minutes=data["max_off_minutes"]),
            )
            kutt = Lastkutt(
                eier, frist.timestamp(), data["min_on_minutes"] * 60, original, kutt_temp, start=naa.timestamp()
            )
            self.kutt[entity_id] = kutt
            # Ansvar foer handling: ogsaa stroembrudd rett etter turn_off maa kunne rettes.
            await self._lagre()
            service = "turn_off" if domain == "switch" else "set_temperature"
            service_data: dict[str, Any] = {"entity_id": entity_id}
            if domain == "climate":
                service_data["temperature"] = kutt_temp
            try:
                await self.hass.services.async_call(domain, service, service_data, blocking=True)
            except HomeAssistantError:
                # Utfallet kan vaere uvisst selv om tjenesten feilet. Behold ansvaret.
                kutt.slipp = True
                await self._lagre()
                raise


async def async_setup_lastvern(hass: HomeAssistant) -> None:
    """En vakt per HA, uavhengig av blueprint- og config-entry-reload."""
    if DATA_LASTVERN in hass.data:
        return
    vern = Lastvern(hass)
    hass.data[DATA_LASTVERN] = vern
    await vern.async_start()
    hass.services.async_register(DOMAIN, SERVICE_STYR_LAST, vern.async_styr, schema=SKJEMA)
