# Effektvakt: portene. Krever `just` (https://github.com/casey/just) og uv.
# På macOS: `brew install just`, og uv fra https://docs.astral.sh/uv/.
#
# Oppskriftene her er de samme kommandolinjene som pre-commit og CI kjører.
# Det finnes ikke en «annen» kommando bygget bruker: er `just check` grønn
# lokalt, er check-jobben i ci.yml grønn på den samme commiten.
#
# Miljøene, ett venv per gruppe, ingen av dem deler sys.modules:
#
#   unit + kvalitet   tests/ med stubbet Home Assistant, Python 3.13
#   ha-minimum        ekte HA 2025.1.0 (Python 3.13), tas i bruk av tests_ha/
#   ha-current        ekte HA 2026.9.2 (Python 3.14), tas i bruk av tests_ha/
#
# Gruppene står i pyproject.toml og er låst i uv.lock.

set shell := ["bash", "-uc"]

# Coverage-flaggene lokalt og i CI er de samme.
cov_args := "--cov=custom_components/effektvakt --cov-report=term-missing"

default:
    @just --list

# Unit- og replay-testene. Ekstra argumenter sendes videre til pytest.
test-unit *args:
    UV_PROJECT_ENVIRONMENT=.venv-unit uv run --frozen --python 3.13 --group unit pytest tests/ {{args}}

# Lint, formatsjekk, typer og død kode. Samme verktøyversjoner som hookene.
# mypy er blokkerende: den var rådgivende med `|| true` fram til september
# 2026, og de 26 feilene den samlet opp var nettopp det en rådgivende port
# koster. Legger du igjen en typefeil nå, stopper den bygget.
#
# Lint, formatsjekk, typer og død kode. Blokkerende, alle fire.
check:
    UV_PROJECT_ENVIRONMENT=.venv-kvalitet uv run --frozen --python 3.13 --group kvalitet ruff check custom_components/effektvakt/ tests/ scripts/ docs/kort-harness/ vulture_whitelist.py
    UV_PROJECT_ENVIRONMENT=.venv-kvalitet uv run --frozen --python 3.13 --group kvalitet ruff format --check custom_components/effektvakt/ tests/ scripts/ docs/kort-harness/ vulture_whitelist.py
    UV_PROJECT_ENVIRONMENT=.venv-kvalitet uv run --frozen --python 3.13 --group kvalitet mypy custom_components/effektvakt/ --ignore-missing-imports
    UV_PROJECT_ENVIRONMENT=.venv-kvalitet uv run --frozen --python 3.13 --group kvalitet vulture custom_components/effektvakt vulture_whitelist.py --min-confidence 80 --exclude "*test*"

# Formater. Den eneste oppskriften her som skriver til filer.
fmt:
    UV_PROJECT_ENVIRONMENT=.venv-kvalitet uv run --frozen --python 3.13 --group kvalitet ruff format custom_components/effektvakt/ tests/ scripts/ docs/kort-harness/ vulture_whitelist.py
    UV_PROJECT_ENVIRONMENT=.venv-kvalitet uv run --frozen --python 3.13 --group kvalitet ruff check --fix custom_components/effektvakt/ tests/ scripts/ docs/kort-harness/ vulture_whitelist.py

# Det AGENTS.md ber om før commit: unit + kvalitet. Krever ikke Home Assistant.
test: test-unit check

# Er dso.py fortsatt nøyaktig det generatoren ville skrevet? Uten --kilde
# lastes tariffene ned fra fri-nettleie på commiten i scripts/dso_kilder.json;
# har du en utsjekk, er `just dso-sjekk _fri-nettleie` den samme sjekken uten
# nett, og det er varianten CI kjører.
#
# Er dso.py i takt med fri-nettleie?
dso-sjekk kilde="":
    #!/usr/bin/env bash
    set -euo pipefail
    # Kjøres i unit-miljøet fordi generatoren trenger pyyaml, og system-Python
    # på en CI-runner ikke har det.
    kjor=(env UV_PROJECT_ENVIRONMENT=.venv-unit uv run --frozen --python 3.13 --group unit
          python scripts/generer_dso_fra_fri_nettleie.py --check)
    if [[ -n "{{kilde}}" ]]; then
        "${kjor[@]}" --kilde "{{kilde}}"
    else
        "${kjor[@]}"
    fi

# Hent fri-nettleie på den pinnede commiten til _fri-nettleie/, så dso-sjekk
# kan kjøres uten nett etterpå. Katalogen er i .gitignore.
#
# Hent fri-nettleie på pinnet commit til _fri-nettleie/.
dso-hent:
    #!/usr/bin/env bash
    set -euo pipefail
    commit=$(jq -r '._meta.commit' scripts/dso_kilder.json)
    rm -rf _fri-nettleie
    git clone --quiet https://github.com/kraftsystemet/fri-nettleie _fri-nettleie
    git -C _fri-nettleie checkout --quiet "$commit"
    echo "_fri-nettleie står på $commit"

# ---------------------------------------------------------------------------
# Coverage
#
# I dag er unit-suiten den eneste som måler. Når tests_ha/ finnes
# (hacs-effektvakt-1vfeemq), kommer coverage-ha ved siden av, og gaten leser
# summen av de to. Terskelen står derfor på 90 og ikke på 95: config_flow.py
# og diagnostics.py er det ekte-HA-testene dekker, og å heve tallet nå ville
# vært å be unit-suiten om å teste noe den ikke kan se.
# ---------------------------------------------------------------------------

# Coverage for hele suiten, med terskel.
coverage: (coverage-unit "-q") coverage-gate

# tests/ med coverage, inn i .coverage.unit og coverage-unit.xml.
coverage-unit *args:
    COVERAGE_FILE=.coverage.unit just test-unit {{cov_args}} --cov-report=xml:coverage-unit.xml {{args}}

# Skriver ut linjene som mangler og feller under 90 %.
coverage-gate:
    UV_PROJECT_ENVIRONMENT=.venv-unit uv run --frozen --python 3.13 --group unit \
        coverage combine --data-file=.coverage .coverage.unit
    UV_PROJECT_ENVIRONMENT=.venv-unit uv run --frozen --python 3.13 --group unit \
        coverage report --data-file=.coverage --show-missing --fail-under=90
