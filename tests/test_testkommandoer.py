"""Vokter at det bare finnes én beskrivelse av hvordan bygget kjøres.

Bakgrunnen er konkret. I september 2026 sa `AGENTS.md` samtidig at det ikke
fantes noe justfile, at miljøet settes opp med `pip install -e '.[dev]'` og at
mypy var rådgivende, mens `justfile` og `ci.yml` gjorde det motsatte av alle
tre. `docs/development.md` beskrev en CI med fire jobber som da hadde seks.
Tre agenter rettet slike pekere samme dag, og de råtnet igjen med en gang,
fordi ingenting leste filene sammen.

Denne filen leser `justfile`, `AGENTS.md`, `docs/`, `.pre-commit-config.yaml`,
`.github/workflows/ci.yml`, `pyproject.toml`, `hacs.json` og `uv.lock`, og
feller når de ikke er enige om hvilke kommandoer som finnes og hva de gjør.
Den kjører ingen av kommandoene.

Den dømmer kommandoer, ikke prosa: at `just test-ha` finnes og godtar de samme
målene som CI-matrisen, ikke at noen formulerte setningen om den annerledes.
Der en doc må nevne noe, holder det at én av dem gjør det, siden AGENTS.md og
docs/development.md deler på å forklare det samme.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]

JUSTFILE = REPO / "justfile"
AGENTS = REPO / "AGENTS.md"
DEVELOPMENT = REPO / "docs" / "development.md"
PRECOMMIT = REPO / ".pre-commit-config.yaml"
CI = REPO / ".github" / "workflows" / "ci.yml"
PYPROJECT = REPO / "pyproject.toml"
HACS = REPO / "hacs.json"
UV_LOCK = REPO / "uv.lock"

# Alt som kan vise en kommando til et menneske. `just <navn>` her må finnes i
# justfile, uansett hvilken av dem som nevner den.
DOKUMENTER = (AGENTS, REPO / "README.md", *sorted((REPO / "docs").glob("*.md")))

# De to som deler på å forklare porter, CI og miljøer. Krav om at noe skal stå
# skrevet, stilles til summen av dem.
PORTDOKUMENTER = (AGENTS, DEVELOPMENT)

# Filene som har lov til å nevne en HA-versjon i klartekst. Hver forekomst
# sjekkes mot uv.lock, så en kopi som ikke er oppdatert feller.
# docs/fysisk-panel.md står ikke her: versjonen der er esphome, ikke HA.
FILER_MED_HA_VERSJON = (JUSTFILE, AGENTS, DEVELOPMENT, PYPROJECT, HACS)

HA_VERSJON = re.compile(r"\b20\d\d\.\d+\.\d+\b")

# Oppskriftene som utgjør bygget. `fmt`, `dso-hent` og `dso-sjekk` er ikke
# porter, men docs viser til dem, og test_alle_just_kommandoer_i_docs_finnes
# dekker dem.
PORT_RECIPES = {
    "test",
    "test-unit",
    "test-ha",
    "check",
    "coverage",
    "coverage-unit",
    "coverage-ha",
    "coverage-gate",
}

HA_TARGETS = {"minimum", "current"}

# Det `just check` faktisk gjør. Vakten må se etter kommandoen, ikke etter at
# oppskriften heter «check»: ellers kunne mypy eller vulture falle ut uten at
# noe felte. Bredden står med, fordi en smalning til custom_components/ ville
# gått grønt på scripts/ og tests/.
CHECK_KOMMANDOER: tuple[tuple[str, str], ...] = (
    ("ruff check", "ruff"),
    ("ruff format --check", "format"),
    ("mypy custom_components/effektvakt/", "mypy"),
    ("vulture custom_components/effektvakt", "vulture"),
)

# Verktøyene pre-commit og kvalitet-gruppa må være enige om. Ulike versjoner er
# spriket som viser seg som «formateringen endret seg av seg selv».
PINNEDE_VERKTOY = ("ruff", "mypy", "vulture")


def _les(sti: Path) -> str:
    assert sti.is_file(), f"{sti.relative_to(REPO)} finnes ikke"
    return sti.read_text(encoding="utf-8")


def _just_recipes() -> dict[str, list[str]]:
    """Oppskriftsnavn til kroppslinjer, lest rett fra justfile.

    Parseren er med vilje enkel: en oppskrift starter i kolonne 0 på formen
    `navn [parametre]:` (ikke `:=`, som er variabeltilordning), og kroppen er
    de innrykkede linjene under.
    """
    recipes: dict[str, list[str]] = {}
    gjeldende: str | None = None
    for linje in _les(JUSTFILE).splitlines():
        if linje.startswith((" ", "\t")):
            if gjeldende:
                recipes[gjeldende].append(linje.strip())
            continue
        if not linje.strip() or linje.startswith("#"):
            continue
        treff = re.match(r"^([a-zA-Z][\w-]*)((?:\s+[^:\n]*)?):(?!=)\s*(.*)$", linje)
        if treff:
            gjeldende = treff.group(1)
            recipes.setdefault(gjeldende, [])
            # `test: test-unit check` har avhengighetene etter kolonet.
            if treff.group(3):
                recipes[gjeldende].append("# avhengigheter: " + treff.group(3))
        else:
            gjeldende = None
    return recipes


def _kodeblokker(tekst: str) -> list[str]:
    """Innholdet i ``` ```-blokkene, altså det en leser faktisk limer inn."""
    return re.findall(r"^```[^\n]*\n(.*?)^```", tekst, re.MULTILINE | re.DOTALL)


def _ci_steg_kommandoer(ci: dict) -> list[tuple[str, str, str]]:
    """(jobbnavn, stegnavn, kommando) for hvert `run:`-steg, med matrisen flatet ut.

    `just ${{ matrix.oppskrift }}` er en ekte kommando, og den skal telle med
    når vakten sjekker at CI bare kaller oppskrifter som finnes.
    """
    kommandoer: list[tuple[str, str, str]] = []
    for jobbnavn, jobb in ci["jobs"].items():
        include = jobb.get("strategy", {}).get("matrix", {}).get("include", [{}])
        for steg in jobb.get("steps", []):
            kommando = steg.get("run")
            if not kommando:
                continue
            for rad in include:
                utflatet = kommando
                for nokkel, verdi in rad.items():
                    utflatet = re.sub(
                        r"\$\{\{\s*matrix\." + re.escape(str(nokkel)) + r"\s*\}\}",
                        str(verdi),
                        utflatet,
                    )
                kommandoer.append((jobbnavn, steg.get("name", "(uten navn)"), utflatet))
    return kommandoer


def _ha_versjon_per_mal() -> dict[str, str]:
    """HA-versjonen hvert test-ha-mål faktisk kjører, slått opp i uv.lock.

    Gruppa `ha-<mål>` pinner en plugin-versjon, og det er plugin-en som drar
    inn homeassistant. Uten dette oppslaget kan hacs.json heves uten at
    `just test-ha minimum` tester noe annet enn før.
    """
    grupper = tomllib.loads(_les(PYPROJECT))["dependency-groups"]
    pakker = tomllib.loads(_les(UV_LOCK))["package"]

    per_mal: dict[str, str] = {}
    for mal in sorted(HA_TARGETS):
        (pin,) = [krav for krav in grupper[f"ha-{mal}"] if krav.startswith("pytest-homeassistant-custom-component")]
        assert "==" in pin, f"ha-{mal} pinner ikke plugin-versjonen eksakt: {pin!r}"
        versjon = pin.split("==")[1]
        (plugin,) = [
            p for p in pakker if p["name"] == "pytest-homeassistant-custom-component" and p["version"] == versjon
        ]
        (ha,) = [d for d in plugin["dependencies"] if d["name"] == "homeassistant"]
        per_mal[mal] = ha["version"]
    return per_mal


@pytest.fixture(scope="module")
def recipes() -> dict[str, list[str]]:
    return _just_recipes()


@pytest.fixture(scope="module")
def ci() -> dict:
    return yaml.safe_load(_les(CI))


def test_justfile_har_alle_portene(recipes: dict[str, list[str]]) -> None:
    mangler = PORT_RECIPES - recipes.keys()
    assert not mangler, f"justfile mangler oppskriftene {sorted(mangler)}"


def test_just_check_kjorer_alle_fire_sjekkene(recipes: dict[str, list[str]]) -> None:
    """Docs lover fire sjekker. Faller én ut, skal vakten felle det."""
    kropp = "\n".join(recipes["check"])
    for kommando, _ in CHECK_KOMMANDOER:
        assert kommando in kropp, (
            f"`just check` kjører ikke {kommando!r}. Docs lover ruff check, "
            "ruff format --check, mypy og vulture, og det er denne oppskriften som er lovet."
        )


def test_just_check_dekker_de_samme_stiene_med_ruff(recipes: dict[str, list[str]]) -> None:
    """`ruff check` og `ruff format --check` skal se på det samme treet.

    Ellers kan en katalog bli formatert av `just fmt` og aldri lintet, eller
    omvendt, og forskjellen viser seg først som en rød CI hos noen andre.
    """
    linjer: dict[str, str] = {}
    for linje in recipes["check"]:
        for rolle in ("ruff format --check", "ruff check"):
            if rolle in linje:
                linjer[rolle] = linje
                break
    assert set(linjer) == {"ruff check", "ruff format --check"}, (
        f"fant ikke begge ruff-kallene i `just check`: {sorted(linjer)}"
    )
    stier = {
        rolle: sorted(a for a in linje.split() if "/" in a or a.endswith(".py")) for rolle, linje in linjer.items()
    }
    assert stier["ruff check"] == stier["ruff format --check"], (
        f"ruff check og ruff format --check ser på ulike stier: {stier}"
    )
    for krevd in ("custom_components/effektvakt/", "tests/", "tests_ha/", "scripts/"):
        assert krevd in stier["ruff check"], f"`just check` linter ikke {krevd}"


def test_ingen_port_er_radgivende(recipes: dict[str, list[str]], ci: dict) -> None:
    """mypy var rådgivende med `|| true` og samlet opp 26 feil ingen så.

    En port som ikke kan felle, er ikke en port. Det gjelder like mye i
    justfile som i ci.yml, der `continue-on-error` er det samme grepet.
    Codecov-opplastingen er unntaket: dekningstallet er ikke en test, og
    terskelen håndheves av coverage-gate.
    """
    for navn, kropp in recipes.items():
        for linje in kropp:
            assert "|| true" not in linje, f"`just {navn}` svelger et exit-status: {linje!r}"

    for jobbnavn, jobb in ci["jobs"].items():
        for steg in jobb.get("steps", []):
            if not steg.get("continue-on-error"):
                continue
            assert "codecov" in steg.get("uses", ""), (
                f"ci.yml lar {steg.get('name')!r} i jobben {jobbnavn!r} feile uten å felle. "
                "Bare Codecov-opplastingen har lov til det."
            )


def test_docs_navngir_de_samme_fire_sjekkene() -> None:
    """Linjen som forklarer `just check` skal ikke kunne love tre av fire."""
    treff = [linje for sti in PORTDOKUMENTER for linje in _les(sti).splitlines() if "just check" in linje]
    assert treff, "verken AGENTS.md eller docs/development.md forklarer `just check`"
    assert any(all(verktoy in linje for _, verktoy in CHECK_KOMMANDOER) for linje in treff), (
        "ingen doc-linje om `just check` navngir alle fire sjekkene "
        f"({', '.join(v for _, v in CHECK_KOMMANDOER)}). Fant: {treff}"
    )


def test_just_test_er_test_unit_pluss_check(recipes: dict[str, list[str]]) -> None:
    """`just test` skal ikke kunne bli noe annet enn de to andre til sammen."""
    kropp = " ".join(recipes["test"])
    assert "test-unit" in kropp and "check" in kropp, (
        "`just test` skal være test-unit + check, ellers betyr den ene kommandoen "
        f"AGENTS.md ber om før commit noe annet enn den sier. Fant: {kropp!r}"
    )
    assert "test-ha" not in kropp, (
        "`just test` skal ikke kreve et ekte Home Assistant-miljø: AGENTS.md lover at den kjøres før hver commit."
    )


def test_just_test_unit_kjorer_hele_testtreet(recipes: dict[str, list[str]]) -> None:
    """En smalning til én fil ville gitt grønt på resten uten å si fra."""
    kropp = " ".join(recipes["test-unit"])
    assert re.search(r"pytest tests/(?:\s|$|\{)", kropp), f"`just test-unit` kjører ikke hele tests/. Fant: {kropp!r}"
    assert re.search(r"pytest tests_ha", " ".join(recipes["test-ha"])), "`just test-ha` kjører ikke tests_ha/"


def test_alle_just_kommandoer_i_docs_finnes(recipes: dict[str, list[str]]) -> None:
    """En doc som viser til en oppskrift som ikke finnes, er verre enn ingen doc."""
    for sti in DOKUMENTER:
        for navn in re.findall(r"`?just ([a-zA-Z][\w-]*)", _les(sti)):
            assert navn in recipes, f"{sti.relative_to(REPO)} viser til `just {navn}`, som ikke finnes i justfile"


def test_docs_lover_ingen_kommando_repoet_ikke_har() -> None:
    """De gamle inngangene sto igjen i AGENTS.md lenge etter at de var borte.

    `pip install -e` kan ikke virke: pyproject har ikke noe [build-system], og
    tests/conftest.py legger custom_components/ på sys.path selv.
    """
    assert not re.search(r"^\[build-system\]", _les(PYPROJECT), re.MULTILINE), (
        "pyproject har fått et build-system. Da er denne vakten feil, ikke docs."
    )
    for sti in DOKUMENTER:
        # Bare kodeblokkene, ikke prosaen: docs forklarer med vilje hvorfor
        # `pip install -e .` ikke trengs, og den setningen er ikke en kommando.
        for blokk in _kodeblokker(_les(sti)):
            assert "pip install -e" not in blokk, (
                f"{sti.relative_to(REPO)} ber om `pip install -e`, som ikke kan virke uten "
                "build-system. Miljøene settes opp av uv gjennom just-oppskriftene."
            )


def test_ci_kjorer_bare_just_oppskrifter(recipes: dict[str, list[str]], ci: dict) -> None:
    """En rød port skal kunne reproduseres lokalt uten å lese ci.yml."""
    kalt = set()
    for jobb, steg, kommando in _ci_steg_kommandoer(ci):
        kalt |= set(re.findall(r"\bjust ([a-zA-Z][\w-]*)", kommando))
        for verktoy in ("pytest ", "ruff ", "mypy ", "vulture ", "coverage "):
            assert verktoy not in kommando, (
                f"ci.yml kjører {verktoy.strip()} direkte i {jobb!r}, steget {steg!r}. "
                "Alt som også kjøres lokalt skal gå gjennom en just-oppskrift, ellers "
                "finnes kommandolinjen to steder."
            )
    for navn in sorted(kalt):
        assert navn in recipes, f"ci.yml kaller `just {navn}`, som ikke finnes i justfile"
    assert {"check", "coverage-unit", "coverage-ha", "coverage-gate", "test-ha"} <= kalt, (
        f"ci.yml kaller bare {sorted(kalt)}; unit, ekte HA, kvalitet og coverage-terskelen skal alle være med"
    )


def test_ci_jobbene_star_i_dokumentasjonen(ci: dict) -> None:
    """En jobb ingen doc nevner, er en jobb ingen vet hvordan de skal kjøre."""
    dokumentert = "\n".join(_les(sti) for sti in PORTDOKUMENTER)
    for jobb in ci["jobs"]:
        assert re.search(rf"`?\b{re.escape(jobb)}\b", dokumentert), (
            f"ci.yml har jobben {jobb!r}, men verken AGENTS.md eller docs/development.md nevner den"
        )


def test_release_porten_venter_paa_alle_jobbene(ci: dict) -> None:
    """Porten er den grenbeskyttelsen krever grønn, så den må dekke alt.

    Både `needs` og listen inne i skriptet, ellers kan en ny jobb bli med i
    grafen uten at noen krever at den er grønn.
    """
    jobber = set(ci["jobs"]) - {"release-gate"}
    port = ci["jobs"]["release-gate"]
    assert set(port["needs"]) == jobber, (
        f"release-gate venter på {sorted(port['needs'])}, men ci.yml har jobbene {sorted(jobber)}"
    )
    (skript,) = [steg["run"] for steg in port["steps"] if "run" in steg]
    (krevd,) = re.findall(r"required = \(([^)]*)\)", skript)
    assert set(re.findall(r'"([\w-]+)"', krevd)) == jobber, (
        f"release-gate krever {krevd!r}, men ci.yml har jobbene {sorted(jobber)}"
    )


def test_ha_maalene_er_de_samme_i_justfile_ci_og_docs(recipes: dict[str, list[str]], ci: dict) -> None:
    kropp = "\n".join(recipes["test-ha"])
    i_justfile = {m for m in HA_TARGETS if re.search(rf"^\s*{m}\)", kropp, re.MULTILINE)}
    assert i_justfile == HA_TARGETS, f"`just test-ha` godtar {sorted(i_justfile)}, forventet {sorted(HA_TARGETS)}"

    i_ci = set(ci["jobs"]["test-ha"]["strategy"]["matrix"]["target"])
    assert i_ci == HA_TARGETS, f"ci.yml kjører {sorted(i_ci)}, justfile godtar {sorted(HA_TARGETS)}"

    assert '--group "ha-$target"' in kropp, (
        "`just test-ha` slår ikke målet opp som dependency-gruppen ha-<mål>. Da kan "
        "målene og gruppene i pyproject.toml drifte fra hverandre."
    )

    dokumentert = "\n".join(_les(sti) for sti in PORTDOKUMENTER)
    for mal in sorted(HA_TARGETS):
        # Begge skrivemåtene justfile godtar, siden `target=` er valgfritt.
        assert re.search(rf"just test-ha (?:target=)?{mal}\b", dokumentert), (
            f"verken AGENTS.md eller docs/development.md viser `just test-ha {mal}`. "
            "Et mål ingen doc viser hvordan man kjører, blir ikke kjørt."
        )


def test_coverage_terskelen_er_det_samme_tallet_overalt(recipes: dict[str, list[str]]) -> None:
    """Terskelen sto som 90 i docs lenge etter at justfile hadde hevet den til 95."""
    (terskel,) = re.findall(r"--fail-under=(\d+)", "\n".join(recipes["coverage-gate"]))
    for sti in (*PORTDOKUMENTER, CI):
        for linjenr, linje in enumerate(_les(sti).splitlines(), start=1):
            if not re.search(r"coverage|dekning", linje, re.IGNORECASE):
                continue
            for tall in re.findall(r"(\d+)\s*%", linje):
                assert tall == terskel, (
                    f"{sti.relative_to(REPO)}:{linjenr} sier {tall} %, men `just coverage-gate` "
                    f"feller under {terskel} %"
                )


def test_coverage_samler_begge_suitene(recipes: dict[str, list[str]]) -> None:
    """Terskelen skal lese summen, aldri én suite alene."""
    gate = "\n".join(recipes["coverage-gate"])
    assert "coverage combine" in gate, "`just coverage-gate` slår ikke sammen datafilene"
    for datafil, skriver in ((".coverage.unit", "coverage-unit"), (".coverage.ha", "coverage-ha")):
        assert datafil in gate, f"`just coverage-gate` leser ikke {datafil}"
        assert datafil in "\n".join(recipes[skriver]), f"`just {skriver}` skriver ikke {datafil}"


def test_gruppene_i_pyproject_er_de_justfile_og_docs_bruker(recipes: dict[str, list[str]]) -> None:
    grupper = set(tomllib.loads(_les(PYPROJECT))["dependency-groups"])
    assert grupper == {"unit", "kvalitet", "ha-minimum", "ha-current"}, (
        f"uventede dependency-grupper: {sorted(grupper)}"
    )

    kropper = " ".join(linje for kropp in recipes.values() for linje in kropp)
    # `ha-$target` settes fra parameteren, så den kommer ut av regexen som «ha-».
    brukt = {g for g in re.findall(r'--group "?([A-Za-z][\w-]*)', kropper) if g != "ha-"}
    ukjente = brukt - grupper
    assert not ukjente, f"justfile ber om gruppene {sorted(ukjente)}, som ikke finnes i pyproject.toml"
    assert {"unit", "kvalitet"} <= brukt, f"justfile bruker ikke unit og kvalitet: {sorted(brukt)}"

    tabell = _les(DEVELOPMENT)
    for gruppe in sorted(grupper):
        assert f"`{gruppe}`" in tabell, f"docs/development.md mangler gruppen {gruppe} i miljøtabellen"
        assert f".venv-{gruppe}" in tabell, f"docs/development.md mangler miljøet .venv-{gruppe}"


def test_python_versjonene_i_justfile_star_i_docs(recipes: dict[str, list[str]]) -> None:
    """Miljøtabellen i docs skal ikke kunne råtne bort fra justfile."""
    tabell = _les(DEVELOPMENT)
    for navn in sorted(PORT_RECIPES):
        for versjon in re.findall(r'--python "?(3\.\d+)', " ".join(recipes[navn])):
            assert versjon in tabell, (
                f"justfile kjører {navn} på Python {versjon}, men docs/development.md nevner den ikke"
            )
    for versjon in re.findall(r"python=(3\.\d+)", "\n".join(recipes["test-ha"])):
        assert versjon in tabell, f"`just test-ha` kjører Python {versjon}, men docs/development.md nevner den ikke"


def test_pre_commit_kaller_de_samme_oppskriftene(recipes: dict[str, list[str]]) -> None:
    config = yaml.safe_load(_les(PRECOMMIT))
    (pytest_hook,) = [h for repo in config["repos"] for h in repo["hooks"] if h["id"] == "pytest"]
    entry = pytest_hook["entry"].strip()
    assert entry.startswith("just "), (
        f"pre-commit-hooken kjører {entry!r} og ikke en just-oppskrift. Da kan den gå grønn "
        "på noe annet enn det AGENTS.md og CI kjører."
    )
    navn = entry.split()[1]
    assert navn in recipes, f"pre-commit-hooken kaller `just {navn}`, som ikke finnes"
    assert pytest_hook["stages"] == ["pre-push"], (
        "pytest-hooken hører på pre-push; på pre-commit kjører hele suiten for hver commit"
    )


def test_verktoyversjonene_er_de_samme_i_hooken_og_kvalitet_gruppa() -> None:
    """Ulik ruff lokalt og i hooken viser seg som at formateringen endrer seg selv."""
    config = yaml.safe_load(_les(PRECOMMIT))
    revisjoner = {}
    for repo in config["repos"]:
        rev = repo.get("rev")
        if not rev:
            continue
        for hook in repo["hooks"]:
            for verktoy in PINNEDE_VERKTOY:
                if hook["id"].startswith(verktoy):
                    revisjoner[verktoy] = rev.lstrip("v")

    pinner = {
        krav.split("==")[0]: krav.split("==")[1]
        for krav in tomllib.loads(_les(PYPROJECT))["dependency-groups"]["kvalitet"]
        if "==" in krav
    }
    for verktoy in PINNEDE_VERKTOY:
        assert verktoy in revisjoner, f".pre-commit-config.yaml har ingen hook for {verktoy}"
        assert verktoy in pinner, f"kvalitet-gruppa pinner ikke {verktoy} eksakt"
        assert revisjoner[verktoy] == pinner[verktoy], (
            f"{verktoy} er {revisjoner[verktoy]} i pre-commit og {pinner[verktoy]} i kvalitet-gruppa"
        )
    assert f"v{revisjoner['ruff']}" in _les(AGENTS), (
        f"AGENTS.md nevner ikke ruff-versjonen v{revisjoner['ruff']} som faktisk er pinnet"
    )


def test_hacs_json_er_kilden_til_minimumsversjonen() -> None:
    """`just test-ha minimum` må teste det hacs.json lover brukerne.

    Uten koblingen kan hacs.json heves uten at minimum-miljøet endrer seg, og
    da tester vi noe annet enn løftet.
    """
    lovet = json.loads(_les(HACS))["homeassistant"]
    testet = _ha_versjon_per_mal()["minimum"]
    assert lovet == testet, (
        f"hacs.json lover HA {lovet}, men ha-minimum i uv.lock løser til {testet}. Hev begge, eller ingen."
    )


def test_ingen_ha_versjon_star_skrevet_for_hand() -> None:
    """Hver HA-versjon i klartekst må være en av de to uv.lock faktisk løser."""
    gyldige = set(_ha_versjon_per_mal().values())
    for sti in FILER_MED_HA_VERSJON:
        for linjenr, linje in enumerate(_les(sti).splitlines(), start=1):
            for funnet in HA_VERSJON.findall(linje):
                assert funnet in gyldige, (
                    f"{sti.relative_to(REPO)}:{linjenr} nevner HA {funnet}, men uv.lock "
                    f"løser {sorted(gyldige)}. Rett kopien eller lås gruppen på nytt."
                )
