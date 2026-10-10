"""Hent lastprofiler fra recorder uten databasearbeid i coordinatorens tick.

Dekning beskriver registrerte tilstander, ikke sensorens rapporteringshelse.
Egne kutt maskeres som ukjent tid slik at de ikke laerer korte natursykluser.
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import TYPE_CHECKING

from .lastprofil import Effektpunkt, Lastprofil, analyser_lastprofil

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from homeassistant.core import HomeAssistant, State

_LOGGER = logging.getLogger(__name__)
_PERIODE = timedelta(days=7)


def _watt(state: State) -> float | None:
    try:
        verdi = float(state.state)
    except (TypeError, ValueError):
        return None
    enhet = state.attributes.get("unit_of_measurement")
    if enhet not in ("W", "kW") or not math.isfinite(verdi) or verdi < 0:
        return None
    return verdi * (1000 if enhet == "kW" else 1)


class Profilhistorikk:
    """Syvdagers snapshot; kall oppdatering i bakgrunnen, normalt hver time.

    Klassen eier ingen timer eller tasks. Entry-livssyklusen eier oppdatering
    og avbryting. Profiler og oppdatert byttes foerst etter en hel innlesing.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.profiler: dict[str, Lastprofil] = {}
        self.oppdatert: datetime | None = None
        self.status = "ikke_hentet"
        self._kutt: dict[str, list[tuple[datetime, datetime]]] = {}

    def noter_kutt(self, sensor: str, start: datetime, slutt: datetime) -> None:
        """Masker et kjent styrt kutt, ogsaa i allerede innlest profil."""
        if start.tzinfo is None or slutt.tzinfo is None or slutt <= start:
            raise ValueError("Kuttintervallet maa ha tidssone og positiv varighet")
        start, slutt = start.astimezone(UTC), slutt.astimezone(UTC)
        vinduer = sorted([*self._kutt.get(sensor, []), (start, slutt)])
        sammenslaatt: list[tuple[datetime, datetime]] = []
        for fra, til in vinduer:
            if sammenslaatt and fra <= sammenslaatt[-1][1]:
                sammenslaatt[-1] = (sammenslaatt[-1][0], max(til, sammenslaatt[-1][1]))
            else:
                sammenslaatt.append((fra, til))
        self._kutt[sensor] = sammenslaatt
        if (profil := self.profiler.get(sensor)) is not None:
            punkter = [Effektpunkt(i.start, i.watt) for i in profil.intervaller]
            self.profiler[sensor] = analyser_lastprofil(
                punkter,
                start=profil.intervaller[0].start,
                slutt=profil.intervaller[-1].slutt,
                terskel_w=profil.terskel_w,
                ekskluderte_vinduer=[(start, slutt)],
            )

    async def async_oppdater(
        self,
        terskler: Mapping[str, float],
        *,
        naa: datetime | None = None,
        utelatte_intervaller: Mapping[str, Sequence[tuple[datetime, datetime]]] | None = None,
    ) -> None:
        """Hent starttilstand, maalehull og alle effektendringer paa executor."""
        slutt = naa or datetime.now(UTC)
        if slutt.tzinfo is None:
            raise ValueError("Analyseperioden maa ha tidssone")
        slutt = slutt.astimezone(UTC)
        start = slutt - _PERIODE
        for sensor, intervaller in (utelatte_intervaller or {}).items():
            for fra, til in intervaller:
                self.noter_kutt(sensor, fra, til)
        self._kutt = {s: [(a, b) for a, b in vinduer if b > start] for s, vinduer in self._kutt.items()}
        if not terskler:
            self.profiler = {}
            self.oppdatert = slutt
            self.status = "ingen_sensorer"
            return
        if "recorder" not in self.hass.config.components:
            self.profiler = {}
            self.status = "recorder_mangler"
            return
        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.history import get_significant_states

            # Normal State beholder enheter ved hver endring, ogsaa W -> kW.
            resultat = await get_instance(self.hass).async_add_executor_job(
                partial(
                    get_significant_states,
                    self.hass,
                    start,
                    slutt,
                    entity_ids=list(terskler),
                    include_start_time_state=True,
                    significant_changes_only=False,
                    minimal_response=False,
                )
            )
            profiler = {}
            for sensor, terskel in terskler.items():
                # last_updated bevarer effekt- og enhetsendringer. Flere
                # recorder-rader med samme tidspunkt bruker den siste raden.
                observasjoner = {s.last_updated.astimezone(UTC): _watt(s) for s in resultat.get(sensor, [])}
                punkter = [Effektpunkt(t, w) for t, w in sorted(observasjoner.items())]
                profiler[sensor] = analyser_lastprofil(
                    punkter, start=start, slutt=slutt, terskel_w=terskel, ekskluderte_vinduer=self._kutt.get(sensor, [])
                )
        except Exception:  # Recorder kan vaere paa vei opp eller stengt under unload.
            _LOGGER.warning("Kunne ikke oppdatere lastprofiler fra recorder", exc_info=True)
            self.status = "historikk_feilet"
            return
        self.profiler = profiler
        self.oppdatert = slutt
        self.status = "klar"
