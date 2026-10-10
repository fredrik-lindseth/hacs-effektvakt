"""Kompakte lastprofiler og forventet energi; ingaen HA- eller recorder-import."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .profilestimat import beregn_kuttenergi
from .tid import tidslinje

if TYPE_CHECKING:
    from datetime import datetime

    from .laster import LastAvlesning
    from .lastprofil import Lastprofil


@dataclass
class Lastprofiler:
    """Observer paakanter uten aa gjette alder ved oppstart eller etter hull."""

    forrige_paa: dict[str, bool | None] = field(default_factory=dict)
    paa_siden: dict[str, datetime | None] = field(default_factory=dict)

    def beregn(
        self,
        avlesninger: list[LastAvlesning],
        *,
        now: datetime,
        resttid_s: float,
        profiler: dict[str, Lastprofil],
        oppdatert: datetime | None = None,
        status: str = "ikke_hentet",
        egne_kutt: set[str] | None = None,
        sperret: set[str] | None = None,
    ) -> dict[str, Any]:
        """Kun valgte profiler summeres; ukjent del gir ukjent sum.

        Raadenergi bruker bare kjente, aktive wattmaalinger. Manuelle profiler
        uten maaling gir planlegging i sensoren, aldri tilgjengelig raadenergi.
        Ikke-profilerte laster beholder dagens antakelse om resten av timen.
        """
        egne = egne_kutt or set()
        sperrede = sperret or set()
        kilder: dict[str, dict[str, Any]] = {}
        energi: list[float | None] = []
        raadenergi = 0.0
        for a in avlesninger:
            last = a.oppsett
            key = last.noekkel
            effekt = a.effekt_w
            paa = None if effekt is None else effekt > last.terskel_w
            if key in egne or key in sperrede:
                self.paa_siden[key] = None
                self.forrige_paa[key] = None
            elif paa is None or paa is False:
                self.paa_siden[key] = None
            elif self.forrige_paa.get(key) is False:
                self.paa_siden[key] = now
            if key not in egne and key not in sperrede:
                self.forrige_paa[key] = paa
            if last.profil == "av":
                if paa and effekt is not None and key not in egne and key not in sperrede:
                    raadenergi += effekt / 1000 * resttid_s / 3600
                continue
            siden = self.paa_siden.get(key)
            alder = max(0.0, (tidslinje(now) - tidslinje(siden)).total_seconds()) if siden else None
            profil = profiler.get(last.effekt_sensor) if last.profil == "auto" else None
            utdatert = bool(oppdatert and (tidslinje(now) - tidslinje(oppdatert)).total_seconds() > 24 * 3600)
            estimat = beregn_kuttenergi(
                maalt_w=0.0 if paa is False else effekt,
                resttid_s=resttid_s,
                profil=None if utdatert else profil,
                nominell_w=last.nominell_w,
                duty=last.arbeidssyklus_pct / 100 if last.arbeidssyklus_pct is not None else None,
                typisk_paa_minutter=last.typisk_paa_minutter,
                allerede_paa_s=alder,
                maks_kutt_s=0 if key in sperrede else last.maks_kutt_minutter * 60,
                egen_kuttet=key in egne,
            )
            energi.append(estimat.kwh)
            if paa and not estimat.planleggingsestimat and estimat.kwh is not None:
                raadenergi += estimat.kwh
            grunnlag = profil.tidsgrunnlag if profil else None

            def avrund(verdi: float | None) -> float | None:
                return round(verdi, 3) if verdi is not None else None

            kilder[key] = {
                "profil": last.profil,
                "kilde": estimat.kilde,
                "datagrunnlag": estimat.datagrunnlag,
                "planleggingsestimat": estimat.planleggingsestimat,
                "arbeidssyklus_pct": avrund(grunnlag.aktiv_andel * 100)
                if grunnlag and grunnlag.aktiv_andel is not None
                else last.arbeidssyklus_pct,
                "aktiv_effekt_w": avrund(grunnlag.middel_aktiv_w) if grunnlag else last.nominell_w,
                "dekning_pct": avrund(grunnlag.dekning * 100) if grunnlag else None,
                "hele_sykluser": len(profil.hele_varigheter_s) if profil else 0,
                "oppdatert": oppdatert.isoformat() if last.profil == "auto" and oppdatert else None,
                "historikk_status": ("historikk_utdatert" if utdatert else status)
                if last.profil == "auto"
                else "manuell",
                "periode_start": profil.intervaller[0].start.isoformat() if profil and profil.intervaller else None,
                "periode_slutt": profil.intervaller[-1].slutt.isoformat() if profil and profil.intervaller else None,
                "estimert_kuttenergi_kwh": avrund(estimat.kwh),
                "forventet_drift_minutter": avrund(estimat.forventet_drift_s / 60)
                if estimat.forventet_drift_s is not None
                else None,
                "stoette_antall": estimat.stoette_antall,
                "sensurerte_antall": estimat.sensurerte_antall,
                "maks_kutt_minutter": last.maks_kutt_minutter,
            }
        return {
            "estimert_kuttenergi_resten_av_timen_kwh": round(sum(e for e in energi if e is not None), 4)
            if energi and all(e is not None for e in energi)
            else None,
            "lastprofiler": kilder,
            "profiler_antall": len(energi),
            "profiler_ukjente": sum(e is None for e in energi),
            "laster_uten_profil": len(avlesninger) - len(energi),
            "profilraad_energi_kwh": raadenergi,
        }
