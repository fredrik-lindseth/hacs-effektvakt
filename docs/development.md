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
    manifest.json       # HA integration manifest
    sensor.py           # De fem sensor-entitetene
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
