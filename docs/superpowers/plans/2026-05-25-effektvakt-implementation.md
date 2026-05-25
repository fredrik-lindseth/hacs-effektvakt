# Effektvakt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bygge HACS-integrasjonen Effektvakt: en prediktiv styringssensor som hindrer at norske strømkunder krysser kapasitetstrinn-grenser i nettleien. Integrasjonen leverer beslutnings-sensorer og blueprints; brukerens automasjoner gjør selve handlingen.

**Architecture:** Coordinator-basert HA-integrasjon med adaptiv polling (60/30/15s). Leser power+energy-sensor, regner projisert time-snitt-kW mot kapasitetstrinn-terskler med NVE-modell (topp-3-DAGER, ikke timer). Eksponerer sensorer + binary_sensor; brukeren kobler handling via medfølgende blueprints. Watchdog-callback uavhengig av coordinator. Persistering av daily_max + hysterese-state i .storage.

**Tech Stack:** Python 3.12+, Home Assistant integration API, voluptuous, pytest, ruff, mypy, vulture. HACS for distribusjon. Pre-commit hooks.

**Spec:** [`docs/superpowers/specs/2026-05-25-effektvakt-design.md`](../specs/2026-05-25-effektvakt-design.md)

---

## File Structure

```
custom_components/effektvakt/
├── __init__.py           # Setup/unload, options listener
├── manifest.json         # Existing, oppdateres
├── const.py              # DOMAIN, CONF_*, defaults, RISIKO_*-konstanter
├── dso.py                # KAPASITETSTRINN_PER_DSO (autogenerert)
├── config_flow.py        # 3-stegs flow + options
├── coordinator.py        # EffektvaktCoordinator
├── sensor.py             # 4 sensorer
├── binary_sensor.py      # 1 binary sensor
├── diagnostics.py        # Standard diagnostics-eksport
├── services.yaml         # 2 services
├── strings.json
└── translations/
    ├── en.json
    └── nb.json

docs/
├── blueprints/
│   ├── enkel_last_shed.yaml
│   ├── prioritert_last_shed.yaml
│   ├── climate_min_temp.yaml
│   └── kun_varsel.yaml
└── dashboard-eksempel.yaml

scripts/
└── sync_dso_from_stromkalkulator.py

tests/
├── conftest.py
├── fixtures/                       # Symlink til ../hacs-strømkalkulator/tests/fixtures/
├── test_dso_data.py
├── test_coordinator_terskel.py
├── test_coordinator_effective_threshold.py
├── test_hysteresis.py
├── test_coordinator_persistence.py
├── test_coordinator_watchdog.py
├── test_coordinator_replay.py
├── test_config_flow.py
├── test_sensor.py
├── test_binary_sensor.py
├── test_init.py
└── test_blueprint_yaml_valid.py

Top-level:
├── pyproject.toml
├── .pre-commit-config.yaml
├── .gitignore
├── LICENSE
├── README.md
├── CHANGELOG.md
├── vulture_whitelist.py
└── .github/workflows/{ci,validate,release}.yml
```

---

## Phase 1: Skjelett og tooling

### Task 1: Lage pyproject.toml og linting-config

**Files:**
- Create: `pyproject.toml`
- Create: `.pre-commit-config.yaml`
- Create: `.gitignore`
- Create: `vulture_whitelist.py`

- [ ] **Step 1: Lage pyproject.toml**

```toml
[project]
name = "effektvakt"
version = "0.1.0"
description = "Home Assistant integration for prediktiv kapasitetstrinn-styring"
readme = "README.md"
requires-python = ">=3.12"
license = "MIT"

[project.optional-dependencies]
dev = [
    "pre-commit>=3.5.0",
    "ruff>=0.8.0",
    "vulture>=2.13",
    "pytest>=8.0.0",
    "pytest-cov>=4.1.0",
    "hypothesis>=6.0.0",
    "mypy>=1.8.0",
    "voluptuous>=0.14",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
addopts = "-v --tb=short"

[tool.ruff]
target-version = "py312"
line-length = 120

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "C4", "UP", "SIM", "TCH", "RUF"]
ignore = ["E501", "B008", "SIM108"]

[tool.ruff.lint.isort]
known-first-party = ["custom_components.effektvakt"]

[tool.vulture]
min_confidence = 80
paths = ["custom_components/effektvakt"]
exclude = ["*test*"]

[tool.mypy]
python_version = "3.12"
warn_return_any = true
warn_unused_ignores = true
disallow_untyped_defs = true
check_untyped_defs = true
ignore_missing_imports = true
files = ["custom_components/effektvakt"]
exclude = ["tests"]
```

- [ ] **Step 2: Lage .pre-commit-config.yaml**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.6
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
        types_or: [python, pyi]
      - id: ruff-format
        types_or: [python, pyi]

  - repo: https://github.com/jendrikseipp/vulture
    rev: v2.14
    hooks:
      - id: vulture
        args: [
          "custom_components/effektvakt",
          "vulture_whitelist.py",
          "--min-confidence", "80",
          "--exclude", "*test*",
        ]

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-added-large-files
        args: ['--maxkb=500']

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.14.1
    hooks:
      - id: mypy
        args: [--ignore-missing-imports, --no-error-summary]
        files: ^custom_components/effektvakt/
        pass_filenames: false
        additional_dependencies: []

  - repo: local
    hooks:
      - id: pytest
        name: pytest
        entry: python -m pytest tests/ -v --tb=short
        language: system
        pass_filenames: false
        always_run: true
        stages: [pre-push]

      - id: sync_dso
        name: Verify DSO sync
        entry: python scripts/sync_dso_from_stromkalkulator.py --check
        language: system
        pass_filenames: false
        files: ^(custom_components/effektvakt/dso\.py|scripts/sync_dso_from_stromkalkulator\.py)$
```

- [ ] **Step 3: Lage .gitignore**

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
.mypy_cache/
.hypothesis/
.coverage
coverage.xml
*.egg-info/
build/
dist/
.DS_Store
.idea/
.vscode/
```

- [ ] **Step 4: Lage vulture_whitelist.py**

```python
"""Vulture whitelist - exports som vulture ikke ser brukt fra eksterne kallere."""

# Home Assistant entry points
async_setup_entry  # noqa: F821
async_unload_entry  # noqa: F821
async_get_options_flow  # noqa: F821
async_step_user  # noqa: F821
async_step_sensors  # noqa: F821
async_step_tuning  # noqa: F821
async_step_pricing  # noqa: F821
async_step_init  # noqa: F821
```

- [ ] **Step 5: LICENSE-fil (MIT)**

```
MIT License

Copyright (c) 2026 Fredrik Lindseth

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 6: Initial commit**

```bash
cd /Users/fredrik/dev/hacs-effektvakt
git add pyproject.toml .pre-commit-config.yaml .gitignore vulture_whitelist.py LICENSE KONGSTANKE.md hacs.json custom_components/effektvakt/manifest.json custom_components/effektvakt/const.py docs/superpowers/
git commit -m "chore: initial tooling, spec, plan"
```

---

### Task 2: Oppdatere manifest.json

**Files:**
- Modify: `custom_components/effektvakt/manifest.json`

- [ ] **Step 1: Oppdatere manifest.json**

```json
{
  "domain": "effektvakt",
  "name": "Effektvakt",
  "codeowners": ["@fredrik-lindseth"],
  "config_flow": true,
  "dependencies": [],
  "documentation": "https://github.com/fredrik-lindseth/hacs-effektvakt",
  "iot_class": "local_polling",
  "issue_tracker": "https://github.com/fredrik-lindseth/hacs-effektvakt/issues",
  "requirements": [],
  "version": "0.1.0",
  "integration_type": "service"
}
```

- [ ] **Step 2: Verifiser at JSON er gyldig**

Run: `jq empty custom_components/effektvakt/manifest.json && echo OK`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/effektvakt/manifest.json
git commit -m "chore(manifest): legg til config_flow og integration_type"
```

---

### Task 3: Lage const.py

**Files:**
- Create: `custom_components/effektvakt/const.py`

- [ ] **Step 1: Skrive const.py**

```python
"""Constants for Effektvakt integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final[str] = "effektvakt"

# Config keys
CONF_DSO: Final[str] = "dso"
CONF_POWER_SENSOR: Final[str] = "power_sensor"
CONF_ENERGY_SENSOR: Final[str] = "energy_sensor"
CONF_KAPASITETSTRINN_CUSTOM: Final[str] = "kapasitetstrinn_custom"
CONF_SAFETY_BUFFER_KW: Final[str] = "safety_buffer_kw"
CONF_MIN_RISIKO_FOR_KUTT: Final[str] = "min_risiko_for_kutt"
CONF_RISIKO_HOLDETID_MINUTTER: Final[str] = "risiko_holdetid_minutter"
CONF_CONFIRM_PEAK_SENSOR: Final[str] = "confirm_peak_sensor"

# Default values
DEFAULT_DSO: Final[str] = "bkk"
DEFAULT_SAFETY_BUFFER_KW: Final[float] = 1.0
DEFAULT_MIN_RISIKO_FOR_KUTT: Final[str] = "medium"
DEFAULT_RISIKO_HOLDETID_MINUTTER: Final[int] = 5

# Risiko-nivåer (sortert: lavest til høyest)
RISIKO_NONE: Final[str] = "none"
RISIKO_LOW: Final[str] = "low"
RISIKO_MEDIUM: Final[str] = "medium"
RISIKO_HIGH: Final[str] = "high"

RISIKO_LEVELS: Final[list[str]] = [RISIKO_NONE, RISIKO_LOW, RISIKO_MEDIUM, RISIKO_HIGH]
RISIKO_RANK: Final[dict[str, int]] = {nivå: idx for idx, nivå in enumerate(RISIKO_LEVELS)}

# Tick-intervaller per risiko-nivå (sekunder)
TICK_INTERVAL_BY_RISIKO: Final[dict[str, int]] = {
    RISIKO_NONE: 60,
    RISIKO_LOW: 60,
    RISIKO_MEDIUM: 30,
    RISIKO_HIGH: 15,
}

# Watchdog
WATCHDOG_INTERVAL_SECONDS: Final[int] = 60
WATCHDOG_STALE_THRESHOLD_SECONDS: Final[int] = 120

# Storage
STORAGE_VERSION: Final[int] = 1

# Peak-sensor-detection mønstre
PEAK_SENSOR_NAME_PATTERNS: Final[list[str]] = [
    "_max_power",
    "_peak_",
    "_peak",
    "_max_per_hour",
    "_average_",
    "_avg_",
]
PEAK_SENSOR_FRIENDLY_NAME_KEYWORDS: Final[list[str]] = ["max", "peak", "average"]

# Validation
VALID_POWER_UNITS: Final[frozenset[str]] = frozenset({"W", "kW"})
VALID_ENERGY_UNITS: Final[frozenset[str]] = frozenset({"Wh", "kWh"})

MAX_POWER_CLAMP_W: Final[int] = 100_000  # 100 kW absolutt øvre grense
MAX_ENERGY_DELTA_KWH: Final[float] = 50.0  # ingen 50+ kWh delta per minutt
```

- [ ] **Step 2: Verifiser at filen er gyldig Python**

Run: `python -m py_compile custom_components/effektvakt/const.py && echo OK`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/effektvakt/const.py
git commit -m "feat(const): konstanter for DOMAIN, CONF_*, RISIKO_*"
```

---

### Task 4: Lage sync_dso-script og generert dso.py

**Files:**
- Create: `scripts/sync_dso_from_stromkalkulator.py`
- Create: `custom_components/effektvakt/dso.py` (autogenerert)

- [ ] **Step 1: Skrive sync-scriptet**

```python
#!/usr/bin/env python3
"""Generer effektvakt/dso.py fra strømkalkulator/dso.py.

Krever at hacs-strømkalkulator er sjekket ut som søskenmappe:
    ~/dev/hacs-effektvakt/
    ~/dev/hacs-strømkalkulator/

Bruk:
    python scripts/sync_dso_from_stromkalkulator.py          # regenerer
    python scripts/sync_dso_from_stromkalkulator.py --check  # feiler hvis diff
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EFFEKTVAKT_DSO = REPO_ROOT / "custom_components" / "effektvakt" / "dso.py"
STROMKALKULATOR_DSO = (
    REPO_ROOT.parent / "hacs-strømkalkulator" / "custom_components" / "stromkalkulator" / "dso.py"
)


def _load_stromkalkulator_dso() -> dict:
    """Importer DSO_LIST fra strømkalkulator uten å installere repoet."""
    if not STROMKALKULATOR_DSO.exists():
        print(f"FEIL: Finner ikke {STROMKALKULATOR_DSO}", file=sys.stderr)
        print("Sjekk at hacs-strømkalkulator er klonet som søskenmappe.", file=sys.stderr)
        sys.exit(2)

    import importlib.util

    spec = importlib.util.spec_from_file_location("stromkalkulator_dso", STROMKALKULATOR_DSO)
    if spec is None or spec.loader is None:
        print("FEIL: Kunne ikke laste strømkalkulator/dso.py", file=sys.stderr)
        sys.exit(2)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.DSO_LIST


def _normalize_kapasitetstrinn(raw: list) -> list[tuple[float, int]]:
    """Normaliser kapasitetstrinn fra (kw, pris) eller {min, max, pris} til tuple."""
    if not raw:
        return []
    if isinstance(raw[0], dict):
        return [(float(entry["max"]), int(entry["pris"])) for entry in raw]
    return [(float(t[0]), int(t[1])) for t in raw]


def _generate(dso_list: dict) -> str:
    """Generer Python-kode for effektvakt/dso.py."""
    lines = [
        "# AUTOGENERATED FROM hacs-strømkalkulator/custom_components/stromkalkulator/dso.py",
        "# Kjør scripts/sync_dso_from_stromkalkulator.py for å regenerere.",
        "# Manuell redigering vil bli overskrevet.",
        "",
        '"""Kapasitetstrinn per DSO. Subset-kopi fra strømkalkulator."""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Final, TypedDict",
        "",
        "",
        "class DSOInfo(TypedDict):",
        '    """Kapasitetstrinn-data for et nettselskap."""',
        "    navn: str",
        "    prisomrade: str",
        "    kapasitetstrinn: list[tuple[float, int]]  # (kW-terskel, kr/mnd)",
        "",
        "",
        "KAPASITETSTRINN_PER_DSO: Final[dict[str, DSOInfo]] = {",
    ]

    for dso_id, dso in sorted(dso_list.items()):
        if not dso.get("supported", False) or dso_id == "custom":
            continue
        kapasitetstrinn = _normalize_kapasitetstrinn(dso.get("kapasitetstrinn", []))
        if not kapasitetstrinn:
            continue
        navn = dso["name"]
        prisomrade = dso.get("prisomrade", "")
        lines.append(f'    "{dso_id}": {{')
        lines.append(f'        "navn": "{navn}",')
        lines.append(f'        "prisomrade": "{prisomrade}",')
        lines.append(f'        "kapasitetstrinn": {kapasitetstrinn!r},')
        lines.append("    },")

    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Feil hvis output skiller seg fra committet fil")
    args = parser.parse_args()

    dso_list = _load_stromkalkulator_dso()
    generated = _generate(dso_list)

    if args.check:
        if not EFFEKTVAKT_DSO.exists():
            print(f"FEIL: {EFFEKTVAKT_DSO} eksisterer ikke. Kjør uten --check først.", file=sys.stderr)
            return 1
        current = EFFEKTVAKT_DSO.read_text()
        if current.strip() != generated.strip():
            print("FEIL: dso.py har driftet fra strømkalkulator.", file=sys.stderr)
            print("Kjør: python scripts/sync_dso_from_stromkalkulator.py", file=sys.stderr)
            return 1
        print("OK: dso.py er i sync.")
        return 0

    EFFEKTVAKT_DSO.write_text(generated)
    n = generated.count('    "')
    print(f"Skrev {EFFEKTVAKT_DSO} ({n} DSO-er)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Gjør scriptet executable og kjør det**

```bash
chmod +x scripts/sync_dso_from_stromkalkulator.py
python scripts/sync_dso_from_stromkalkulator.py
```

Expected: `Skrev .../dso.py (N DSO-er)` der N er antall supported DSO-er fra strømkalkulator.

- [ ] **Step 3: Verifiser at generert dso.py er gyldig Python**

Run: `python -m py_compile custom_components/effektvakt/dso.py && echo OK`
Expected: `OK`

- [ ] **Step 4: Verifiser at --check virker**

Run: `python scripts/sync_dso_from_stromkalkulator.py --check`
Expected: `OK: dso.py er i sync.`

- [ ] **Step 5: Commit**

```bash
git add scripts/ custom_components/effektvakt/dso.py
git commit -m "feat(dso): sync-script og generert kapasitetstrinn-data"
```

---

## Phase 2: Coordinator core (TDD)

### Task 5: Lage tests/conftest.py med HA-mocks

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/__init__.py` (tom)

- [ ] **Step 1: Skrive conftest.py**

```python
"""Pytest configuration, shared helpers og fixtures for Effektvakt-tester.

Mocker hele Home Assistant-stacken slik at vi slipper å installere HA
i CI. Følger samme mønster som strømkalkulator.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "custom_components"))

# Mock Home Assistant-moduler før vi importerer vår kode
sys.modules["homeassistant"] = MagicMock()
sys.modules["homeassistant.const"] = MagicMock()
sys.modules["homeassistant.core"] = MagicMock()
sys.modules["homeassistant.config_entries"] = MagicMock()
sys.modules["homeassistant.data_entry_flow"] = MagicMock()
sys.modules["homeassistant.helpers"] = MagicMock()
sys.modules["homeassistant.helpers.event"] = MagicMock()
sys.modules["homeassistant.helpers.issue_registry"] = MagicMock()
sys.modules["homeassistant.helpers.storage"] = MagicMock()
sys.modules["homeassistant.helpers.update_coordinator"] = MagicMock()
sys.modules["homeassistant.helpers.entity"] = MagicMock()
sys.modules["homeassistant.helpers.selector"] = MagicMock()
sys.modules["homeassistant.components.sensor"] = MagicMock()
sys.modules["homeassistant.components.binary_sensor"] = MagicMock()

_dt_util_mock = MagicMock()
_dt_util_mock.now.return_value = datetime(2026, 6, 15, 12, 0, 0)
_ha_util_mock = MagicMock()
_ha_util_mock.dt = _dt_util_mock
sys.modules["homeassistant.util"] = _ha_util_mock
sys.modules["homeassistant.util.dt"] = _dt_util_mock


def make_state(value, *, unit: str | None = None, state_class: str | None = None):
    """Mock HA state-objekt."""
    state = MagicMock()
    state.state = str(value)
    state.attributes = {}
    if unit is not None:
        state.attributes["unit_of_measurement"] = unit
    if state_class is not None:
        state.attributes["state_class"] = state_class
    return state


def make_entry(
    entry_id: str = "test_entry",
    dso: str = "bkk",
    power_sensor: str = "sensor.power",
    energy_sensor: str | None = "sensor.energy",
    safety_buffer_kw: float = 1.0,
    min_risiko_for_kutt: str = "medium",
    risiko_holdetid_minutter: int = 5,
    kapasitetstrinn_custom: list | None = None,
):
    """Mock config entry med Effektvakt-defaults."""
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.data = {
        "dso": dso,
        "power_sensor": power_sensor,
        "energy_sensor": energy_sensor,
        "safety_buffer_kw": safety_buffer_kw,
        "min_risiko_for_kutt": min_risiko_for_kutt,
        "risiko_holdetid_minutter": risiko_holdetid_minutter,
    }
    if kapasitetstrinn_custom is not None:
        entry.data["kapasitetstrinn_custom"] = kapasitetstrinn_custom
    return entry


def make_hass_with_states(states: dict[str, object]):
    """Mock hass-objekt med states.get som leter i en gitt dict."""
    hass = MagicMock()
    hass.states.get = lambda entity_id: states.get(entity_id)
    return hass


@pytest.fixture
def hass():
    """Default hass-mock."""
    return make_hass_with_states({})


@pytest.fixture
def entry():
    """Default config entry."""
    return make_entry()
```

- [ ] **Step 2: Lage tom tests/__init__.py**

```python
```

- [ ] **Step 3: Verifiser at pytest starter uten feil**

Run: `pytest tests/ --co -q`
Expected: `no tests ran in ...s` (ingen tester ennå, men ingen errors)

- [ ] **Step 4: Commit**

```bash
git add tests/__init__.py tests/conftest.py
git commit -m "test: conftest med HA-mocks"
```

---

### Task 6: test_dso_data: sanity-tester for generert DSO-data

**Files:**
- Create: `tests/test_dso_data.py`

- [ ] **Step 1: Skrive testene**

```python
"""Sanity-sjekker på generert dso.py."""

from __future__ import annotations

from custom_components.effektvakt.dso import KAPASITETSTRINN_PER_DSO


def test_har_minst_en_dso():
    assert len(KAPASITETSTRINN_PER_DSO) >= 10, "Forventer minst 10 DSO-er"


def test_alle_dso_har_navn_og_kapasitetstrinn():
    for dso_id, info in KAPASITETSTRINN_PER_DSO.items():
        assert info["navn"], f"{dso_id}: mangler navn"
        assert info["kapasitetstrinn"], f"{dso_id}: tom kapasitetstrinn-liste"


def test_kapasitetstrinn_terskler_stigende():
    for dso_id, info in KAPASITETSTRINN_PER_DSO.items():
        trinn = info["kapasitetstrinn"]
        terskler = [t[0] for t in trinn]
        assert terskler == sorted(terskler), (
            f"{dso_id}: terskler ikke stigende: {terskler}"
        )


def test_kapasitetstrinn_priser_stigende_eller_likt():
    for dso_id, info in KAPASITETSTRINN_PER_DSO.items():
        trinn = info["kapasitetstrinn"]
        priser = [t[1] for t in trinn]
        # Noen DSO-er kan ha samme pris over flere trinn, men aldri synkende
        for prev, curr in zip(priser, priser[1:], strict=False):
            assert curr >= prev, f"{dso_id}: pris {curr} < forrige {prev}"


def test_bkk_eksisterer():
    assert "bkk" in KAPASITETSTRINN_PER_DSO
    bkk = KAPASITETSTRINN_PER_DSO["bkk"]
    assert bkk["navn"]
    assert len(bkk["kapasitetstrinn"]) >= 5


def test_alle_terskler_positive():
    for dso_id, info in KAPASITETSTRINN_PER_DSO.items():
        for terskel, pris in info["kapasitetstrinn"]:
            assert terskel > 0, f"{dso_id}: ikke-positiv terskel {terskel}"
            assert pris > 0, f"{dso_id}: ikke-positiv pris {pris}"
```

- [ ] **Step 2: Kjøre testene**

Run: `pytest tests/test_dso_data.py -v`
Expected: alle 6 tester PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_dso_data.py
git commit -m "test(dso): sanity-tester for kapasitetstrinn-data"
```

---

### Task 7: Coordinator-skjelett og helpers (read_sensor, normalize_unit)

**Files:**
- Create: `custom_components/effektvakt/coordinator.py`
- Create: `tests/test_coordinator_helpers.py`

- [ ] **Step 1: Test for power-sensor-lesing med unit-normalisering**

```python
"""Tester for helper-funksjoner i coordinator."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.effektvakt.coordinator import read_power_kw, read_energy_kwh
from tests.conftest import make_state


def test_read_power_kw_fra_watt():
    hass = MagicMock()
    hass.states.get.return_value = make_state("2500", unit="W")
    assert read_power_kw(hass, "sensor.p") == 2.5


def test_read_power_kw_fra_kw():
    hass = MagicMock()
    hass.states.get.return_value = make_state("3.2", unit="kW")
    assert read_power_kw(hass, "sensor.p") == 3.2


def test_read_power_kw_ukjent_unit_returnerer_none():
    hass = MagicMock()
    hass.states.get.return_value = make_state("1", unit="VA")
    assert read_power_kw(hass, "sensor.p") is None


def test_read_power_kw_unavailable_returnerer_none():
    hass = MagicMock()
    hass.states.get.return_value = make_state("unavailable", unit="W")
    assert read_power_kw(hass, "sensor.p") is None


def test_read_power_kw_ingen_sensor_returnerer_none():
    hass = MagicMock()
    assert read_power_kw(hass, None) is None


def test_read_energy_kwh_fra_kwh():
    hass = MagicMock()
    hass.states.get.return_value = make_state("124523.105", unit="kWh")
    assert read_energy_kwh(hass, "sensor.e") == 124523.105


def test_read_energy_kwh_fra_wh():
    hass = MagicMock()
    hass.states.get.return_value = make_state("124523105", unit="Wh")
    assert read_energy_kwh(hass, "sensor.e") == 124523.105
```

- [ ] **Step 2: Kjør testene, forvent FAIL**

Run: `pytest tests/test_coordinator_helpers.py -v`
Expected: ImportError / function not defined.

- [ ] **Step 3: Implementere coordinator.py-skjelett med helpers**

```python
"""Coordinator for Effektvakt."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from .const import (
    MAX_POWER_CLAMP_W,
    VALID_ENERGY_UNITS,
    VALID_POWER_UNITS,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def read_power_kw(hass: HomeAssistant, entity_id: str | None) -> float | None:
    """Les power-sensor og returner verdi normalisert til kW.

    Returnerer None hvis sensor ikke finnes, er unavailable, har ugyldig
    unit, eller verdien er ikke-finit/over MAX_POWER_CLAMP_W.
    """
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in ("unknown", "unavailable", None):
        return None
    try:
        value = float(state.state)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(value):
        return None
    unit = (state.attributes or {}).get("unit_of_measurement")
    if unit not in VALID_POWER_UNITS:
        return None
    if unit == "W":
        if value > MAX_POWER_CLAMP_W:
            _LOGGER.warning("power_sensor %s = %s W > clamp %s", entity_id, value, MAX_POWER_CLAMP_W)
            return None
        return value / 1000
    return value  # kW


def read_energy_kwh(hass: HomeAssistant, entity_id: str | None) -> float | None:
    """Les energy-sensor og returner verdi normalisert til kWh.

    Returnerer None hvis sensor ikke finnes, er unavailable, eller har ugyldig
    unit.
    """
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in ("unknown", "unavailable", None):
        return None
    try:
        value = float(state.state)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    unit = (state.attributes or {}).get("unit_of_measurement")
    if unit not in VALID_ENERGY_UNITS:
        return None
    if unit == "Wh":
        return value / 1000
    return value  # kWh
```

- [ ] **Step 4: Kjør testene, forvent PASS**

Run: `pytest tests/test_coordinator_helpers.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/effektvakt/coordinator.py tests/test_coordinator_helpers.py
git commit -m "feat(coordinator): read_power_kw og read_energy_kwh med unit-normalisering"
```

---

### Task 8: Risikoklassifisering (rå)

**Files:**
- Modify: `custom_components/effektvakt/coordinator.py`
- Create: `tests/test_risk_classification.py`

- [ ] **Step 1: Test for rå risiko-klassifisering**

```python
"""Tester for rå risikoklassifisering (uten hysterese)."""

from __future__ import annotations

import pytest

from custom_components.effektvakt.coordinator import classify_raw_risk
from custom_components.effektvakt.const import RISIKO_NONE, RISIKO_LOW, RISIKO_MEDIUM, RISIKO_HIGH


@pytest.mark.parametrize("margin,buffer,expected", [
    (5.0, 1.0, RISIKO_NONE),     # margin > 2 * buffer
    (2.5, 1.0, RISIKO_NONE),     # margin > 2 * buffer (grense)
    (1.5, 1.0, RISIKO_LOW),      # buffer < margin <= 2 * buffer
    (1.0, 1.0, RISIKO_LOW),      # margin == buffer faller i low (siden 0 < 1 <= 2)
    (0.5, 1.0, RISIKO_MEDIUM),   # 0 < margin <= buffer
    (0.0, 1.0, RISIKO_HIGH),     # margin <= 0
    (-1.0, 1.0, RISIKO_HIGH),
    (3.0, 0.5, RISIKO_NONE),
    (0.4, 0.5, RISIKO_MEDIUM),
])
def test_classify_raw_risk(margin: float, buffer: float, expected: str):
    assert classify_raw_risk(margin_kw=margin, safety_buffer_kw=buffer) == expected
```

Vent: formelen i spec sier:
- `none`: margin > 2 × buffer
- `low`: buffer < margin ≤ 2 × buffer
- `medium`: 0 < margin ≤ buffer
- `high`: margin ≤ 0

Det betyr at margin == buffer (1.0 = 1.0) faller i low fordi "buffer < margin" er falsk. Endre testen:

```python
@pytest.mark.parametrize("margin,buffer,expected", [
    (5.0, 1.0, RISIKO_NONE),
    (2.5, 1.0, RISIKO_NONE),
    (2.0, 1.0, RISIKO_LOW),      # margin == 2*buffer, ≤ 2*buffer -> low
    (1.5, 1.0, RISIKO_LOW),
    (1.0, 1.0, RISIKO_MEDIUM),   # margin == buffer, ≤ buffer -> medium
    (0.5, 1.0, RISIKO_MEDIUM),
    (0.001, 1.0, RISIKO_MEDIUM),
    (0.0, 1.0, RISIKO_HIGH),
    (-1.0, 1.0, RISIKO_HIGH),
    (3.0, 0.5, RISIKO_NONE),
    (0.4, 0.5, RISIKO_MEDIUM),
])
def test_classify_raw_risk(margin: float, buffer: float, expected: str):
    assert classify_raw_risk(margin_kw=margin, safety_buffer_kw=buffer) == expected
```

- [ ] **Step 2: Kjør testene, forvent FAIL**

Run: `pytest tests/test_risk_classification.py -v`
Expected: ImportError.

- [ ] **Step 3: Implementere classify_raw_risk i coordinator.py**

Legg til etter `read_energy_kwh` i `coordinator.py`:

```python
from .const import RISIKO_HIGH, RISIKO_LOW, RISIKO_MEDIUM, RISIKO_NONE


def classify_raw_risk(*, margin_kw: float, safety_buffer_kw: float) -> str:
    """Klassifiser rå risiko basert på margin og safety_buffer.

    Returnerer en av RISIKO_NONE, RISIKO_LOW, RISIKO_MEDIUM, RISIKO_HIGH.
    Se spec for tabell.
    """
    if margin_kw <= 0:
        return RISIKO_HIGH
    if margin_kw <= safety_buffer_kw:
        return RISIKO_MEDIUM
    if margin_kw <= 2 * safety_buffer_kw:
        return RISIKO_LOW
    return RISIKO_NONE
```

- [ ] **Step 4: Kjør testene, forvent PASS**

Run: `pytest tests/test_risk_classification.py -v`
Expected: 11 PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/effektvakt/coordinator.py tests/test_risk_classification.py
git commit -m "feat(coordinator): classify_raw_risk basert på margin og safety_buffer"
```

---

### Task 9: Topp-3-dager-beregning og effective_threshold

**Files:**
- Modify: `custom_components/effektvakt/coordinator.py`
- Create: `tests/test_effective_threshold.py`

- [ ] **Step 1: Test for daily_max-aggregering**

```python
"""Tester for effective_threshold-beregning."""

from __future__ import annotations

from datetime import date

import pytest

from custom_components.effektvakt.coordinator import (
    compute_effective_threshold,
    top_n_average,
)


def test_top_n_average_tom_dict():
    assert top_n_average({}, n=2) is None


def test_top_n_average_én_dag():
    assert top_n_average({date(2026, 5, 1): 5.0}, n=2) == pytest.approx(5.0)


def test_top_n_average_to_dager():
    dm = {date(2026, 5, 1): 5.0, date(2026, 5, 2): 7.0}
    assert top_n_average(dm, n=2) == pytest.approx(6.0)


def test_top_n_average_tre_dager_velger_de_to_hoyeste():
    dm = {
        date(2026, 5, 1): 5.0,
        date(2026, 5, 2): 7.0,
        date(2026, 5, 3): 3.0,
    }
    assert top_n_average(dm, n=2) == pytest.approx(6.0)


def test_top_n_average_topp_3():
    dm = {
        date(2026, 5, 1): 5.0,
        date(2026, 5, 2): 7.0,
        date(2026, 5, 3): 3.0,
        date(2026, 5, 4): 9.0,
    }
    assert top_n_average(dm, n=3) == pytest.approx((9 + 7 + 5) / 3)


def test_effective_threshold_med_for_få_dager():
    """Når < 2 dager logget, fall tilbake til next_tier_threshold."""
    dm = {date(2026, 5, 1): 5.0}
    assert compute_effective_threshold(
        next_tier_threshold_kw=10.0,
        daily_max_kw=dm,
    ) == 10.0


def test_effective_threshold_topp_2_under_terskel():
    """Topp-2-snitt under next_tier: bruk next_tier."""
    dm = {date(2026, 5, 1): 6.0, date(2026, 5, 2): 7.0}  # snitt 6.5
    assert compute_effective_threshold(
        next_tier_threshold_kw=10.0,
        daily_max_kw=dm,
    ) == 10.0


def test_effective_threshold_topp_2_over_terskel():
    """Topp-2-snitt over next_tier: bruk topp-2-snitt."""
    dm = {date(2026, 5, 1): 11.0, date(2026, 5, 2): 13.0}  # snitt 12.0
    assert compute_effective_threshold(
        next_tier_threshold_kw=10.0,
        daily_max_kw=dm,
    ) == pytest.approx(12.0)


def test_effective_threshold_eksempel_fra_spec():
    """Bruker har 3 dager på 12 kW i et 10-15 kW-trinn, betaler allerede 15-trinnet."""
    dm = {date(2026, 5, 1): 12.0, date(2026, 5, 2): 12.0, date(2026, 5, 3): 12.0}
    # Topp-2-snitt = 12, neste trinn = 15 (siden de allerede er over 10).
    # Effective_threshold = max(15, 12) = 15. Kutting hjelper kun til å holde under 15.
    assert compute_effective_threshold(
        next_tier_threshold_kw=15.0,
        daily_max_kw=dm,
    ) == pytest.approx(15.0)
```

- [ ] **Step 2: Kjør, forvent FAIL**

Run: `pytest tests/test_effective_threshold.py -v`
Expected: ImportError.

- [ ] **Step 3: Implementere i coordinator.py**

```python
from datetime import date


def top_n_average(daily_max_kw: dict[date, float], *, n: int) -> float | None:
    """Snitt av de n høyeste verdiene i daily_max_kw.

    Returnerer None hvis dict er tom. Hvis det er færre enn n entries,
    returneres snittet av alle.
    """
    if not daily_max_kw:
        return None
    sorted_vals = sorted(daily_max_kw.values(), reverse=True)
    take = sorted_vals[:n]
    return sum(take) / len(take)


def compute_effective_threshold(
    *,
    next_tier_threshold_kw: float,
    daily_max_kw: dict[date, float],
) -> float:
    """Beregn effective_threshold for topp-3-bevissthet.

    Hvis < 2 dager logget: fall tilbake til next_tier_threshold (konservativt
    valg tidlig i måneden).

    Ellers: max(next_tier_threshold, snitt_av_topp_2_dager).
    """
    if len(daily_max_kw) < 2:
        return next_tier_threshold_kw
    topp_2 = top_n_average(daily_max_kw, n=2)
    assert topp_2 is not None  # len >= 2 garantert
    return max(next_tier_threshold_kw, topp_2)
```

- [ ] **Step 4: Kjør, forvent PASS**

Run: `pytest tests/test_effective_threshold.py -v`
Expected: 9 PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/effektvakt/coordinator.py tests/test_effective_threshold.py
git commit -m "feat(coordinator): topp-3-aware effective_threshold"
```

---

### Task 10: Tier-oppslag (next_tier_threshold + prev_tier_threshold)

**Files:**
- Modify: `custom_components/effektvakt/coordinator.py`
- Create: `tests/test_tier_lookup.py`

- [ ] **Step 1: Test for tier-oppslag**

```python
"""Tester for next/prev-tier-oppslag fra kapasitetstrinn-liste."""

from __future__ import annotations

from custom_components.effektvakt.coordinator import lookup_tiers


# BKK 2026-trinn (eksempel: verdier sjekkes ikke nøyaktig her)
BKK_TIER_EXAMPLE = [
    (2.0, 130),
    (5.0, 230),
    (10.0, 415),
    (15.0, 600),
    (20.0, 800),
    (25.0, 1000),
]


def test_lookup_tiers_under_første_trinn():
    """Bruker er under første trinn: prev = None, next = laveste."""
    info = lookup_tiers(projected_kw=1.5, trinn=BKK_TIER_EXAMPLE)
    assert info.prev_threshold_kw is None
    assert info.next_threshold_kw == 2.0
    assert info.next_pris_per_mnd == 130


def test_lookup_tiers_i_første_trinn():
    """Bruker er i første trinn (under 5): prev = 2.0, next = 5.0."""
    info = lookup_tiers(projected_kw=3.0, trinn=BKK_TIER_EXAMPLE)
    assert info.prev_threshold_kw == 2.0
    assert info.next_threshold_kw == 5.0
    assert info.next_pris_per_mnd == 230


def test_lookup_tiers_på_grense():
    """Bruker er nøyaktig på trinn-grense (5.0): det regnes som under neste."""
    info = lookup_tiers(projected_kw=5.0, trinn=BKK_TIER_EXAMPLE)
    assert info.prev_threshold_kw == 2.0
    assert info.next_threshold_kw == 5.0


def test_lookup_tiers_over_grense():
    info = lookup_tiers(projected_kw=7.5, trinn=BKK_TIER_EXAMPLE)
    assert info.prev_threshold_kw == 5.0
    assert info.next_threshold_kw == 10.0


def test_lookup_tiers_over_høyeste_trinn():
    """Bruker er over høyeste trinn: next = None, prev = høyeste."""
    info = lookup_tiers(projected_kw=30.0, trinn=BKK_TIER_EXAMPLE)
    assert info.prev_threshold_kw == 25.0
    assert info.next_threshold_kw is None
    assert info.next_pris_per_mnd is None
```

- [ ] **Step 2: Kjør, forvent FAIL**

Run: `pytest tests/test_tier_lookup.py -v`
Expected: ImportError.

- [ ] **Step 3: Implementere lookup_tiers**

Legg til i `coordinator.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class TierInfo:
    """Resultat fra tier-oppslag."""
    prev_threshold_kw: float | None
    next_threshold_kw: float | None
    next_pris_per_mnd: int | None


def lookup_tiers(
    *,
    projected_kw: float,
    trinn: list[tuple[float, int]],
) -> TierInfo:
    """Finn prev og next tier basert på projisert kW.

    Trinn-listen er sortert stigende på kW-terskel. "next" er det laveste
    trinnet hvor terskel >= projected_kw. "prev" er trinnet rett under.
    """
    if not trinn:
        return TierInfo(None, None, None)

    next_idx: int | None = None
    for i, (threshold, _) in enumerate(trinn):
        if projected_kw <= threshold:
            next_idx = i
            break

    if next_idx is None:
        # over høyeste trinn
        prev_kw, _prev_pris = trinn[-1]
        return TierInfo(prev_threshold_kw=prev_kw, next_threshold_kw=None, next_pris_per_mnd=None)

    next_kw, next_pris = trinn[next_idx]
    prev_kw = trinn[next_idx - 1][0] if next_idx > 0 else None
    return TierInfo(prev_threshold_kw=prev_kw, next_threshold_kw=next_kw, next_pris_per_mnd=next_pris)
```

- [ ] **Step 4: Kjør, forvent PASS**

Run: `pytest tests/test_tier_lookup.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/effektvakt/coordinator.py tests/test_tier_lookup.py
git commit -m "feat(coordinator): lookup_tiers for next/prev kapasitetstrinn"
```

---

### Task 11: Hysterese-state

**Files:**
- Modify: `custom_components/effektvakt/coordinator.py`
- Create: `tests/test_hysteresis.py`

- [ ] **Step 1: Test for hysterese-logikk**

```python
"""Tester for hysterese-state-maskinen."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from custom_components.effektvakt.coordinator import HystereseState, apply_hysteresis
from custom_components.effektvakt.const import RISIKO_NONE, RISIKO_LOW, RISIKO_MEDIUM, RISIKO_HIGH


HOLDETID = timedelta(minutes=5)
NOW = datetime(2026, 5, 25, 14, 0, 0)


def test_oppgang_er_umiddelbar():
    state = HystereseState(nivå=RISIKO_NONE, pending_nivå=None, pending_since=None)
    apply_hysteresis(state, rå_nivå=RISIKO_MEDIUM, now=NOW, holdetid=HOLDETID)
    assert state.nivå == RISIKO_MEDIUM
    assert state.pending_nivå is None


def test_oppgang_overskriver_pending():
    state = HystereseState(
        nivå=RISIKO_HIGH,
        pending_nivå=RISIKO_MEDIUM,
        pending_since=NOW - timedelta(minutes=2),
    )
    apply_hysteresis(state, rå_nivå=RISIKO_HIGH, now=NOW, holdetid=HOLDETID)
    # rå == nivå: oppgang/likt-grenen treffer, pending nullstilles
    assert state.nivå == RISIKO_HIGH
    assert state.pending_nivå is None
    assert state.pending_since is None


def test_nedgang_starter_timer():
    state = HystereseState(nivå=RISIKO_HIGH, pending_nivå=None, pending_since=None)
    apply_hysteresis(state, rå_nivå=RISIKO_LOW, now=NOW, holdetid=HOLDETID)
    assert state.nivå == RISIKO_HIGH  # holder seg
    assert state.pending_nivå == RISIKO_LOW
    assert state.pending_since == NOW


def test_nedgang_holder_innenfor_holdetid():
    state = HystereseState(
        nivå=RISIKO_HIGH,
        pending_nivå=RISIKO_LOW,
        pending_since=NOW - timedelta(minutes=2),
    )
    apply_hysteresis(
        state, rå_nivå=RISIKO_LOW, now=NOW, holdetid=HOLDETID
    )
    assert state.nivå == RISIKO_HIGH  # < holdetid


def test_nedgang_trigger_etter_holdetid_multi_step():
    """Hopp fra HIGH til NONE: går trinn-for-trinn med holdetid mellom."""
    state = HystereseState(
        nivå=RISIKO_HIGH,
        pending_nivå=RISIKO_NONE,
        pending_since=NOW - timedelta(minutes=5),
    )
    apply_hysteresis(state, rå_nivå=RISIKO_NONE, now=NOW, holdetid=HOLDETID)
    # Etter holdetid: går ned ett trinn til MEDIUM, ny holdetid for å nå NONE
    assert state.nivå == RISIKO_MEDIUM
    assert state.pending_since == NOW  # ny timer for neste trinn


def test_oscillasjon_kansellerer_pending():
    """Hvis rå går opp under pending, glem nedgangen."""
    state = HystereseState(
        nivå=RISIKO_HIGH,
        pending_nivå=RISIKO_LOW,
        pending_since=NOW - timedelta(minutes=2),
    )
    apply_hysteresis(state, rå_nivå=RISIKO_HIGH, now=NOW, holdetid=HOLDETID)
    assert state.nivå == RISIKO_HIGH
    assert state.pending_nivå is None
    assert state.pending_since is None


def test_endret_pending_nullstiller_timer():
    """Hvis pending var LOW men nå er rå MEDIUM (også lavere enn nivå), reset timer."""
    state = HystereseState(
        nivå=RISIKO_HIGH,
        pending_nivå=RISIKO_LOW,
        pending_since=NOW - timedelta(minutes=2),
    )
    apply_hysteresis(state, rå_nivå=RISIKO_MEDIUM, now=NOW, holdetid=HOLDETID)
    assert state.nivå == RISIKO_HIGH
    assert state.pending_nivå == RISIKO_MEDIUM
    assert state.pending_since == NOW


def test_full_nedgang_to_none_over_tid():
    """Test hele sekvensen high -> medium -> low -> none stegvis."""
    state = HystereseState(nivå=RISIKO_HIGH, pending_nivå=None, pending_since=None)
    times = [NOW + timedelta(minutes=i) for i in range(0, 20)]

    # Minutt 0: rå == LOW, starter timer
    apply_hysteresis(state, rå_nivå=RISIKO_LOW, now=times[0], holdetid=HOLDETID)
    assert state.nivå == RISIKO_HIGH

    # Minutt 5: holdetid utløpt, går til MEDIUM
    apply_hysteresis(state, rå_nivå=RISIKO_LOW, now=times[5], holdetid=HOLDETID)
    assert state.nivå == RISIKO_MEDIUM

    # Minutt 10: holdetid utløpt på nytt, går til LOW
    apply_hysteresis(state, rå_nivå=RISIKO_LOW, now=times[10], holdetid=HOLDETID)
    assert state.nivå == RISIKO_LOW

    # Rå er fortsatt LOW, ingen nedgang lenger
    apply_hysteresis(state, rå_nivå=RISIKO_LOW, now=times[15], holdetid=HOLDETID)
    assert state.nivå == RISIKO_LOW
```

- [ ] **Step 2: Kjør, forvent FAIL**

Run: `pytest tests/test_hysteresis.py -v`
Expected: ImportError.

- [ ] **Step 3: Implementere HystereseState og apply_hysteresis**

```python
from datetime import timedelta
from .const import RISIKO_LEVELS, RISIKO_RANK


@dataclass
class HystereseState:
    """Stateful hysterese-tilstand."""
    nivå: str
    pending_nivå: str | None = None
    pending_since: datetime | None = None


def _nivå_ett_under(nivå: str) -> str:
    """Returner risiko-nivået ett trinn under det gitte. RISIKO_NONE returnerer seg selv."""
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
        # oppgang eller likt
        state.nivå = rå_nivå
        state.pending_nivå = None
        state.pending_since = None
        return

    # rå er lavere enn nåværende nivå -> nedgang i progress
    if state.pending_nivå != rå_nivå:
        # ny eller endret nedgang
        state.pending_nivå = rå_nivå
        state.pending_since = now
        return

    # samme pending som før, sjekk om holdetiden er utløpt
    if state.pending_since is None:
        state.pending_since = now
        return

    if (now - state.pending_since) >= holdetid:
        ett_under = _nivå_ett_under(state.nivå)
        state.nivå = ett_under
        if RISIKO_RANK[state.nivå] > rå_rank:
            # fortsatt over rå, starter ny timer for neste trinn
            state.pending_since = now
        else:
            state.pending_nivå = None
            state.pending_since = None
```

- [ ] **Step 4: Kjør, forvent PASS**

Run: `pytest tests/test_hysteresis.py -v`
Expected: 8 PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/effektvakt/coordinator.py tests/test_hysteresis.py
git commit -m "feat(coordinator): hysterese-state med multi-step nedgang"
```

---

### Task 12: EffektvaktCoordinator-klasse: minimal versjon (init + read sensors + projection)

**Files:**
- Modify: `custom_components/effektvakt/coordinator.py`
- Create: `tests/test_coordinator_projection.py`

- [ ] **Step 1: Test for projisert time-snitt-beregning**

```python
"""Tester for projisert time-snitt-beregning."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from custom_components.effektvakt.coordinator import compute_projected_avg


def test_projected_avg_uten_energy_sensor_starten_av_timen():
    """Ved minutt 0, projected = current_kw."""
    result = compute_projected_avg(
        actual_kwh_this_hour=0.0,
        current_kw=5.0,
        elapsed_h=0.0,
    )
    assert result == pytest.approx(5.0)


def test_projected_avg_midt_i_timen():
    """Ved minutt 30, halve timen er current_kw, halve er actual."""
    result = compute_projected_avg(
        actual_kwh_this_hour=2.0,  # 2 kWh på 30 min = snitt 4 kW
        current_kw=6.0,
        elapsed_h=0.5,
    )
    # 2 + 6 * 0.5 = 5.0
    assert result == pytest.approx(5.0)


def test_projected_avg_på_slutten_av_timen():
    """Ved minutt 60, projected = actual_kwh."""
    result = compute_projected_avg(
        actual_kwh_this_hour=4.5,
        current_kw=10.0,
        elapsed_h=1.0,
    )
    assert result == pytest.approx(4.5)


def test_projected_avg_minutter_55_av_60_blindspot():
    """Ved minutt 55, ny stor last gir minimal effekt på prediksjon."""
    result = compute_projected_avg(
        actual_kwh_this_hour=3.0,
        current_kw=20.0,  # plutselig veldig høy
        elapsed_h=55 / 60,
    )
    # 3 + 20 * 5/60 = 3 + 1.667 = 4.667
    assert result == pytest.approx(3.0 + 20.0 * 5 / 60, rel=1e-3)
```

- [ ] **Step 2: Kjør, forvent FAIL**

Run: `pytest tests/test_coordinator_projection.py -v`
Expected: ImportError.

- [ ] **Step 3: Implementere compute_projected_avg**

Legg til i `coordinator.py`:

```python
def compute_projected_avg(
    *,
    actual_kwh_this_hour: float,
    current_kw: float,
    elapsed_h: float,
) -> float:
    """Projisert time-snitt-kW.

    actual_kwh_this_hour: hva som er målt så langt denne klokketimen.
    current_kw: instant power-sensor-verdi.
    elapsed_h: hvor langt inn i timen vi er (0.0 til 1.0).
    """
    remaining_h = max(0.0, 1.0 - elapsed_h)
    return actual_kwh_this_hour + current_kw * remaining_h


def compute_elapsed_h(now: datetime) -> float:
    """Andel av klokketimen som er passert."""
    return (now.minute + now.second / 60) / 60
```

- [ ] **Step 4: Kjør, forvent PASS**

Run: `pytest tests/test_coordinator_projection.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/effektvakt/coordinator.py tests/test_coordinator_projection.py
git commit -m "feat(coordinator): compute_projected_avg + compute_elapsed_h"
```

---

### Task 13: Full coordinator-klasse: init, _async_update_data, integrert beregning

**Files:**
- Modify: `custom_components/effektvakt/coordinator.py`
- Create: `tests/test_coordinator_integration.py`

- [ ] **Step 1: Integrert test for coordinator full pipeline**

```python
"""Tester for full coordinator-pipeline (sensor → projected → risiko)."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from custom_components.effektvakt.coordinator import EffektvaktCoordinator
from custom_components.effektvakt.const import RISIKO_HIGH, RISIKO_LOW, RISIKO_MEDIUM, RISIKO_NONE
from tests.conftest import make_entry, make_hass_with_states, make_state


@pytest.fixture
def base_states():
    """Power 3 kW, energy 100 kWh."""
    return {
        "sensor.power": make_state("3000", unit="W"),
        "sensor.energy": make_state("100.0", unit="kWh"),
    }


def _make_coordinator(states, entry_overrides=None):
    overrides = entry_overrides or {}
    entry = make_entry(**overrides)
    hass = make_hass_with_states(states)
    with patch("custom_components.effektvakt.coordinator.Store"):
        coord = EffektvaktCoordinator(hass, entry)
    return coord


@pytest.mark.asyncio
async def test_coordinator_init_leser_konfig(base_states):
    coord = _make_coordinator(base_states)
    assert coord.power_sensor == "sensor.power"
    assert coord.energy_sensor == "sensor.energy"
    assert coord.safety_buffer_kw == 1.0
    assert coord._daily_max_kw == {}


@pytest.mark.asyncio
async def test_coordinator_low_power_gir_none_risk(base_states):
    """3 kW, BKK-trinn: ligger godt under første trinn, risiko = none."""
    coord = _make_coordinator(base_states)
    with patch(
        "custom_components.effektvakt.coordinator.dt_util_now",
        return_value=datetime(2026, 5, 25, 14, 30, 0),
    ):
        data = await coord._async_update_data()
    assert data["risiko_niva"] == RISIKO_NONE
    assert data["projected_avg_kw"] < 5
```

- [ ] **Step 2: Kjør, forvent FAIL**

Run: `pytest tests/test_coordinator_integration.py -v`
Expected: ImportError (EffektvaktCoordinator finnes ikke ennå).

- [ ] **Step 3: Implementere EffektvaktCoordinator**

Legg til på toppen av `coordinator.py`:

```python
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util_module

from .const import (
    CONF_DSO,
    CONF_ENERGY_SENSOR,
    CONF_MIN_RISIKO_FOR_KUTT,
    CONF_POWER_SENSOR,
    CONF_RISIKO_HOLDETID_MINUTTER,
    CONF_SAFETY_BUFFER_KW,
    CONF_KAPASITETSTRINN_CUSTOM,
    DEFAULT_MIN_RISIKO_FOR_KUTT,
    DEFAULT_RISIKO_HOLDETID_MINUTTER,
    DEFAULT_SAFETY_BUFFER_KW,
    DOMAIN,
    STORAGE_VERSION,
    TICK_INTERVAL_BY_RISIKO,
)
from .dso import KAPASITETSTRINN_PER_DSO


def dt_util_now():
    """Wrapper for monkeypatch-vennlig now()."""
    return dt_util_module.now()
```

Og hovedklassen:

```python
class EffektvaktCoordinator(DataUpdateCoordinator):
    """Coordinator for Effektvakt."""

    def __init__(self, hass, entry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=TICK_INTERVAL_BY_RISIKO[RISIKO_NONE]),
        )
        self.entry = entry
        self.power_sensor = entry.data.get(CONF_POWER_SENSOR)
        self.energy_sensor = entry.data.get(CONF_ENERGY_SENSOR)
        self.safety_buffer_kw = float(entry.data.get(CONF_SAFETY_BUFFER_KW, DEFAULT_SAFETY_BUFFER_KW))
        self.min_risiko_for_kutt = entry.data.get(CONF_MIN_RISIKO_FOR_KUTT, DEFAULT_MIN_RISIKO_FOR_KUTT)
        self.risiko_holdetid = timedelta(minutes=int(
            entry.data.get(CONF_RISIKO_HOLDETID_MINUTTER, DEFAULT_RISIKO_HOLDETID_MINUTTER)
        ))

        dso_id = entry.data.get(CONF_DSO)
        custom = entry.data.get(CONF_KAPASITETSTRINN_CUSTOM)
        if custom:
            self.kapasitetstrinn = [(float(t[0]), int(t[1])) for t in custom]
        else:
            dso_info = KAPASITETSTRINN_PER_DSO.get(dso_id)
            self.kapasitetstrinn = list(dso_info["kapasitetstrinn"]) if dso_info else []

        # Mutable state
        self._daily_max_kw: dict[date, float] = {}
        self._current_month: str = dt_util_now().strftime("%Y-%m")
        self._current_hour_kwh: float = 0.0
        self._current_hour_start: datetime | None = None
        self._current_hour_bucket: tuple[int, timedelta | None] | None = None
        self._energy_at_hour_start: float | None = None
        self._previous_month_top_3_snitt_kw: float | None = None
        self._previous_month_name: str | None = None
        self._hysterese_state = HystereseState(nivå=RISIKO_NONE)
        self._last_successful_update: datetime | None = None
        self._store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}")
        self._store_loaded = False

    async def _load_stored_data(self) -> None:
        """Last persistert state fra .storage. Kalles én gang ved oppstart."""
        if self._store_loaded:
            return
        stored = await self._store.async_load()
        self._store_loaded = True
        if not stored:
            return
        data = stored.get("data", {})
        # daily_max_kw lagres som {"YYYY-MM-DD": kw}
        for date_str, kw in (data.get("daily_max_kw") or {}).items():
            try:
                d = date.fromisoformat(date_str)
                self._daily_max_kw[d] = float(kw)
            except (ValueError, TypeError):
                continue
        self._current_hour_kwh = float(data.get("current_hour_kwh", 0.0))
        self._energy_at_hour_start = data.get("energy_at_hour_start")
        self._previous_month_top_3_snitt_kw = data.get("previous_month_top_3_snitt_kw")
        self._previous_month_name = data.get("previous_month_name")
        hyst = data.get("hysterese_state", {})
        if hyst.get("nivå") in RISIKO_LEVELS:
            self._hysterese_state.nivå = hyst["nivå"]

    async def _persist(self) -> None:
        """Skriv state til .storage."""
        await self._store.async_save({
            "data": {
                "current_month": self._current_month,
                "daily_max_kw": {d.isoformat(): kw for d, kw in self._daily_max_kw.items()},
                "current_hour_kwh": self._current_hour_kwh,
                "energy_at_hour_start": self._energy_at_hour_start,
                "previous_month_top_3_snitt_kw": self._previous_month_top_3_snitt_kw,
                "previous_month_name": self._previous_month_name,
                "hysterese_state": {
                    "nivå": self._hysterese_state.nivå,
                    "pending_nivå": self._hysterese_state.pending_nivå,
                    "pending_since": (
                        self._hysterese_state.pending_since.isoformat()
                        if self._hysterese_state.pending_since else None
                    ),
                },
            }
        })

    async def _async_update_data(self) -> dict:
        """Hovedoppdatering: leser sensorer, regner, oppdaterer state."""
        await self._load_stored_data()
        now = dt_util_now()

        # Sjekk klokketime-rollover
        hour_bucket = (now.hour, now.utcoffset())
        if self._current_hour_bucket is not None and self._current_hour_bucket != hour_bucket:
            self._finalize_hour()
        if self._current_hour_bucket is None or self._current_hour_bucket != hour_bucket:
            self._current_hour_bucket = hour_bucket
            self._current_hour_start = now.replace(minute=0, second=0, microsecond=0)
            self._current_hour_kwh = 0.0

        # Sjekk månedsskifte
        month_str = now.strftime("%Y-%m")
        if month_str != self._current_month:
            self._handle_month_rollover()
            self._current_month = month_str

        # Les sensorer
        current_kw = read_power_kw(self.hass, self.power_sensor) or 0.0
        energy_now = read_energy_kwh(self.hass, self.energy_sensor)

        # Akkumuler kwh denne timen
        if energy_now is not None:
            if self._energy_at_hour_start is None:
                self._energy_at_hour_start = energy_now
            else:
                delta = energy_now - self._energy_at_hour_start - self._current_hour_kwh
                if delta > 0:
                    self._current_hour_kwh += delta
                # Negative deltas ignoreres (counter reset, meter-bytte)

        elapsed_h = compute_elapsed_h(now)
        projected_avg = compute_projected_avg(
            actual_kwh_this_hour=self._current_hour_kwh,
            current_kw=current_kw,
            elapsed_h=elapsed_h,
        )

        # Tier-info
        tiers = lookup_tiers(projected_kw=projected_avg, trinn=self.kapasitetstrinn)

        # Effective threshold med topp-2-dager-bevissthet
        if tiers.next_threshold_kw is None:
            effective_threshold = float("inf")  # over høyeste trinn, ingenting å beskytte mot
        else:
            effective_threshold = compute_effective_threshold(
                next_tier_threshold_kw=tiers.next_threshold_kw,
                daily_max_kw=self._daily_max_kw,
            )

        margin = effective_threshold - projected_avg
        rå = classify_raw_risk(margin_kw=margin, safety_buffer_kw=self.safety_buffer_kw)
        apply_hysteresis(self._hysterese_state, rå_nivå=rå, now=now, holdetid=self.risiko_holdetid)

        # Adaptiv tick
        new_interval = timedelta(seconds=TICK_INTERVAL_BY_RISIKO[self._hysterese_state.nivå])
        if self.update_interval != new_interval:
            self.update_interval = new_interval

        self._last_successful_update = now

        topp_3 = top_n_average(self._daily_max_kw, n=3) or 0.0
        topp_2 = top_n_average(self._daily_max_kw, n=2)

        await self._persist()

        return {
            "projected_avg_kw": round(projected_avg, 3),
            "current_kw": round(current_kw, 3),
            "actual_kwh_this_hour": round(self._current_hour_kwh, 3),
            "elapsed_minutes_in_hour": int(elapsed_h * 60),
            "margin_kw": round(margin, 3),
            "effective_threshold_kw": effective_threshold,
            "next_tier_threshold_kw": tiers.next_threshold_kw,
            "prev_tier_threshold_kw": tiers.prev_threshold_kw,
            "next_tier_pris_per_maned": tiers.next_pris_per_mnd,
            "topp_3_snitt_denne_maned_kw": round(topp_3, 3),
            "topp_2_snitt_denne_maned_kw": round(topp_2, 3) if topp_2 else None,
            "kutt_anbefalt_kw": max(0.0, -margin),
            "risiko_niva": self._hysterese_state.nivå,
            "raw_risiko_niva": rå,
            "last_update": now.isoformat(),
        }

    def _finalize_hour(self) -> None:
        """Lagre forrige times kWh som potensiell dags-maks."""
        if self._current_hour_kwh > 0 and self._current_hour_start is not None:
            d = self._current_hour_start.date()
            existing = self._daily_max_kw.get(d, 0.0)
            if self._current_hour_kwh > existing:
                self._daily_max_kw[d] = round(self._current_hour_kwh, 3)
        # Reset for ny time, men behold _energy_at_hour_start oppdatert
        self._current_hour_kwh = 0.0
        # _energy_at_hour_start oppdateres ved neste tick's energy_now-avlesning

    def _handle_month_rollover(self) -> None:
        """Arkiver forrige måneds topp-3, tøm daily_max for ny måned."""
        topp_3 = top_n_average(self._daily_max_kw, n=3)
        if topp_3 is not None:
            self._previous_month_top_3_snitt_kw = round(topp_3, 3)
            self._previous_month_name = self._current_month
        self._daily_max_kw = {}
```

- [ ] **Step 4: Kjør integrasjonstesten, forvent PASS**

Run: `pytest tests/test_coordinator_integration.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Kjør alle eksisterende tester for å sjekke regresjoner**

Run: `pytest tests/ -v`
Expected: alle tester fra Task 5-12 fortsatt PASS.

- [ ] **Step 6: Commit**

```bash
git add custom_components/effektvakt/coordinator.py tests/test_coordinator_integration.py
git commit -m "feat(coordinator): EffektvaktCoordinator med adaptive tick og persistence"
```

---

### Task 14: Watchdog (uavhengig av coordinator)

**Files:**
- Modify: `custom_components/effektvakt/coordinator.py`
- Create: `tests/test_watchdog.py`

- [ ] **Step 1: Test for watchdog**

```python
"""Tester for watchdog som flagger stale coordinator."""

from __future__ import annotations

from datetime import datetime, timedelta

from custom_components.effektvakt.coordinator import is_coordinator_stale
from custom_components.effektvakt.const import WATCHDOG_STALE_THRESHOLD_SECONDS


NOW = datetime(2026, 5, 25, 14, 0, 0)


def test_stale_aldri_oppdatert():
    assert is_coordinator_stale(last_successful_update=None, now=NOW) is True


def test_stale_oppdatert_for_lenge_siden():
    last = NOW - timedelta(seconds=WATCHDOG_STALE_THRESHOLD_SECONDS + 1)
    assert is_coordinator_stale(last_successful_update=last, now=NOW) is True


def test_ikke_stale_oppdatert_nylig():
    last = NOW - timedelta(seconds=30)
    assert is_coordinator_stale(last_successful_update=last, now=NOW) is False


def test_ikke_stale_på_grensen():
    last = NOW - timedelta(seconds=WATCHDOG_STALE_THRESHOLD_SECONDS - 1)
    assert is_coordinator_stale(last_successful_update=last, now=NOW) is False
```

- [ ] **Step 2: Kjør, forvent FAIL**

Run: `pytest tests/test_watchdog.py -v`
Expected: ImportError.

- [ ] **Step 3: Implementere is_coordinator_stale**

Legg til i `coordinator.py`:

```python
from .const import WATCHDOG_STALE_THRESHOLD_SECONDS


def is_coordinator_stale(
    *,
    last_successful_update: datetime | None,
    now: datetime,
) -> bool:
    """True hvis siste vellykkede oppdatering er eldre enn watchdog-terskel."""
    if last_successful_update is None:
        return True
    return (now - last_successful_update).total_seconds() > WATCHDOG_STALE_THRESHOLD_SECONDS
```

- [ ] **Step 4: Kjør, forvent PASS**

Run: `pytest tests/test_watchdog.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/effektvakt/coordinator.py tests/test_watchdog.py
git commit -m "feat(coordinator): watchdog-helper for stale-deteksjon"
```

---

## Phase 3: Sensors & binary_sensor

### Task 15: sensor.py: 4 sensorer

**Files:**
- Create: `custom_components/effektvakt/sensor.py`
- Create: `tests/test_sensor.py`

- [ ] **Step 1: Test for sensor-klassene**

```python
"""Tester for sensor.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.effektvakt.sensor import (
    EffektvaktProjisertSensor,
    EffektvaktMarginSensor,
    EffektvaktTopp3Sensor,
    EffektvaktRisikoSensor,
)


@pytest.fixture
def coord_mock():
    coord = MagicMock()
    coord.entry.entry_id = "test_entry"
    coord.data = {
        "projected_avg_kw": 5.5,
        "margin_kw": 4.5,
        "topp_3_snitt_denne_maned_kw": 4.2,
        "risiko_niva": "low",
        "next_tier_threshold_kw": 10.0,
        "next_tier_pris_per_maned": 415,
        "prev_tier_threshold_kw": 5.0,
        "effective_threshold_kw": 10.0,
        "kutt_anbefalt_kw": 0.0,
        "topp_2_snitt_denne_maned_kw": 4.0,
        "elapsed_minutes_in_hour": 30,
        "actual_kwh_this_hour": 2.5,
        "current_kw": 5.5,
        "last_update": "2026-05-25T14:30:00",
    }
    return coord


def test_projisert_sensor_native_value(coord_mock):
    s = EffektvaktProjisertSensor(coord_mock)
    assert s.native_value == 5.5
    assert s.native_unit_of_measurement == "kW"


def test_margin_sensor_har_anbefalt_kw_attributt(coord_mock):
    s = EffektvaktMarginSensor(coord_mock)
    assert s.native_value == 4.5
    attrs = s.extra_state_attributes
    assert attrs["kutt_anbefalt_kw"] == 0.0
    assert attrs["next_tier_threshold_kw"] == 10.0
    assert attrs["prev_tier_threshold_kw"] == 5.0


def test_topp_3_sensor(coord_mock):
    s = EffektvaktTopp3Sensor(coord_mock)
    assert s.native_value == 4.2


def test_risiko_sensor_native_value(coord_mock):
    s = EffektvaktRisikoSensor(coord_mock)
    assert s.native_value == "low"


def test_risiko_sensor_options(coord_mock):
    s = EffektvaktRisikoSensor(coord_mock)
    assert "none" in s.options
    assert "high" in s.options
```

- [ ] **Step 2: Kjør, forvent FAIL**

Run: `pytest tests/test_sensor.py -v`
Expected: ImportError.

- [ ] **Step 3: Implementere sensor.py**

```python
"""Sensor-plattformer for Effektvakt."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, RISIKO_LEVELS

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import EffektvaktCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from config entry."""
    coordinator: EffektvaktCoordinator = entry.runtime_data
    async_add_entities([
        EffektvaktProjisertSensor(coordinator),
        EffektvaktMarginSensor(coordinator),
        EffektvaktTopp3Sensor(coordinator),
        EffektvaktRisikoSensor(coordinator),
    ])


class _EffektvaktBaseSensor(CoordinatorEntity, SensorEntity):
    """Felles base for Effektvakt-sensorer."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EffektvaktCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{self._sensor_key}"

    @property
    def _sensor_key(self) -> str:
        raise NotImplementedError

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        d = self.coordinator.data
        if not d:
            return None
        return {
            "elapsed_minutes_in_hour": d.get("elapsed_minutes_in_hour"),
            "actual_kwh_this_hour": d.get("actual_kwh_this_hour"),
            "current_kw": d.get("current_kw"),
            "next_tier_threshold_kw": d.get("next_tier_threshold_kw"),
            "next_tier_pris_per_maned": d.get("next_tier_pris_per_maned"),
            "prev_tier_threshold_kw": d.get("prev_tier_threshold_kw"),
            "effective_threshold_kw": d.get("effective_threshold_kw"),
            "kutt_anbefalt_kw": d.get("kutt_anbefalt_kw"),
            "topp_2_snitt_denne_maned_kw": d.get("topp_2_snitt_denne_maned_kw"),
            "last_update": d.get("last_update"),
        }


class EffektvaktProjisertSensor(_EffektvaktBaseSensor):
    _attr_name = "Projisert time-snitt"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = "kW"
    _attr_state_class = SensorStateClass.MEASUREMENT

    _sensor_key = "projisert_time_snitt"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get("projected_avg_kw") if self.coordinator.data else None


class EffektvaktMarginSensor(_EffektvaktBaseSensor):
    _attr_name = "Margin til neste trinn"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = "kW"
    _attr_state_class = SensorStateClass.MEASUREMENT

    _sensor_key = "margin_til_neste_trinn"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get("margin_kw") if self.coordinator.data else None


class EffektvaktTopp3Sensor(_EffektvaktBaseSensor):
    _attr_name = "Topp-3 snitt denne måned"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = "kW"
    _attr_state_class = SensorStateClass.MEASUREMENT

    _sensor_key = "topp_3_snitt_denne_maned"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get("topp_3_snitt_denne_maned_kw") if self.coordinator.data else None


class EffektvaktRisikoSensor(_EffektvaktBaseSensor):
    _attr_name = "Risiko-nivå"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(RISIKO_LEVELS)

    _sensor_key = "risiko_niva"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.get("risiko_niva") if self.coordinator.data else None

    @property
    def options(self) -> list[str]:
        return list(RISIKO_LEVELS)
```

- [ ] **Step 4: Kjør, forvent PASS**

Run: `pytest tests/test_sensor.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/effektvakt/sensor.py tests/test_sensor.py
git commit -m "feat(sensor): 4 sensorer med diagnostikk-attributter"
```

---

### Task 16: binary_sensor.py

**Files:**
- Create: `custom_components/effektvakt/binary_sensor.py`
- Create: `tests/test_binary_sensor.py`

- [ ] **Step 1: Test**

```python
"""Tester for binary_sensor.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.effektvakt.binary_sensor import EffektvaktKuttNedAnbefaltBinarySensor
from custom_components.effektvakt.const import RISIKO_HIGH, RISIKO_LOW, RISIKO_MEDIUM, RISIKO_NONE


@pytest.mark.parametrize("risiko,min_for_kutt,expected", [
    (RISIKO_NONE, "medium", False),
    (RISIKO_LOW, "medium", False),
    (RISIKO_MEDIUM, "medium", True),
    (RISIKO_HIGH, "medium", True),
    (RISIKO_LOW, "low", True),
    (RISIKO_HIGH, "high", True),
    (RISIKO_MEDIUM, "high", False),
])
def test_binary_sensor_is_on(risiko: str, min_for_kutt: str, expected: bool):
    coord = MagicMock()
    coord.entry.entry_id = "test"
    coord.min_risiko_for_kutt = min_for_kutt
    coord.data = {"risiko_niva": risiko}
    bs = EffektvaktKuttNedAnbefaltBinarySensor(coord)
    assert bs.is_on is expected


def test_binary_sensor_unknown_when_no_data():
    coord = MagicMock()
    coord.entry.entry_id = "test"
    coord.min_risiko_for_kutt = "medium"
    coord.data = None
    bs = EffektvaktKuttNedAnbefaltBinarySensor(coord)
    assert bs.is_on is None
```

- [ ] **Step 2: Kjør, forvent FAIL**

Run: `pytest tests/test_binary_sensor.py -v`
Expected: ImportError.

- [ ] **Step 3: Implementere binary_sensor.py**

```python
"""Binary sensor for Effektvakt."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import RISIKO_RANK

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import EffektvaktCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EffektvaktCoordinator = entry.runtime_data
    async_add_entities([EffektvaktKuttNedAnbefaltBinarySensor(coordinator)])


class EffektvaktKuttNedAnbefaltBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """`on` når hysteresefull risiko ≥ min_risiko_for_kutt."""

    _attr_has_entity_name = True
    _attr_name = "Kutt ned anbefalt"

    def __init__(self, coordinator: EffektvaktCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_kutt_ned_anbefalt"

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        nivå = self.coordinator.data.get("risiko_niva")
        if nivå is None:
            return None
        threshold = self.coordinator.min_risiko_for_kutt
        return RISIKO_RANK.get(nivå, -1) >= RISIKO_RANK.get(threshold, 99)
```

- [ ] **Step 4: Kjør, forvent PASS**

Run: `pytest tests/test_binary_sensor.py -v`
Expected: 8 PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/effektvakt/binary_sensor.py tests/test_binary_sensor.py
git commit -m "feat(binary_sensor): kutt_ned_anbefalt basert på hysteresefull risiko"
```

---

## Phase 4: Config flow

### Task 17: strings.json + translations

**Files:**
- Create: `custom_components/effektvakt/strings.json`
- Create: `custom_components/effektvakt/translations/en.json`
- Create: `custom_components/effektvakt/translations/nb.json`

- [ ] **Step 1: strings.json (en + nb felles base)**

```json
{
  "title": "Effektvakt",
  "config": {
    "step": {
      "user": {
        "title": "Velg nettselskap",
        "description": "Effektvakt bruker kapasitetstrinn fra ditt nettselskap for å forutse trinn-overskridelser.",
        "data": {
          "dso": "Nettselskap"
        }
      },
      "sensors": {
        "title": "Velg sensorer",
        "description": "Effektvakt trenger en power-sensor (instant-effekt i W eller kW) og helst en energy-sensor (kumulativ kWh).",
        "data": {
          "power_sensor": "Power-sensor (instant)",
          "energy_sensor": "Energy-sensor (kumulativ, valgfri men anbefalt)",
          "confirm_peak_sensor": "Jeg bekrefter at sensoren rapporterer instant-effekt"
        }
      },
      "tuning": {
        "title": "Innstillinger",
        "description": "Disse kan endres senere via integrasjonens innstillinger.",
        "data": {
          "safety_buffer_kw": "Sikkerhetsmargin (kW)",
          "min_risiko_for_kutt": "Laveste risiko som trigger kutt",
          "risiko_holdetid_minutter": "Holdetid på risiko-sensor ved nedgang (min)"
        }
      },
      "pricing": {
        "title": "Egendefinerte kapasitetstrinn",
        "description": "Skriv inn dine egne kW-terskler og priser per måned. Én linje per trinn, sortert lavest først.",
        "data": {
          "kapasitetstrinn_custom": "Kapasitetstrinn (JSON, f.eks. [[2, 130], [5, 230]])"
        }
      }
    },
    "error": {
      "sensor_not_found": "Sensoren finnes ikke",
      "power_unit_invalid": "Power-sensor må ha enhet W eller kW",
      "energy_unit_invalid": "Energy-sensor må ha enhet Wh eller kWh",
      "peak_sensor_warning": "Sensoren ser ut som peak/snitt-aggregat. Velg instant-sensor eller bekreft.",
      "kapasitetstrinn_invalid": "Kapasitetstrinn må være liste av [kW, kr] par sortert stigende",
      "already_configured": "Denne power-sensoren er allerede konfigurert"
    },
    "abort": {
      "already_configured": "Allerede konfigurert"
    }
  },
  "options": {
    "step": {
      "init": {
        "title": "Effektvakt-innstillinger",
        "data": {
          "safety_buffer_kw": "Sikkerhetsmargin (kW)",
          "min_risiko_for_kutt": "Laveste risiko som trigger kutt",
          "risiko_holdetid_minutter": "Holdetid på risiko-sensor ved nedgang (min)"
        }
      }
    }
  },
  "services": {
    "set_safety_buffer": {
      "name": "Sett sikkerhetsmargin",
      "description": "Endre safety_buffer_kw uten reload.",
      "fields": {
        "kw": {
          "name": "kW",
          "description": "Ny safety_buffer-verdi i kW"
        }
      }
    },
    "reset_topp_3": {
      "name": "Nullstill topp-3-buffer",
      "description": "Tøm daily_max-historikken for inneværende måned."
    }
  }
}
```

- [ ] **Step 2: en.json identisk struktur, oversatt**

```json
{
  "title": "Effektvakt",
  "config": {
    "step": {
      "user": {
        "title": "Select grid company",
        "description": "Effektvakt uses your grid company's capacity tiers to predict tier crossings.",
        "data": {
          "dso": "Grid company"
        }
      },
      "sensors": {
        "title": "Select sensors",
        "description": "Effektvakt needs a power sensor (instant power in W or kW) and ideally an energy sensor (cumulative kWh).",
        "data": {
          "power_sensor": "Power sensor (instant)",
          "energy_sensor": "Energy sensor (cumulative, optional but recommended)",
          "confirm_peak_sensor": "I confirm the sensor reports instantaneous power"
        }
      },
      "tuning": {
        "title": "Settings",
        "description": "These can be changed later via integration options.",
        "data": {
          "safety_buffer_kw": "Safety buffer (kW)",
          "min_risiko_for_kutt": "Minimum risk level that triggers shed",
          "risiko_holdetid_minutter": "Risk sensor hold-time on de-escalation (min)"
        }
      },
      "pricing": {
        "title": "Custom capacity tiers",
        "description": "Enter your own kW thresholds and monthly prices. Sorted lowest first.",
        "data": {
          "kapasitetstrinn_custom": "Capacity tiers (JSON, e.g. [[2, 130], [5, 230]])"
        }
      }
    },
    "error": {
      "sensor_not_found": "Sensor not found",
      "power_unit_invalid": "Power sensor must have unit W or kW",
      "energy_unit_invalid": "Energy sensor must have unit Wh or kWh",
      "peak_sensor_warning": "Sensor looks like a peak/average aggregate. Pick an instant sensor or confirm.",
      "kapasitetstrinn_invalid": "Capacity tiers must be list of [kW, NOK] pairs sorted ascending",
      "already_configured": "This power sensor is already configured"
    },
    "abort": {
      "already_configured": "Already configured"
    }
  },
  "options": {
    "step": {
      "init": {
        "title": "Effektvakt settings",
        "data": {
          "safety_buffer_kw": "Safety buffer (kW)",
          "min_risiko_for_kutt": "Minimum risk level that triggers shed",
          "risiko_holdetid_minutter": "Risk sensor hold-time on de-escalation (min)"
        }
      }
    }
  },
  "services": {
    "set_safety_buffer": {
      "name": "Set safety buffer",
      "description": "Change safety_buffer_kw without reload.",
      "fields": {
        "kw": {
          "name": "kW",
          "description": "New safety buffer value in kW"
        }
      }
    },
    "reset_topp_3": {
      "name": "Reset top-3 buffer",
      "description": "Clear daily_max history for the current month."
    }
  }
}
```

- [ ] **Step 3: nb.json identisk med strings.json (norsk er primært)**

```bash
cp custom_components/effektvakt/strings.json custom_components/effektvakt/translations/nb.json
```

- [ ] **Step 4: Verifiser JSON-validitet**

```bash
jq empty custom_components/effektvakt/strings.json
jq empty custom_components/effektvakt/translations/en.json
jq empty custom_components/effektvakt/translations/nb.json
echo OK
```

- [ ] **Step 5: Commit**

```bash
git add custom_components/effektvakt/strings.json custom_components/effektvakt/translations/
git commit -m "i18n: strings + en/nb-oversettelser for config flow og services"
```

---

### Task 18: config_flow.py: heuristikk for peak-sensor + validering

**Files:**
- Create: `custom_components/effektvakt/config_flow.py`
- Create: `tests/test_config_flow.py`

- [ ] **Step 1: Test for peak-sensor-deteksjon**

```python
"""Tester for config_flow-helpers."""

from __future__ import annotations

import pytest

from custom_components.effektvakt.config_flow import looks_like_peak_sensor


@pytest.mark.parametrize("entity_id,friendly,expected", [
    ("sensor.tibber_max_power", "Tibber Max Power", True),
    ("sensor.house_peak_power", "House Peak", True),
    ("sensor.power_max_per_hour", "Power Max Per Hour", True),
    ("sensor.tibber_pulse_power", "Tibber Pulse Power", False),
    ("sensor.house_power", "House Power", False),
    ("sensor.average_power", "Average Power", True),  # average i navn
    ("sensor.power_average_per_hour", "Power Average", True),
])
def test_looks_like_peak_sensor(entity_id: str, friendly: str, expected: bool):
    assert looks_like_peak_sensor(entity_id, friendly_name=friendly) is expected
```

- [ ] **Step 2: Kjør, forvent FAIL**

Run: `pytest tests/test_config_flow.py -v`
Expected: ImportError.

- [ ] **Step 3: Implementere config_flow.py med heuristikk-funksjonen**

```python
"""Config flow for Effektvakt."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CONFIRM_PEAK_SENSOR,
    CONF_DSO,
    CONF_ENERGY_SENSOR,
    CONF_KAPASITETSTRINN_CUSTOM,
    CONF_MIN_RISIKO_FOR_KUTT,
    CONF_POWER_SENSOR,
    CONF_RISIKO_HOLDETID_MINUTTER,
    CONF_SAFETY_BUFFER_KW,
    DEFAULT_DSO,
    DEFAULT_MIN_RISIKO_FOR_KUTT,
    DEFAULT_RISIKO_HOLDETID_MINUTTER,
    DEFAULT_SAFETY_BUFFER_KW,
    DOMAIN,
    PEAK_SENSOR_FRIENDLY_NAME_KEYWORDS,
    PEAK_SENSOR_NAME_PATTERNS,
    RISIKO_LEVELS,
    VALID_ENERGY_UNITS,
    VALID_POWER_UNITS,
)
from .dso import KAPASITETSTRINN_PER_DSO

if TYPE_CHECKING:
    from homeassistant.data_entry_flow import FlowResult

_LOGGER = logging.getLogger(__name__)


def looks_like_peak_sensor(entity_id: str, *, friendly_name: str = "") -> bool:
    """True hvis sensor-navn eller friendly_name antyder peak/snitt-aggregat."""
    lower_id = entity_id.lower()
    if any(pat in lower_id for pat in PEAK_SENSOR_NAME_PATTERNS):
        return True
    lower_name = friendly_name.lower()
    if any(kw in lower_name for kw in PEAK_SENSOR_FRIENDLY_NAME_KEYWORDS):
        return True
    return False


def _dso_options() -> list[selector.SelectOptionDict]:
    options = [
        selector.SelectOptionDict(value=k, label=v["navn"])
        for k, v in sorted(KAPASITETSTRINN_PER_DSO.items(), key=lambda kv: kv[1]["navn"])
    ]
    options.append(selector.SelectOptionDict(value="custom", label="Egendefinert"))
    return options


class EffektvaktConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_sensors()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_DSO, default=DEFAULT_DSO): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=_dso_options(),
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
            }),
        )

    async def async_step_sensors(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            power_id = user_input[CONF_POWER_SENSOR]
            energy_id = user_input.get(CONF_ENERGY_SENSOR)
            confirm_peak = user_input.get(CONF_CONFIRM_PEAK_SENSOR, False)

            power_state = self.hass.states.get(power_id)
            if power_state is None:
                errors[CONF_POWER_SENSOR] = "sensor_not_found"
            else:
                unit = (power_state.attributes or {}).get("unit_of_measurement")
                if unit not in VALID_POWER_UNITS:
                    errors[CONF_POWER_SENSOR] = "power_unit_invalid"
                else:
                    friendly = (power_state.attributes or {}).get("friendly_name", "")
                    if looks_like_peak_sensor(power_id, friendly_name=friendly) and not confirm_peak:
                        errors[CONF_POWER_SENSOR] = "peak_sensor_warning"

            if energy_id:
                e_state = self.hass.states.get(energy_id)
                if e_state is None:
                    errors[CONF_ENERGY_SENSOR] = "sensor_not_found"
                else:
                    e_unit = (e_state.attributes or {}).get("unit_of_measurement")
                    if e_unit not in VALID_ENERGY_UNITS:
                        errors[CONF_ENERGY_SENSOR] = "energy_unit_invalid"

            # unique_id-sjekk
            if not errors:
                unique_id = f"{DOMAIN}_{power_id}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                self._data.update(user_input)
                if self._data[CONF_DSO] == "custom":
                    return await self.async_step_pricing()
                return await self.async_step_tuning()

        return self.async_show_form(
            step_id="sensors",
            data_schema=vol.Schema({
                vol.Required(CONF_POWER_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="power"),
                ),
                vol.Optional(CONF_ENERGY_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="energy"),
                ),
                vol.Optional(CONF_CONFIRM_PEAK_SENSOR, default=False): selector.BooleanSelector(),
            }),
            errors=errors,
        )

    async def async_step_pricing(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                raw = json.loads(user_input[CONF_KAPASITETSTRINN_CUSTOM])
                if not isinstance(raw, list) or not raw:
                    raise ValueError
                normalized = []
                prev_kw = -1.0
                for entry in raw:
                    if not (isinstance(entry, list | tuple) and len(entry) == 2):
                        raise ValueError
                    kw, pris = float(entry[0]), int(entry[1])
                    if kw <= prev_kw:
                        raise ValueError
                    normalized.append((kw, pris))
                    prev_kw = kw
                self._data[CONF_KAPASITETSTRINN_CUSTOM] = normalized
                return await self.async_step_tuning()
            except (ValueError, TypeError, json.JSONDecodeError):
                errors[CONF_KAPASITETSTRINN_CUSTOM] = "kapasitetstrinn_invalid"

        return self.async_show_form(
            step_id="pricing",
            data_schema=vol.Schema({
                vol.Required(CONF_KAPASITETSTRINN_CUSTOM): str,
            }),
            errors=errors,
        )

    async def async_step_tuning(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(
                title=KAPASITETSTRINN_PER_DSO.get(self._data[CONF_DSO], {}).get("navn", "Effektvakt"),
                data=self._data,
            )

        return self.async_show_form(
            step_id="tuning",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_SAFETY_BUFFER_KW, default=DEFAULT_SAFETY_BUFFER_KW
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.1, max=5, step=0.1, mode=selector.NumberSelectorMode.SLIDER
                    ),
                ),
                vol.Required(
                    CONF_MIN_RISIKO_FOR_KUTT, default=DEFAULT_MIN_RISIKO_FOR_KUTT
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=lvl, label=lvl)
                            for lvl in RISIKO_LEVELS if lvl != "none"
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
                vol.Required(
                    CONF_RISIKO_HOLDETID_MINUTTER, default=DEFAULT_RISIKO_HOLDETID_MINUTTER
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=30, mode=selector.NumberSelectorMode.BOX),
                ),
            }),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return EffektvaktOptionsFlow(config_entry)


class EffektvaktOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        data = self.config_entry.data
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_SAFETY_BUFFER_KW,
                    default=data.get(CONF_SAFETY_BUFFER_KW, DEFAULT_SAFETY_BUFFER_KW),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0.1, max=5, step=0.1, mode=selector.NumberSelectorMode.SLIDER),
                ),
                vol.Required(
                    CONF_MIN_RISIKO_FOR_KUTT,
                    default=data.get(CONF_MIN_RISIKO_FOR_KUTT, DEFAULT_MIN_RISIKO_FOR_KUTT),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=lvl, label=lvl)
                            for lvl in RISIKO_LEVELS if lvl != "none"
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    ),
                ),
                vol.Required(
                    CONF_RISIKO_HOLDETID_MINUTTER,
                    default=data.get(CONF_RISIKO_HOLDETID_MINUTTER, DEFAULT_RISIKO_HOLDETID_MINUTTER),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=30, mode=selector.NumberSelectorMode.BOX),
                ),
            }),
        )
```

- [ ] **Step 4: Kjør peak-sensor-testen, forvent PASS**

Run: `pytest tests/test_config_flow.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/effektvakt/config_flow.py tests/test_config_flow.py
git commit -m "feat(config_flow): 3-stegs flow med peak-sensor-heuristikk"
```

---

## Phase 5: __init__.py og services

### Task 19: __init__.py: setup_entry, watchdog, services

**Files:**
- Create: `custom_components/effektvakt/__init__.py`
- Create: `custom_components/effektvakt/services.yaml`
- Create: `tests/test_init.py`

- [ ] **Step 1: Lage services.yaml**

```yaml
set_safety_buffer:
  name: Sett sikkerhetsmargin
  description: Endre safety_buffer_kw runtime uten reload.
  fields:
    kw:
      name: kW
      description: Ny safety_buffer-verdi i kW
      required: true
      selector:
        number:
          min: 0.1
          max: 5
          step: 0.1
          mode: slider

reset_topp_3:
  name: Nullstill topp-3-buffer
  description: Tøm daily_max-historikken for inneværende måned. Debug-hjelp.
```

- [ ] **Step 2: Test for service-registrering**

```python
"""Tester for __init__.py setup/unload."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.effektvakt import async_setup_entry, async_unload_entry
from tests.conftest import make_entry


@pytest.mark.asyncio
async def test_async_setup_entry_oppretter_coordinator():
    entry = make_entry()
    hass = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.async_add_executor_job = AsyncMock()

    with (
        patch("custom_components.effektvakt.EffektvaktCoordinator") as MockCoord,
        patch("custom_components.effektvakt.async_track_time_interval"),
    ):
        MockCoord.return_value.async_config_entry_first_refresh = AsyncMock()
        ok = await async_setup_entry(hass, entry)
    assert ok is True
    MockCoord.assert_called_once_with(hass, entry)


@pytest.mark.asyncio
async def test_async_unload_entry():
    entry = make_entry()
    entry.runtime_data = MagicMock()
    hass = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    ok = await async_unload_entry(hass, entry)
    assert ok is True
```

- [ ] **Step 3: Kjør, forvent FAIL**

Run: `pytest tests/test_init.py -v`
Expected: ImportError.

- [ ] **Step 4: Implementere __init__.py**

```python
"""Effektvakt integration for Home Assistant."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.helpers.event import async_track_time_interval

from .const import CONF_SAFETY_BUFFER_KW, DOMAIN, WATCHDOG_INTERVAL_SECONDS
from .coordinator import EffektvaktCoordinator, is_coordinator_stale, dt_util_now

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Sett opp Effektvakt fra en config entry."""
    coordinator = EffektvaktCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    async def _watchdog_check(_now) -> None:
        if is_coordinator_stale(
            last_successful_update=coordinator._last_successful_update,
            now=dt_util_now(),
        ):
            _LOGGER.warning(
                "Effektvakt coordinator stale, setter sensorer til unknown"
            )
            coordinator.async_set_updated_data({})  # signal at data er ugyldig

    entry.async_on_unload(
        async_track_time_interval(
            hass, _watchdog_check, timedelta(seconds=WATCHDOG_INTERVAL_SECONDS)
        )
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _set_safety_buffer(call) -> None:
        kw = float(call.data["kw"])
        coordinator.safety_buffer_kw = kw
        await coordinator.async_request_refresh()

    async def _reset_topp_3(call) -> None:
        coordinator._daily_max_kw = {}
        await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, "set_safety_buffer", _set_safety_buffer)
    hass.services.async_register(DOMAIN, "reset_topp_3", _reset_topp_3)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload integration når options endrer seg."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Avregistrer platforms."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
```

- [ ] **Step 5: Installere pytest-asyncio som dev-dep**

```bash
pip install pytest-asyncio
```

Legg til i `pyproject.toml` under `dev`:
```toml
"pytest-asyncio>=0.23.0",
```

Også: legg til i `[tool.pytest.ini_options]`:
```toml
asyncio_mode = "auto"
```

- [ ] **Step 6: Kjør, forvent PASS**

Run: `pytest tests/test_init.py -v`
Expected: 2 PASS.

- [ ] **Step 7: Commit**

```bash
git add custom_components/effektvakt/__init__.py custom_components/effektvakt/services.yaml tests/test_init.py pyproject.toml
git commit -m "feat: __init__.py med setup/unload, watchdog, services"
```

---

### Task 20: diagnostics.py

**Files:**
- Create: `custom_components/effektvakt/diagnostics.py`

- [ ] **Step 1: Skrive diagnostics.py**

```python
"""Diagnostics support for Effektvakt."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Returner diagnose-info for support-issues."""
    coordinator = entry.runtime_data
    return {
        "config": dict(entry.data),
        "coordinator": {
            "data": coordinator.data,
            "daily_max_kw_count": len(coordinator._daily_max_kw),
            "previous_month_top_3_snitt_kw": coordinator._previous_month_top_3_snitt_kw,
            "hysterese_state": {
                "nivå": coordinator._hysterese_state.nivå,
                "pending_nivå": coordinator._hysterese_state.pending_nivå,
            },
            "kapasitetstrinn": coordinator.kapasitetstrinn,
        },
    }
```

- [ ] **Step 2: Verifiser kompilering**

Run: `python -m py_compile custom_components/effektvakt/diagnostics.py && echo OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/effektvakt/diagnostics.py
git commit -m "feat(diagnostics): config entry diagnostics-eksport"
```

---

## Phase 6: Blueprints

### Task 21: docs/blueprints/enkel_last_shed.yaml

**Files:**
- Create: `docs/blueprints/enkel_last_shed.yaml`

- [ ] **Step 1: Skrive blueprint**

```yaml
blueprint:
  name: Effektvakt - Enkel last-shed
  description: >
    Slå av én switch når Effektvakt signaliserer kutt anbefalt.
    Slår på igjen automatisk når risikoen er borte, eller etter max_off_minutes
    som failsafe mot at coordinator henger.
  domain: automation
  source_url: https://github.com/fredrik-lindseth/hacs-effektvakt/raw/main/docs/blueprints/enkel_last_shed.yaml
  input:
    binary_sensor_entity:
      name: Effektvakt binary sensor
      description: Vanligvis binary_sensor.effektvakt_kutt_ned_anbefalt
      default: binary_sensor.effektvakt_kutt_ned_anbefalt
      selector:
        entity:
          domain: binary_sensor
    switch_entity:
      name: Switch å slå av (typisk VVB, billader)
      selector:
        entity:
          domain: switch
    max_off_minutes:
      name: Maks minutter slått av før tving-on (failsafe)
      description: Hvis Effektvakt henger, slås switchen på etter denne tiden.
      default: 30
      selector:
        number:
          min: 5
          max: 240
          step: 5

variables:
  switch_entity: !input switch_entity
  binary_sensor_entity: !input binary_sensor_entity
  max_off_minutes: !input max_off_minutes

trigger:
  - platform: state
    entity_id: !input binary_sensor_entity
    to: "on"
    id: trigger_off
  - platform: state
    entity_id: !input binary_sensor_entity
    to: "off"
    id: trigger_on

mode: restart

action:
  - choose:
      - conditions:
          - condition: trigger
            id: trigger_off
        sequence:
          - service: switch.turn_off
            target:
              entity_id: "{{ switch_entity }}"
          - delay:
              minutes: "{{ max_off_minutes }}"
          - service: switch.turn_on
            target:
              entity_id: "{{ switch_entity }}"
      - conditions:
          - condition: trigger
            id: trigger_on
        sequence:
          - service: switch.turn_on
            target:
              entity_id: "{{ switch_entity }}"
```

- [ ] **Step 2: YAML-validitets-sjekk**

Run: `python -c "import yaml; yaml.safe_load(open('docs/blueprints/enkel_last_shed.yaml')); print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add docs/blueprints/enkel_last_shed.yaml
git commit -m "feat(blueprint): enkel last-shed med failsafe"
```

---

### Task 22: docs/blueprints/prioritert_last_shed.yaml

**Files:**
- Create: `docs/blueprints/prioritert_last_shed.yaml`

- [ ] **Step 1: Skrive blueprint**

```yaml
blueprint:
  name: Effektvakt - Prioritert last-shed
  description: >
    Slå av switches i prioritert rekkefølge basert på risiko-nivå.
    medium risiko -> første switch av. high risiko -> alle switches av.
    Slår på igjen i revers rekkefølge når risiko synker.
  domain: automation
  source_url: https://github.com/fredrik-lindseth/hacs-effektvakt/raw/main/docs/blueprints/prioritert_last_shed.yaml
  input:
    risiko_sensor:
      name: Risiko-sensor
      default: sensor.effektvakt_risiko_niva
      selector:
        entity:
          domain: sensor
    switch_high_priority:
      name: Første switch som slås av (medium risiko)
      selector:
        entity:
          domain: switch
    switch_medium_priority:
      name: Andre switch som slås av (high risiko)
      selector:
        entity:
          domain: switch
    max_off_minutes:
      name: Maks minutter slått av før tving-on
      default: 30
      selector:
        number:
          min: 5
          max: 240
          step: 5

variables:
  switch_high: !input switch_high_priority
  switch_medium: !input switch_medium_priority
  max_off_minutes: !input max_off_minutes

trigger:
  - platform: state
    entity_id: !input risiko_sensor

mode: restart

action:
  - choose:
      - conditions:
          - condition: state
            entity_id: !input risiko_sensor
            state: "high"
        sequence:
          - service: switch.turn_off
            target:
              entity_id:
                - "{{ switch_high }}"
                - "{{ switch_medium }}"
          - delay:
              minutes: "{{ max_off_minutes }}"
          - service: switch.turn_on
            target:
              entity_id:
                - "{{ switch_high }}"
                - "{{ switch_medium }}"
      - conditions:
          - condition: state
            entity_id: !input risiko_sensor
            state: "medium"
        sequence:
          - service: switch.turn_off
            target:
              entity_id: "{{ switch_high }}"
          - service: switch.turn_on
            target:
              entity_id: "{{ switch_medium }}"
          - delay:
              minutes: "{{ max_off_minutes }}"
          - service: switch.turn_on
            target:
              entity_id: "{{ switch_high }}"
    default:
      - service: switch.turn_on
        target:
          entity_id:
            - "{{ switch_high }}"
            - "{{ switch_medium }}"
```

- [ ] **Step 2: YAML-sjekk**

Run: `python -c "import yaml; yaml.safe_load(open('docs/blueprints/prioritert_last_shed.yaml')); print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add docs/blueprints/prioritert_last_shed.yaml
git commit -m "feat(blueprint): prioritert last-shed på 2 switches"
```

---

### Task 23: docs/blueprints/climate_min_temp.yaml

**Files:**
- Create: `docs/blueprints/climate_min_temp.yaml`

- [ ] **Step 1: Skrive blueprint**

```yaml
blueprint:
  name: Effektvakt - Climate med min-temp
  description: >
    Sett climate-entitet (panelovn) til min-temp ved kutt anbefalt, og
    restore til lagret verdi når risiko er borte. Bruker en input_number-hjelper
    for å persistere temperatur over HA-restart.
    Failsafe: etter max_off_minutes restoreres temperatur uavhengig av sensor.
  domain: automation
  source_url: https://github.com/fredrik-lindseth/hacs-effektvakt/raw/main/docs/blueprints/climate_min_temp.yaml
  input:
    binary_sensor_entity:
      name: Effektvakt binary sensor
      default: binary_sensor.effektvakt_kutt_ned_anbefalt
      selector:
        entity:
          domain: binary_sensor
    climate_entity:
      name: Climate-entitet (panelovn)
      selector:
        entity:
          domain: climate
    min_temp:
      name: Min-temperatur ved kutt
      default: 10
      selector:
        number:
          min: 5
          max: 18
          unit_of_measurement: °C
    restore_helper:
      name: input_number for å lagre forrige temperatur
      description: Opprett en input_number med min=5, max=30, step=0.5, og pek hit.
      selector:
        entity:
          domain: input_number
    max_off_minutes:
      name: Maks minutter med min-temp før tving-restore
      default: 30
      selector:
        number:
          min: 5
          max: 240
          step: 5

variables:
  climate_entity: !input climate_entity
  restore_helper: !input restore_helper
  min_temp: !input min_temp
  max_off_minutes: !input max_off_minutes

trigger:
  - platform: state
    entity_id: !input binary_sensor_entity
    to: "on"
    id: shed
  - platform: state
    entity_id: !input binary_sensor_entity
    to: "off"
    id: restore
  - platform: homeassistant
    event: start
    id: ha_start

mode: restart

action:
  - choose:
      - conditions:
          - condition: trigger
            id: shed
        sequence:
          - service: input_number.set_value
            target:
              entity_id: "{{ restore_helper }}"
            data:
              value: "{{ state_attr(climate_entity, 'temperature') | float(20) }}"
          - service: climate.set_temperature
            target:
              entity_id: "{{ climate_entity }}"
            data:
              temperature: "{{ min_temp }}"
          - delay:
              minutes: "{{ max_off_minutes }}"
          - service: climate.set_temperature
            target:
              entity_id: "{{ climate_entity }}"
            data:
              temperature: "{{ states(restore_helper) | float(20) }}"
      - conditions:
          - condition: trigger
            id: restore
        sequence:
          - service: climate.set_temperature
            target:
              entity_id: "{{ climate_entity }}"
            data:
              temperature: "{{ states(restore_helper) | float(20) }}"
      - conditions:
          - condition: trigger
            id: ha_start
        sequence:
          - service: climate.set_temperature
            target:
              entity_id: "{{ climate_entity }}"
            data:
              temperature: "{{ states(restore_helper) | float(20) }}"
```

- [ ] **Step 2: YAML-sjekk**

Run: `python -c "import yaml; yaml.safe_load(open('docs/blueprints/climate_min_temp.yaml')); print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add docs/blueprints/climate_min_temp.yaml
git commit -m "feat(blueprint): climate med min-temp og restore-via-helper"
```

---

### Task 24: docs/blueprints/kun_varsel.yaml

**Files:**
- Create: `docs/blueprints/kun_varsel.yaml`

- [ ] **Step 1: Skrive blueprint**

```yaml
blueprint:
  name: Effektvakt - Kun varsel
  description: >
    Send notifikasjon når risiko går til medium eller high. Ingen styring.
    For brukere som vil ta beslutningen selv basert på en push.
  domain: automation
  source_url: https://github.com/fredrik-lindseth/hacs-effektvakt/raw/main/docs/blueprints/kun_varsel.yaml
  input:
    risiko_sensor:
      name: Risiko-sensor
      default: sensor.effektvakt_risiko_niva
      selector:
        entity:
          domain: sensor
    notify_service:
      name: Notify-tjeneste (uten notify.-prefiks)
      description: For eksempel mobile_app_iphone
      default: notify
      selector:
        text:
    dashboard_url:
      name: URL til Lovelace-dashboardet ditt
      default: ""
      selector:
        text:

trigger:
  - platform: state
    entity_id: !input risiko_sensor
    to: medium
    id: medium
  - platform: state
    entity_id: !input risiko_sensor
    to: high
    id: high

mode: queued

action:
  - service: "notify.{{ notify_service }}"
    data:
      title: "Effektvakt: {{ trigger.id | upper }} risiko"
      message: >
        Projisert time-snitt: {{ states('sensor.effektvakt_projisert_time_snitt') }} kW.
        Margin: {{ states('sensor.effektvakt_margin_til_neste_trinn') }} kW.
      data:
        url: "{{ dashboard_url }}"
```

- [ ] **Step 2: YAML-sjekk**

Run: `python -c "import yaml; yaml.safe_load(open('docs/blueprints/kun_varsel.yaml')); print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add docs/blueprints/kun_varsel.yaml
git commit -m "feat(blueprint): kun varsel (uten styring)"
```

---

### Task 25: test_blueprint_yaml_valid.py

**Files:**
- Create: `tests/test_blueprint_yaml_valid.py`

- [ ] **Step 1: Skrive testen**

```python
"""Verifiser at alle blueprints er gyldig YAML og har nødvendige felt."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

BLUEPRINTS_DIR = Path(__file__).parent.parent / "docs" / "blueprints"


@pytest.mark.parametrize("blueprint_path", sorted(BLUEPRINTS_DIR.glob("*.yaml")))
def test_blueprint_is_valid_yaml(blueprint_path: Path):
    """YAML-en må parse uten feil."""
    data = yaml.safe_load(blueprint_path.read_text())
    assert isinstance(data, dict)
    assert "blueprint" in data
    bp = data["blueprint"]
    assert "name" in bp
    assert "description" in bp
    assert "domain" in bp
    assert "input" in bp


@pytest.mark.parametrize("blueprint_path", sorted(BLUEPRINTS_DIR.glob("*.yaml")))
def test_shed_blueprints_har_max_off_minutes(blueprint_path: Path):
    """Shed-blueprints (alle unntatt kun_varsel) må ha max_off_minutes."""
    if "kun_varsel" in blueprint_path.name:
        pytest.skip("kun_varsel trenger ikke max_off_minutes")
    data = yaml.safe_load(blueprint_path.read_text())
    inputs = data["blueprint"]["input"]
    assert "max_off_minutes" in inputs, (
        f"{blueprint_path.name} mangler max_off_minutes failsafe-input"
    )


def test_finnes_minst_4_blueprints():
    paths = list(BLUEPRINTS_DIR.glob("*.yaml"))
    assert len(paths) >= 4


def test_blueprint_filnavn_matcher_konvensjon():
    """Alle blueprints skal ha snake_case-navn."""
    for path in BLUEPRINTS_DIR.glob("*.yaml"):
        name = path.stem
        assert name.islower(), f"{name} må være lowercase"
        assert " " not in name
```

- [ ] **Step 2: Installere pyyaml (hvis ikke allerede)**

```bash
pip install pyyaml
```

Legg til i pyproject.toml under dev:
```toml
"pyyaml>=6.0",
```

- [ ] **Step 3: Kjør testen**

Run: `pytest tests/test_blueprint_yaml_valid.py -v`
Expected: alle PASS (4 blueprints × 2 parametriserte + 2 = ~10 tester).

- [ ] **Step 4: Commit**

```bash
git add tests/test_blueprint_yaml_valid.py pyproject.toml
git commit -m "test(blueprints): YAML-validitet og max_off_minutes-krav"
```

---

## Phase 7: Replay-test mot fixturer

### Task 26: Symlink fixturer og lage minimal replay-test

**Files:**
- Create: `tests/fixtures` (symlink)
- Create: `tests/test_coordinator_replay.py`

- [ ] **Step 1: Lage symlink**

```bash
cd tests
ln -s ../../hacs-strømkalkulator/tests/fixtures fixtures
ls -la fixtures/
```

Expected: symlink-listing som viser BKK-fixtur-filene.

- [ ] **Step 2: Lage replay-helpers**

```python
"""Replay-test mot strømkalkulator-fixturer (NVE-modell: én topp-time per dag)."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from custom_components.effektvakt.coordinator import (
    compute_effective_threshold,
    lookup_tiers,
    top_n_average,
)
from custom_components.effektvakt.dso import KAPASITETSTRINN_PER_DSO


FIXTURES_DIR = Path(__file__).parent / "fixtures"
BKK_FIXTURES = sorted(FIXTURES_DIR.glob("bkk_*_hourly.json"))


def _load_fixture(path: Path) -> list[dict]:
    payload = json.loads(path.read_text())
    return payload["hours"]


def _aggregate_daily_max(hours: list[dict]) -> dict[date, float]:
    """Rå daily_max (uten styring). NVE-modellen: én topp-time per dag."""
    daily: dict[date, float] = {}
    for h in hours:
        dt = datetime.fromisoformat(h["start_local"])
        d = dt.date()
        kwh = float(h["kwh"])
        if kwh > daily.get(d, 0.0):
            daily[d] = kwh
    return daily


def _simulate_with_shed(hours: list[dict], trinn: list[tuple[float, int]]) -> dict[date, float]:
    """Anta Effektvakt fikk styre. Reduserer kwh med 0.5 i timer hvor risiko ville vært ≥ medium."""
    daily_max_so_far: dict[date, float] = {}
    daily_result: dict[date, float] = {}
    safety_buffer_kw = 1.0

    for h in hours:
        dt = datetime.fromisoformat(h["start_local"])
        d = dt.date()
        kwh = float(h["kwh"])

        # Vurder om timen ville krysset effective_threshold ved time-slutt
        tiers = lookup_tiers(projected_kw=kwh, trinn=trinn)
        if tiers.next_threshold_kw is None:
            adjusted = kwh
        else:
            effective_threshold = compute_effective_threshold(
                next_tier_threshold_kw=tiers.next_threshold_kw,
                daily_max_kw=daily_max_so_far,
            )
            margin = effective_threshold - kwh
            # risiko ≥ medium = margin <= safety_buffer
            would_shed = margin <= safety_buffer_kw
            adjusted = kwh - 0.5 if would_shed else kwh

        if adjusted > daily_result.get(d, 0.0):
            daily_result[d] = adjusted
        if kwh > daily_max_so_far.get(d, 0.0):
            daily_max_so_far[d] = kwh

    return daily_result


def _trinn_idx_for_kw(kw: float, trinn: list[tuple[float, int]]) -> int:
    """Returner index av første trinn hvor kw <= terskel. -1 hvis over alle."""
    for i, (t, _) in enumerate(trinn):
        if kw <= t:
            return i
    return -1
```

- [ ] **Step 3: Test for besparelse-assertion**

Legg til etter helpers i samme fil:

```python
@pytest.mark.skipif(
    not FIXTURES_DIR.exists() or not BKK_FIXTURES,
    reason="strømkalkulator-fixturer ikke tilgjengelig",
)
def test_replay_skadebegrensning_over_5_måneder():
    """Post-styring topp-3-snitt ≥ 0.3 kW lavere i ≥ 4 av 5 måneder."""
    trinn = KAPASITETSTRINN_PER_DSO["bkk"]["kapasitetstrinn"]

    forbedringer = []
    for path in BKK_FIXTURES:
        hours = _load_fixture(path)
        rå_daily = _aggregate_daily_max(hours)
        post_daily = _simulate_with_shed(hours, trinn)

        rå_topp_3 = top_n_average(rå_daily, n=3) or 0.0
        post_topp_3 = top_n_average(post_daily, n=3) or 0.0
        forbedringer.append((path.stem, rå_topp_3 - post_topp_3))

    print("\nMåned-for-måned forbedring:")
    for navn, forbedring in forbedringer:
        print(f"  {navn}: {forbedring:+.3f} kW")

    over_0_3 = sum(1 for _, f in forbedringer if f >= 0.3)
    assert over_0_3 >= 4, (
        f"Forventet ≥ 4 av {len(forbedringer)} måneder med ≥ 0.3 kW forbedring, fikk {over_0_3}"
    )


@pytest.mark.skipif(
    not FIXTURES_DIR.exists() or not BKK_FIXTURES,
    reason="strømkalkulator-fixturer ikke tilgjengelig",
)
def test_replay_ingen_false_positives_lavt_forbruk():
    """Effektvakt skal ikke forsøke kutt i timer langt under tier-grensa."""
    trinn = KAPASITETSTRINN_PER_DSO["bkk"]["kapasitetstrinn"]

    for path in BKK_FIXTURES:
        hours = _load_fixture(path)
        daily_max_so_far: dict[date, float] = {}

        for h in hours:
            dt = datetime.fromisoformat(h["start_local"])
            d = dt.date()
            kwh = float(h["kwh"])
            if kwh > 1.5:
                # Skip - bare se på lav-forbruk-timer
                if kwh > daily_max_so_far.get(d, 0.0):
                    daily_max_so_far[d] = kwh
                continue

            tiers = lookup_tiers(projected_kw=kwh, trinn=trinn)
            if tiers.next_threshold_kw is None:
                continue
            effective_threshold = compute_effective_threshold(
                next_tier_threshold_kw=tiers.next_threshold_kw,
                daily_max_kw=daily_max_so_far,
            )
            margin = effective_threshold - kwh
            assert margin > 1.0, (
                f"{path.stem} {dt}: lav forbruks-time {kwh:.2f} kWh "
                f"gir margin {margin:.2f} (forventet > 1.0)"
            )

            if kwh > daily_max_so_far.get(d, 0.0):
                daily_max_so_far[d] = kwh
```

- [ ] **Step 4: Kjør replay-testen**

Run: `pytest tests/test_coordinator_replay.py -v -s`
Expected: PASS hvis fixturene er tilgjengelig. Se output med måned-for-måned-forbedring.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures tests/test_coordinator_replay.py
git commit -m "test(replay): kontrafaktisk besparelse-test mot BKK-fixturer"
```

---

## Phase 8: README, dashboard og CI

### Task 27: README.md med blueprint-import-knapper

**Files:**
- Create: `README.md`
- Create: `CHANGELOG.md`

- [ ] **Step 1: README.md**

```markdown
# Effektvakt

Prediktiv kapasitetstrinn-styring for norske strømkunder i Home Assistant. Effektvakt forutsier om du er på vei mot å krysse neste kapasitetstrinn i nettleien og signaliserer kutt-anbefalinger gjennom sensorer du kobler til dine egne switches via medfølgende blueprints.

## Hvordan det virker

Norske nettselskap fakturerer kapasitetsledd etter snittet av topp-3 maks-timer fra ulike dager i måneden (NVE-modellen). Krysser du neste trinn én eneste time, betaler du for det trinnet resten av måneden. Effektvakt leser power- og energy-sensoren din, projiserer time-snittet, og varsler når en handling kan forhindre trinn-overskridelse.

## Installasjon

1. Installer via HACS (legg til som custom repository hvis ikke i default-listen).
2. Konfigurer integrasjonen: velg DSO, power-sensor, energy-sensor og innstillinger.
3. Importer en av blueprints nedenfor for å koble på styring.

## Sensorer

| Sensor | Hva |
|---|---|
| `sensor.effektvakt_projisert_time_snitt` | Forventet time-snitt i kW ved time-slutt |
| `sensor.effektvakt_margin_til_neste_trinn` | Hvor mange kW under neste trinn (etter topp-3-vurdering) |
| `sensor.effektvakt_topp_3_snitt_denne_maned` | Snitt av topp-3 maks-timer fra ulike dager |
| `sensor.effektvakt_risiko_niva` | none / low / medium / high (hysteresefull) |
| `binary_sensor.effektvakt_kutt_ned_anbefalt` | on når kutt anbefales |

## Blueprints

Klikk for å importere blueprint direkte til ditt Home Assistant:

- [Enkel last-shed](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Ffredrik-lindseth%2Fhacs-effektvakt%2Fraw%2Fmain%2Fdocs%2Fblueprints%2Fenkel_last_shed.yaml): én switch av/på basert på risiko
- [Prioritert last-shed](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Ffredrik-lindseth%2Fhacs-effektvakt%2Fraw%2Fmain%2Fdocs%2Fblueprints%2Fprioritert_last_shed.yaml): flere switches i rekkefølge
- [Climate med min-temp](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Ffredrik-lindseth%2Fhacs-effektvakt%2Fraw%2Fmain%2Fdocs%2Fblueprints%2Fclimate_min_temp.yaml): panelovner med restore-helper
- [Kun varsel](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Ffredrik-lindseth%2Fhacs-effektvakt%2Fraw%2Fmain%2Fdocs%2Fblueprints%2Fkun_varsel.yaml): push-notifikasjon, ingen styring

## Dashboard-eksempel

Se [docs/dashboard-eksempel.yaml](docs/dashboard-eksempel.yaml) for en kopierbar Lovelace-konfigurasjon.

## Failsafe

Alle shed-blueprints har en `max_off_minutes`-input som tvinger lasten på igjen etter en tidsfrist, uavhengig av Effektvakts tilstand. Effektvakts coordinator har egen watchdog som setter sensorer til `unknown` hvis ingen oppdatering har skjedd på 2 minutter. Designet skal aldri etterlate VVB-en din av forever.

## Lisens

MIT. Se LICENSE.
```

- [ ] **Step 2: CHANGELOG.md**

```markdown
# Endringslogg

Følger [Keep a Changelog](https://keepachangelog.com/) og [SemVer](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-05-25

### Lagt til

- Initial release.
- Coordinator med NVE-modell (topp-3 dager), effective_threshold, adaptiv tick.
- 4 sensorer + 1 binary_sensor.
- 4 blueprints (enkel, prioritert, climate, kun varsel) med max_off_minutes-failsafe.
- Watchdog uavhengig av coordinator.
- DSO-sync-script mot strømkalkulator.
- Replay-test mot BKK-fixturer.
```

- [ ] **Step 3: Commit**

```bash
git add README.md CHANGELOG.md
git commit -m "docs: README med blueprint-import-knapper, CHANGELOG 0.1.0"
```

---

### Task 28: docs/dashboard-eksempel.yaml

**Files:**
- Create: `docs/dashboard-eksempel.yaml`

- [ ] **Step 1: Skrive dashboard-yaml**

```yaml
# Lim inn som en ny view i Lovelace eller bruk som ny dashboard.
title: Effektvakt
views:
  - title: Oversikt
    cards:
      - type: gauge
        entity: sensor.effektvakt_margin_til_neste_trinn
        name: Margin til neste trinn
        min: -2
        max: 5
        severity:
          green: 2
          yellow: 1
          red: 0
        needle: true

      - type: entities
        title: Effektvakt sensorer
        entities:
          - entity: sensor.effektvakt_risiko_niva
            name: Risiko-nivå
          - entity: sensor.effektvakt_projisert_time_snitt
            name: Projisert time-snitt
          - entity: sensor.effektvakt_topp_3_snitt_denne_maned
            name: Topp-3 hittil i måned
          - entity: binary_sensor.effektvakt_kutt_ned_anbefalt
            name: Kutt anbefalt

      - type: history-graph
        title: Risiko siste 24t
        entities:
          - sensor.effektvakt_risiko_niva
        hours_to_show: 24

      - type: history-graph
        title: Margin siste 24t
        entities:
          - sensor.effektvakt_margin_til_neste_trinn
        hours_to_show: 24
```

- [ ] **Step 2: YAML-sjekk**

Run: `python -c "import yaml; yaml.safe_load(open('docs/dashboard-eksempel.yaml')); print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add docs/dashboard-eksempel.yaml
git commit -m "docs: Lovelace dashboard-eksempel"
```

---

### Task 29: CI-workflow

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/validate.yml`

- [ ] **Step 1: ci.yml**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout effektvakt
        uses: actions/checkout@v6

      - name: Checkout strømkalkulator for DSO-sync
        uses: actions/checkout@v6
        with:
          repository: fredrik-lindseth/hacs-strømkalkulator
          path: ../hacs-strømkalkulator

      - name: Set up Python
        uses: actions/setup-python@v6
        with:
          python-version: '3.12'

      - name: Install deps
        run: pip install -e ".[dev]" pyyaml pytest-asyncio

      - name: Lint (ruff)
        run: ruff check custom_components/effektvakt/ tests/ scripts/

      - name: Type check (mypy, warnings only)
        run: mypy custom_components/effektvakt/ --ignore-missing-imports || true

      - name: Verify DSO sync
        run: python scripts/sync_dso_from_stromkalkulator.py --check

      - name: Tests with coverage
        run: pytest tests/ -v --cov=custom_components/effektvakt --cov-report=term-missing

      - name: Manifest valid JSON
        run: jq empty custom_components/effektvakt/manifest.json

      - name: Required files present
        run: |
          for f in \
            custom_components/effektvakt/__init__.py \
            custom_components/effektvakt/manifest.json \
            custom_components/effektvakt/config_flow.py \
            custom_components/effektvakt/coordinator.py \
            custom_components/effektvakt/sensor.py \
            custom_components/effektvakt/binary_sensor.py \
            custom_components/effektvakt/const.py \
            custom_components/effektvakt/dso.py \
            README.md \
            CHANGELOG.md \
            LICENSE; do
            [ -f "$f" ] || { echo "Missing: $f"; exit 1; }
          done

      - name: Version-format manifest
        run: |
          VERSION=$(jq -r '.version' custom_components/effektvakt/manifest.json)
          [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Bad version: $VERSION"; exit 1; }
```

- [ ] **Step 2: validate.yml (hassfest + hacs)**

```yaml
name: Validate

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 4 * * 1'

jobs:
  hacs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: hacs/action@main
        with:
          category: integration

  hassfest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: home-assistant/actions/hassfest@master
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/
git commit -m "ci: pytest, ruff, DSO-sync-sjekk, hassfest, HACS-validering"
```

---

## Phase 9: Sluttsjekk og release

### Task 30: Kjør full test-suite og pre-commit

**Files:**
- Ingen nye filer

- [ ] **Step 1: Installer pre-commit hooks**

```bash
pre-commit install
pre-commit install --hook-type pre-push
```

- [ ] **Step 2: Kjør pre-commit på alt**

```bash
pre-commit run --all-files
```

Expected: alle hooks PASS (eller auto-fixed).

- [ ] **Step 3: Full test-suite**

```bash
pytest tests/ -v --cov=custom_components/effektvakt
```

Expected: alle tester PASS. Coverage rapport viser ≥ 80% på coordinator.

- [ ] **Step 4: Verifiser sync_dso --check**

```bash
python scripts/sync_dso_from_stromkalkulator.py --check
```

Expected: `OK: dso.py er i sync.`

- [ ] **Step 5: Vulture-sjekk**

```bash
vulture custom_components/effektvakt/ vulture_whitelist.py --min-confidence 80
```

Expected: ingen unused symbols (eller bare false positives som whitelistes).

- [ ] **Step 6: Lage v0.1.0 git-tag**

```bash
git tag -a v0.1.0 -m "Initial release: prediktiv kapasitetstrinn-styring"
git tag --list
```

- [ ] **Step 7: Final commit hvis det er endringer fra pre-commit**

```bash
git status
# Hvis endringer:
git add -A
git commit -m "chore: pre-commit fix-ups"
```

---

## Self-Review checklist

Etter at planen er skrevet, sjekk:

**Spec coverage:**
- ✅ Topp-3-dager (NVE-modell): Task 9, 12, 13
- ✅ Effective_threshold med fallback: Task 9
- ✅ Hysterese (oppgang umiddelbar, multi-step nedgang): Task 11
- ✅ Adaptiv tick (60/30/15s): Task 13
- ✅ Watchdog uavhengig av coordinator: Task 14, 19
- ✅ DSO-sync-script + CI-check: Task 4, 29
- ✅ Power-sensor unit-validering: Task 7
- ✅ Peak-sensor-heuristikk: Task 18
- ✅ Persistering (daily_max + arkiv): Task 13
- ✅ 4 blueprints med max_off_minutes (unntatt kun_varsel): Task 21-24
- ✅ Replay-test variant A: Task 26
- ✅ DST-håndtering via (hour, utcoffset)-bucket: Task 13
- ⚠️ Replay variant B (syntetisk minutt-replay): utelatt, kan legges til senere som ekstra-task
- ✅ Sensor-katalog: 4 + 1 binary: Task 15, 16
- ✅ Options-flow: Task 18

**Placeholder scan:** Ingen TBD, TODO, "implement later", "similar to Task N".

**Type-consistency:** `EffektvaktCoordinator`, `HystereseState`, `TierInfo`, `compute_*`, `read_*`, `lookup_tiers`, `apply_hysteresis`, `classify_raw_risk` brukes konsekvent.

**Mangler:**
- Replay variant B (syntetisk minutt-replay) er ikke i planen. Bevisst utelatt: variant A dekker hovedformålet. Hvis brukeren vil ha B senere, legges som egen task.
