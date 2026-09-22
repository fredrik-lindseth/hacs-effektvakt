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
#   ha-minimum        tests_ha/ mot ekte HA 2025.1.0 (Python 3.13)
#   ha-current        tests_ha/ mot ekte HA 2026.9.2 (Python 3.14)
#
# Gruppene står i pyproject.toml og er låst i uv.lock. tests/ og tests_ha/ kan
# ikke dele miljø: tests/conftest.py stubber homeassistant.* i sys.modules, og
# en ekte homeassistant ved siden av ville kollidert med stubbene.

set shell := ["bash", "-uc"]

# Coverage-flaggene lokalt og i CI er de samme.
cov_args := "--cov=custom_components/effektvakt --cov-report=term-missing"

default:
    @just --list

# Unit- og replay-testene. Ekstra argumenter sendes videre til pytest.
test-unit *args:
    UV_PROJECT_ENVIRONMENT=.venv-unit uv run --frozen --python 3.13 --group unit pytest tests/ {{args}}

# tests_ha/ mot en ekte Home Assistant. target=minimum er versjonen hacs.json
# lover brukerne, target=current den nyeste vi har sett på. Begge skal være
# grønne: feller minimum, er det enten en kompatibilitetsfeil å rette eller et
# minimum å heve med vilje, aldri noe å hoppe over.
#
# Testene som er markert xfail der er ekte feil i integrasjonen, ikke i
# testene, og markørene er strict. Se kommentarene i tests_ha/test_frontend.py
# og tests_ha/test_config_flow.py.
#
# Ekte HA-tester, target=minimum eller current.
test-ha target="current" *args:
    #!/usr/bin/env bash
    set -euo pipefail
    # `just test-ha target=minimum` sender hele strengen som posisjonsargument,
    # så prefikset strippes framfor å avvise skrivemåten docs bruker.
    target="{{target}}"; target="${target#target=}"
    case "$target" in
        minimum) python=3.13 ;;
        current) python=3.14 ;;
        *) echo "Ukjent target '$target'. Bruk minimum eller current." >&2; exit 2 ;;
    esac
    # asyncio_mode står i pyproject, men fixture-loopens scope gjør det ikke,
    # og uten den advarer pytest-asyncio på hver kjøring.
    UV_PROJECT_ENVIRONMENT=".venv-ha-$target" uv run --frozen --python "$python" \
        --group "ha-$target" pytest tests_ha -o asyncio_default_fixture_loop_scope=function {{args}}

# Lint, formatsjekk, typer og død kode. Samme verktøyversjoner som hookene.
# mypy er blokkerende: den var rådgivende med `|| true` fram til september
# 2026, og de 26 feilene den samlet opp var nettopp det en rådgivende port
# koster. Legger du igjen en typefeil nå, stopper den bygget.
#
# Lint, formatsjekk, typer og død kode. Blokkerende, alle fire.
check:
    UV_PROJECT_ENVIRONMENT=.venv-kvalitet uv run --frozen --python 3.13 --group kvalitet ruff check custom_components/effektvakt/ tests/ tests_ha/ scripts/ docs/kort-harness/ vulture_whitelist.py
    UV_PROJECT_ENVIRONMENT=.venv-kvalitet uv run --frozen --python 3.13 --group kvalitet ruff format --check custom_components/effektvakt/ tests/ tests_ha/ scripts/ docs/kort-harness/ vulture_whitelist.py
    UV_PROJECT_ENVIRONMENT=.venv-kvalitet uv run --frozen --python 3.13 --group kvalitet mypy custom_components/effektvakt/ --ignore-missing-imports
    UV_PROJECT_ENVIRONMENT=.venv-kvalitet uv run --frozen --python 3.13 --group kvalitet vulture custom_components/effektvakt vulture_whitelist.py --min-confidence 80 --exclude "*test*"

# Formater. Den eneste oppskriften her som skriver til filer.
fmt:
    UV_PROJECT_ENVIRONMENT=.venv-kvalitet uv run --frozen --python 3.13 --group kvalitet ruff format custom_components/effektvakt/ tests/ tests_ha/ scripts/ docs/kort-harness/ vulture_whitelist.py
    UV_PROJECT_ENVIRONMENT=.venv-kvalitet uv run --frozen --python 3.13 --group kvalitet ruff check --fix custom_components/effektvakt/ tests/ tests_ha/ scripts/ docs/kort-harness/ vulture_whitelist.py

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
# Begge suitene måler, og bare summen av dem betyr noe: hver av dem alene
# lar kode stå udekket som den andre dekker, og ingen av dem er ment å bære
# tallet alene. Derfor combine før rapport, og derfor ingen terskel per suite.
#
# tests_ha måles bare på current. Minimum kjører nøyaktig de samme testene mot
# en eldre HA, så en måling til ville vært det samme tallet en gang til.
# ---------------------------------------------------------------------------

# Coverage for hele suiten, med terskel.
coverage: (coverage-unit "-q") (coverage-ha "-q") coverage-gate

# tests/ med coverage, inn i .coverage.unit og coverage-unit.xml.
coverage-unit *args:
    COVERAGE_FILE=.coverage.unit just test-unit {{cov_args}} --cov-report=xml:coverage-unit.xml {{args}}

# tests_ha/ på current med coverage, inn i .coverage.ha og coverage-ha.xml.
coverage-ha *args:
    COVERAGE_FILE=.coverage.ha just test-ha current {{cov_args}} --cov-report=xml:coverage-ha.xml {{args}}

# Slår sammen de to datafilene, skriver ut linjene som mangler og feller
# under terskelen. CI kjører den i en egen jobb som venter på begge suitene
# og henter datafilene som artefakter.
coverage-gate:
    UV_PROJECT_ENVIRONMENT=.venv-unit uv run --frozen --python 3.13 --group unit \
        coverage combine --data-file=.coverage .coverage.unit .coverage.ha
    UV_PROJECT_ENVIRONMENT=.venv-unit uv run --frozen --python 3.13 --group unit \
        coverage report --data-file=.coverage --show-missing --fail-under=95
