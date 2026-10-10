"""Forventet kuttenergi fra maalt effekt og historisk eller manuell drift.

Estimatet gjelder det avgrensede tidsvinduet, ikke sparte kroner eller en
garanti om lastens behov. Uten effektmaaling er resultatet bare planlegging.
Historiske hele sykluser brukes betinget paa kjent alder, eller tidsvektet
ved tilfeldig fase naar alderen er ukjent. Sensurering kan skjevfordele
utvalget mot korte sykluser; stoette og datagrunnlag maa foelge estimatet.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .lastprofil import Lastprofil


@dataclass(frozen=True)
class KuttenergiEstimat:
    kilde: str
    datagrunnlag: str
    kwh: float | None
    forventet_drift_s: float | None
    stoette_antall: int
    sensurerte_antall: int
    vindu_s: float
    planleggingsestimat: bool


def _varighet(verdi: float, navn: str) -> None:
    if not math.isfinite(verdi) or verdi < 0:
        raise ValueError(f"{navn} maa vaere endelig og ikke-negativ")


def _tilfeldig_fase(varigheter: tuple[float, ...], vindu_s: float) -> float:
    """Forventet min(resttid, vindu) ved tilfeldig observasjon mens lasten er paa.

    Lange sykluser blir observert oftere, derfor deles integralet over
    syklusene paa samlet paatid, ikke antall sykluser.
    """
    total = sum(varigheter)
    return sum(min(t, vindu_s) * ((t - min(t, vindu_s) / 2) / total) for t in varigheter)


def beregn_kuttenergi(
    *,
    maalt_w: float | None,
    resttid_s: float,
    profil: Lastprofil | None = None,
    nominell_w: float | None = None,
    duty: float | None = None,
    typisk_paa_minutter: float | None = None,
    allerede_paa_s: float | None = None,
    maks_kutt_s: float | None = None,
    egen_kuttet: bool = False,
) -> KuttenergiEstimat:
    """Forventet energi som kan utsettes i resten av timen, innen tillatt avtid.

    ``duty`` er en andel fra 0 til 1. Aktiv maaling kan ikke ganges med
    ubetinget duty: lasten er allerede paa. Da kreves hele historiske
    sykluser eller en uttrykkelig antatt typisk paatid. Uten maaling brukes
    manuell nominell effekt/duty, ellers historisk aktiv effekt/andel.

    Manuell modus velges ved aa utelate ``profil``. Ved aktiv maaling har
    anvendelige historiske sykluser prioritet over manuell typisk paatid.
    Allerede kuttet last gir aldri ny tilgjengelig kuttenergi.
    """
    _varighet(resttid_s, "Resttid")
    if maks_kutt_s is not None:
        _varighet(maks_kutt_s, "Maksimal avtid")
    if allerede_paa_s is not None:
        _varighet(allerede_paa_s, "Allerede paatid")
    if nominell_w is not None and (not math.isfinite(nominell_w) or nominell_w <= 0):
        raise ValueError("Nominell effekt maa vaere endelig og positiv")
    if duty is not None and (not math.isfinite(duty) or not 0 <= duty <= 1):
        raise ValueError("Duty maa vaere en endelig andel fra 0 til 1")
    if typisk_paa_minutter is not None and (not math.isfinite(typisk_paa_minutter) or typisk_paa_minutter <= 0):
        raise ValueError("Typisk paatid maa vaere endelig og positiv")
    if maalt_w is not None and (not math.isfinite(maalt_w) or maalt_w < 0):
        maalt_w = None
    vindu = min(resttid_s, maks_kutt_s) if maks_kutt_s is not None else resttid_s
    sensurerte = sum(not p.hel for p in profil.aktive_perioder) if profil else 0
    planlegging = maalt_w is None

    def resultat(
        kilde: str, grunnlag: str, drift: float | None, effekt: float | None, stoette: int = 0
    ) -> KuttenergiEstimat:
        return KuttenergiEstimat(
            kilde,
            grunnlag,
            effekt / 1000 * (drift / 3600) if effekt is not None and drift is not None else None,
            drift,
            stoette,
            sensurerte,
            vindu,
            planlegging and kilde not in ("egen_kuttet", "ingen_tid"),
        )

    if egen_kuttet:
        return resultat("egen_kuttet", "eierskap", 0, 0)
    if vindu == 0:
        return resultat("ingen_tid", "tidsgrense", 0, 0)
    if maalt_w == 0 or (maalt_w is not None and profil is not None and maalt_w <= profil.terskel_w):
        return resultat("maalt_av", "maalt", 0, 0)
    if maalt_w is None:
        if nominell_w is not None and duty is not None:
            return resultat("manuell_duty", "manuelt", duty * vindu, nominell_w)
        if profil is not None:
            tidsgrunnlag = profil.tidsgrunnlag
            if tidsgrunnlag.aktiv_andel is not None:
                return resultat(
                    "historisk_duty",
                    "lavt",
                    tidsgrunnlag.aktiv_andel * vindu,
                    tidsgrunnlag.middel_aktiv_w if tidsgrunnlag.middel_aktiv_w is not None else 0,
                    len(profil.hele_varigheter_s),
                )
        return resultat("ukjent", "ukjent", None, None)

    if profil is not None:
        varigheter = profil.hele_varigheter_s
        if allerede_paa_s is not None:
            varigheter = tuple(t for t in varigheter if t >= allerede_paa_s)
        if varigheter:
            grunnlag = "beskrivende"
            if len(varigheter) < 20 or profil.tidsgrunnlag.dekning < 0.9 or sensurerte > len(varigheter):
                grunnlag = "lavt"
            if allerede_paa_s is None:
                return resultat(
                    "empirisk_ukjent_alder", "lavt", _tilfeldig_fase(varigheter, vindu), maalt_w, len(varigheter)
                )
            drift = sum(min(t - allerede_paa_s, vindu) for t in varigheter) / len(varigheter)
            return resultat("empirisk", grunnlag, drift, maalt_w, len(varigheter))
    if typisk_paa_minutter is not None:
        typisk_s = typisk_paa_minutter * 60
        if allerede_paa_s is None:
            return resultat("manuell_paatid_ukjent_alder", "manuelt", _tilfeldig_fase((typisk_s,), vindu), maalt_w)
        if allerede_paa_s < typisk_s:
            return resultat("manuell_paatid", "manuelt", min(typisk_s - allerede_paa_s, vindu), maalt_w)
    # Lasten er maalt paa, men vi vet ikke hvor lenge. Ubetinget duty ville
    # svart paa et annet spoersmaal og er derfor ikke et resttidsestimat.
    return resultat("ukjent_varighet", "ukjent", None, maalt_w)
