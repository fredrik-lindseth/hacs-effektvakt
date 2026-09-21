# Utvikling

## Repo-struktur

```
custom_components/effektvakt/
    __init__.py         # Entry-setup, watchdog, service-registrering
    binary_sensor.py    # binary_sensor.effektvakt_kutt_ned_anbefalt
    config_flow.py      # Config flow og options flow
    const.py            # Konstanter og default-verdier
    coordinator.py      # Beregningslogikk, hysterese, persist
    diagnostics.py      # HA diagnostics-support
    dso.py              # Kapasitetstrinn per DSO (auto-generert)
    faceplate.py        # SVG-kilde for GEHA-METER-skiven (kort og trykk)
    manifest.json       # HA integration manifest
    sensor.py           # De seks sensor-entitetene
    services.yaml       # Service-definisjoner

docs/
    blueprints/         # Blueprint YAML-filer
    beregninger.md
    begrensninger.md
    blueprints.md
    development.md
    dso.md
    faq.md
    input-sensorer.md
    sensorer.md
    strategi.md

scripts/
    export_faceplate.py               # Eksporter skiven til SVG for trykk og CAD
    sync_dso_from_stromkalkulator.py  # Sync DSO-data fra strømkalkulator

tests/
    conftest.py
    fixtures/
    test_*.py
```

---

## Kjøre tester

```bash
# Installer dev-avhengigheter
pip install -e ".[dev]"

# Kjør alle tester
pytest tests/ -v

# Kjør med coverage
pytest tests/ --cov=custom_components/effektvakt --cov-report=term-missing

# Kjør spesifikk testfil
pytest tests/test_coordinator_projection.py -v
```

---

## Pre-commit hooks

```bash
pre-commit install
pre-commit run --all-files
```

Hooks kjører ruff (lint + format), mypy og vulture. CI kjører de samme sjekkene.

---

## Oppdatere DSO-data

DSO-data i `custom_components/effektvakt/dso.py` er auto-generert fra `hacs-strømkalkulator/custom_components/stromkalkulator/dso.py`. Kjør synk-scriptet:

```bash
python scripts/sync_dso_from_stromkalkulator.py
```

Scriptet forutsetter at `hacs-strømkalkulator` ligger parallelt med `hacs-effektvakt` (dvs. `../hacs-strømkalkulator`). Etter generering: kjør tester og commit `dso.py`.

DSO-test i `tests/test_dso_data.py` verifiserer at alle trinn-lister er sortert, har gyldige terskel-verdier og at prisene er positive.

---

## Eksportere GEHA-METER-skiven

`custom_components/effektvakt/faceplate.py` tegner skiven som SVG, og både dashboard-kortet og den fysiske plata kommer fra den samme kilden. `scripts/export_faceplate.py` skriver den til fil:

```bash
# Hvilke DSO-er finnes?
python3 scripts/export_faceplate.py --liste

# Skiven for BKK, klar for trykk
python3 scripts/export_faceplate.py --dso bkk --out bkk.svg

# Kortvarianten med visere og deksel, med PNG-korrektur ved siden av
python3 scripts/export_faceplate.py --dso bkk --variant card --png

# Skala opp til 30 kW for et anlegg med høyere trinn
python3 scripts/export_faceplate.py --dso sygnir --maks-kw 30
```

Scriptet laster `dso.py` og `faceplate.py` rett fra fil med importlib, så det kjører uten at Home Assistant er installert. Uten `--out` havner filen i arbeidskatalogen som `geha-meter-<dso>-<variant>.svg`. `--variant print` er standard og gir flate farger uten visere, siden viserne på den fysiske plata er av metall. `--variant card` legger på visere, slitasje og plastdeksel, altså det kortet viser. `--maks-kw` rundes opp til nærmeste multiplum av 15 så hovedtallene på skalaen forblir hele, og scriptet sier fra når det skjer. Skriver du en DSO-id feil, foreslår det nærmeste treff og peker på `--liste` i stedet for å kaste en stacktrace. Id-en kan også oppgis som nettselskapets navn (`--dso BKK`).

`--png` kjører `rsvg-convert` og legger PNG-en ved siden av SVG-en, 1181 x 1181 piksler som er 300 dpi ved 100 mm. Det er korrektur for skjerm, ikke en trykkfil. Mangler `rsvg-convert`, sier scriptet fra at den installeres med `brew install librsvg`.

### Mål og tekst

SVG-en er 100 mm i faktisk størrelse. viewBox er `0 0 1000 1000` der én enhet er 0,1 mm, altså 1000 enheter = 100 mm, så filen kan tas rett inn i CAD med kjent skala.

Teksten ligger som ekte `<text>`-elementer med en fontstakk, ikke som baner. Den må konverteres til baner før den går til gravering eller trykk, ellers blir bokstavformene det maskinen tilfeldigvis har installert. Inkscape (`inkscape --export-text-to-path`) finnes ikke på denne maskinen, så konverteringen gjøres i CAD-programmet eller hos trykkeriet.

---

## Deploye til lokal HA

Kopier `custom_components/effektvakt` til `/config/custom_components/` på HA-instansen og start på nytt. For rask iterasjon: monter config-mappen via Samba eller SSH.

```bash
rsync -av custom_components/effektvakt/ homeassistant:/config/custom_components/effektvakt/
```

---

## CI-workflows

`.github/workflows/ci.yml`:

- ruff check + format
- mypy
- pytest med coverage
- vulture (dead code)

`.github/workflows/validate.yml`:

- HACS validation (hassfest)
- manifest.json-sjekk

---

## Services

Effektvakt registrerer to tjenester:

### `effektvakt.set_safety_buffer`

Justerer sikkerhetsbufferen live uten restart.

```yaml
service: effektvakt.set_safety_buffer
data:
  kw: 1.5
```

### `effektvakt.reset_topp_3`

Nullstiller `daily_max_kw` for inneværende måned. Nyttig for testing eller hvis du vil starte over.

```yaml
service: effektvakt.reset_topp_3
```

---

## Diagnostics

HA-diagnostics er støttet. Eksporter diagnose fra **Settings > Devices & Services > Effektvakt > (device) > Download diagnostics**. Diagnose-filen inneholder koordinator-data, hysterese-state og kapasitetstrinn, men aldri sensor-entitet-ID-er (unngår persondata).
