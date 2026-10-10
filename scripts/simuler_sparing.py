#!/usr/bin/env python3
"""Sammenlign antatte lastscenarioer: uv run --group unit python scripts/simuler_sparing.py.

Ingen Home Assistant kreves. JSON-rapporten skiller en teoretisk reduksjon uten
tilbakefoering fra en kausal lastmodell som bevarer energi. Tallene dokumenterer
forutsetningene, ikke hva en bestemt ovn, bereder eller automasjon ville gjort.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=REPO / "tests" / "fixtures")
    parser.add_argument("--kutt-kw", type=float, nargs="+", default=[0.6, 1.0])
    parser.add_argument("--maal-kw", type=float, default=5.0)
    parser.add_argument("--maks-av-minutter", type=int, default=60)
    parser.add_argument("--minste-paa-minutter", type=int, default=5)
    parser.add_argument("--komfortfrist-minutter", type=int, default=120)
    args = parser.parse_args()
    # En egen pakke lar domenemodulene beholde relative importer uten HA-setup.
    pakke = ModuleType("effektvakt_scenario")
    pakke.__path__ = [str(REPO / "custom_components" / "effektvakt")]
    sys.modules[pakke.__name__] = pakke
    simulering = importlib.import_module(f"{pakke.__name__}.simulering")
    modell = importlib.import_module(f"{pakke.__name__}.modell")
    dso = importlib.import_module(f"{pakke.__name__}.dso")
    trinn = dso.KAPASITETSTRINN_PER_DSO["bkk"]["kapasitetstrinn"]
    timer = []
    for sti in sorted(args.fixtures.glob("bkk_*_hourly.json")):
        for rad in json.loads(sti.read_text())["hours"]:
            timer.append(simulering.Simuleringstime(datetime.fromisoformat(rad["start_local"]), rad["kwh"]))
    timer.sort(key=lambda time: time.start.astimezone(UTC))
    if not timer:
        parser.error("Ingen BKK-fixturer funnet")

    rapport = {
        "forutsetninger": [
            "Jevn effekt innen hver maalte time, beslutninger hvert minutt uten framtidige timer.",
            "Antatt kuttbar effekt finnes alltid, begrenset av husets forbruk.",
            "Ekstra effekt til tilbakefoering er lik kuttbar effekt; ikke en termostatmodell.",
            "Kutt slippes senest ved timeskiftet; all utsatt energi betales foer nye kutt.",
            "Et startet kutt holdes til tidsgrensen; tidligere slipp ved fallende HA-risiko modelleres ikke.",
            "Reaktiv strategi bruker domenets kriterium, ikke HA-hysterese eller blueprint-kjoering.",
            "Ideal trekker effekt fra alle timer uten tilbakefoering; dette er ikke spart energi.",
            "Priser bruker repoets BKK-tabell, ikke historiske fakturapriser.",
            "Bare hele kalendermåneder uten maalehull, fristbrudd eller uavklart gjeld inngaar i kr-sum.",
        ],
        "scenarioer": [],
    }
    for kw in args.kutt_kw:
        valg = simulering.Simuleringsvalg(
            kutt_kw=kw,
            tilbakefoering_kw=kw,
            maal_kw=args.maal_kw,
            maks_av_minutter=args.maks_av_minutter,
            minste_paa_minutter=args.minste_paa_minutter,
            komfortfrist_minutter=args.komfortfrist_minutter,
        )
        for strategi in ("reaktiv", "maal"):
            resultat = simulering.simuler(timer, trinn=trinn, strategi=strategi, valg=valg)
            grupper = defaultdict(list)
            for time in resultat.timer:
                grupper[time.start.strftime("%Y-%m")].append(time)
            maaneder = []
            total = ideal_total = 0.0
            for maaned, rader in grupper.items():
                foer, etter, ideal = {}, {}, {}
                for rad in rader:
                    if rad.opprinnelig_kwh is None:
                        continue
                    dag = rad.start.date()
                    foer[dag] = max(foer.get(dag, 0), rad.opprinnelig_kwh)
                    etter[dag] = max(etter.get(dag, 0), rad.styrt_kwh)
                    ideal[dag] = max(ideal.get(dag, 0), max(0, rad.opprinnelig_kwh - kw))
                topper = [modell.snitt_av_topp_3(dager) for dager in (foer, etter, ideal)]
                priser = [trinn[modell.trinn_indeks(topp, trinn)][1] for topp in topper]
                start = rader[0].start
                slutt = (rader[-1].start.astimezone(UTC) + timedelta(hours=1)).astimezone(rader[-1].start.tzinfo)
                hel_maaned = (
                    start.day == 1
                    and start.hour == 0
                    and slutt.day == 1
                    and slutt.hour == 0
                    and slutt.strftime("%Y-%m") != maaned
                )
                gyldig = hel_maaned and maaned not in resultat.ugyldige_maaneder
                mangler = sum(rad.opprinnelig_kwh is None for rad in rader)
                spart = priser[0] - priser[1] if gyldig else None
                ideal_spart = priser[0] - priser[2] if hel_maaned and not mangler else None
                total += spart or 0
                ideal_total += ideal_spart or 0
                maaneder.append(
                    {
                        "maaned": maaned,
                        "manglende_timer": mangler,
                        "topp3_foer_kw": round(topper[0], 6),
                        "topp3_styrt_kw": round(topper[1], 6),
                        "topp3_ideal_kw": round(topper[2], 6),
                        "kapasitetsbesparelse_scenario_kr": spart,
                        "kapasitetsbesparelse_ideal_kr": ideal_spart,
                        "utsatt_kwh": round(sum(rad.utsatt_kwh for rad in rader), 6),
                        "tilbakefoert_kwh": round(sum(rad.tilbakefoert_kwh for rad in rader), 6),
                        "restgjeld_kwh": round(rader[-1].gjeld_kwh, 6),
                        "kutt_minutter": sum(rad.kutt_minutter for rad in rader),
                    }
                )
            rapport["scenarioer"].append(
                {
                    "strategi": strategi,
                    "kutt_kw": kw,
                    "maal_kw": args.maal_kw,
                    "maks_av_minutter": args.maks_av_minutter,
                    "minste_paa_minutter": args.minste_paa_minutter,
                    "komfortfrist_minutter": args.komfortfrist_minutter,
                    "fristbrudd": resultat.fristbrudd,
                    "restgjeld_kwh": round(resultat.restgjeld_kwh, 6),
                    "opprinnelig_kwh": round(sum(t.opprinnelig_kwh or 0 for t in resultat.timer), 6),
                    "styrt_kwh": round(sum(t.styrt_kwh or 0 for t in resultat.timer), 6),
                    "sum_scenario_kr": total,
                    "sum_ideal_kr": ideal_total,
                    "maaneder": maaneder,
                }
            )
    print(json.dumps(rapport, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
