"""Verifiser at alle blueprints er gyldig YAML og har nødvendige felt."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

DOCS_DIR = Path(__file__).parent.parent / "docs"
BLUEPRINTS_DIR = DOCS_DIR / "blueprints"
BLUEPRINTS_MD = DOCS_DIR / "blueprints.md"

# Mappen Home Assistant leser blueprints fra, og dermed prefikset i
# use_blueprint: path:. Docs beskriver at filene kopieres til
# config/blueprints/automation/effektvakt/, så prefikset er låst til det.
INSTALLERT_MAPPE = "effektvakt"

RAW_BASE = "https://raw.githubusercontent.com/fredrik-lindseth/hacs-effektvakt/main/docs/blueprints/"

# Gaten hovedbryteren virker gjennom. Tom streng slipper gjennom, se
# test_automatikk_bryteren_er_valgfri.
GATE = "{{ automatikk_switch == '' or is_state(automatikk_switch, 'on') }}"


class _BlueprintLoader(yaml.SafeLoader):
    """SafeLoader som tolererer HA's !input-tag."""


_BlueprintLoader.add_constructor("!input", lambda loader, node: loader.construct_scalar(node))


def _load(path: Path) -> dict:
    return yaml.load(path.read_text(), Loader=_BlueprintLoader)


def _finn_alle(node: Any, nøkkel: str) -> list[Any]:
    """Alle verdier lagret under `nøkkel`, uansett hvor dypt de ligger."""
    funn: list[Any] = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k == nøkkel:
                funn.append(v)
            funn.extend(_finn_alle(v, nøkkel))
    elif isinstance(node, list):
        for v in node:
            funn.extend(_finn_alle(v, nøkkel))
    return funn


@pytest.mark.parametrize("blueprint_path", sorted(BLUEPRINTS_DIR.glob("*.yaml")))
def test_blueprint_is_valid_yaml(blueprint_path: Path):
    """YAML-en må parse uten feil og ha nødvendige felt."""
    data = _load(blueprint_path)
    assert isinstance(data, dict)
    assert "blueprint" in data
    bp = data["blueprint"]
    assert "name" in bp
    assert "description" in bp
    assert "domain" in bp
    assert "input" in bp


LASTKUTT_BLUEPRINTS = sorted(p for p in BLUEPRINTS_DIR.glob("*.yaml") if "kun_varsel" not in p.name)


@pytest.mark.parametrize("blueprint_path", LASTKUTT_BLUEPRINTS)
def test_lastkutt_delegerer_ansvar_til_vedvarende_vern(blueprint_path: Path):
    """Ingen ventetid i en avbrytbar automasjon skal eie gjeninnkoblingen."""
    data = _load(blueprint_path)
    assert not _finn_alle(data, "wait_for_trigger")
    assert not _finn_alle(data, "delay")
    assert set(_finn_alle(data, "service")) == {"effektvakt.styr_last"}
    for handling in data["action"]:
        assert handling["data"]["eier"] == "{{ this.entity_id }}"
        assert handling["data"]["max_off_minutes"] == "{{ max_off_minutes }}"
        assert handling["data"]["min_on_minutes"] == "{{ min_on_minutes }}"
    assert any(t.get("platform") == "time_pattern" for t in data["trigger"])


@pytest.mark.parametrize("blueprint_path", LASTKUTT_BLUEPRINTS)
def test_lastkutt_gir_lasten_påtid_før_nytt_kutt(blueprint_path: Path):
    """Uten en påtid ville lasten blitt kuttet igjen i samme sekund som den
    slippes, og timeskiftet hadde vært et slipp bare på papiret."""
    inputs = _load(blueprint_path)["blueprint"]["input"]
    assert "min_on_minutes" in inputs, f"{blueprint_path.name} mangler min_on_minutes"
    assert inputs["min_on_minutes"]["selector"]["number"]["min"] >= 1, (
        f"{blueprint_path.name} tillater 0 minutter påtid, som er ingen påtid"
    )


@pytest.mark.parametrize("blueprint_path", LASTKUTT_BLUEPRINTS)
def test_lastkutt_gater_kuttingen_på_bryteren(blueprint_path: Path):
    """Hovedbryteren skal virke fra ett sted, så ingen lastkutt-blueprint
    får slippe unna."""
    data = _load(blueprint_path)
    assert "automatikk_switch" in data["blueprint"]["input"], f"{blueprint_path.name} leser ikke hovedbryteren"
    assert "automatikk_switch" in data["variables"], f"{blueprint_path.name} mangler variabelen"
    for handling in data["action"]:
        assert handling["data"]["automatikk_switch"] == "{{ automatikk_switch }}"


def test_kun_varsel_gates_ikke_på_bryteren():
    """Har brukeren skrudd av automatikken, må han kutte selv, og da trenger
    han varselet mer, ikke mindre. Bryteren er fortsatt input, men bare for å
    si fra i teksten at ingenting kuttes av seg selv."""
    path = BLUEPRINTS_DIR / "kun_varsel.yaml"
    data = _load(path)
    assert "condition" not in data, "kun_varsel stopper hele kjøringen på bryteren"
    assert GATE not in path.read_text(), "kun_varsel gater fortsatt på bryteren"
    assert "automatikk_switch" in data["blueprint"]["input"]
    assert "automatikk_switch" in data["variables"]


def test_kun_varsel_sier_kroner_og_handling():
    """«Projisert 9,7 kW. Margin 0,3 kW» sier verken hva det koster eller hva
    du skal gjøre. Varselet skal si begge deler."""
    data = _load(BLUEPRINTS_DIR / "kun_varsel.yaml")
    melding = next(iter(_finn_alle(data, "message")))

    assert "kr " in melding, "varselet sier ikke hva timen koster"
    assert "Slå av" in melding, "varselet sier ikke hva brukeren skal gjøre"

    inputs = data["blueprint"]["input"]
    assert "kostnad_sensor" in inputs, "kronene må komme fra en sensor brukeren kan peke ut"
    assert "tilgjengelig_kutt_sensor" in inputs, "handlingen må komme fra kutt_kilder"


@pytest.mark.parametrize("blueprint_path", sorted(BLUEPRINTS_DIR.glob("*.yaml")))
def test_maler_ser_bare_variabler_som_er_deklarert(blueprint_path: Path):
    """!input substitueres i YAML-en, ikke inne i en Jinja-mal.

    Bruker en mal {{ notify_service }} uten at inputen står under variables,
    er den udefinert når automasjonen kjører.
    """
    data = _load(blueprint_path)
    inputs = set(data["blueprint"]["input"])
    deklarert = set(data.get("variables", {}))

    brukt_i_mal = set()
    for mal in re.findall(r"\{\{(.*?)\}\}|\{%(.*?)%\}", blueprint_path.read_text(), re.DOTALL):
        for navn in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", " ".join(mal)):
            if navn in inputs:
                brukt_i_mal.add(navn)

    mangler = brukt_i_mal - deklarert
    assert not mangler, f"{blueprint_path.name} bruker {sorted(mangler)} i en mal uten å deklarere dem"


@pytest.mark.parametrize("blueprint_path", sorted(BLUEPRINTS_DIR.glob("*.yaml")))
def test_automatikk_bryteren_er_valgfri(blueprint_path: Path):
    """Uten default ville hver eksisterende automasjon brekt ved oppdatering.

    Tom streng er den eneste defaulten som gir mening: den peker ikke på en
    entitets-id som avhenger av config entryen, og malene slipper den
    gjennom slik at automasjonen oppfører seg som før bryteren fantes.
    """
    felt = _load(blueprint_path)["blueprint"]["input"]["automatikk_switch"]
    assert felt.get("default") == "", f"{blueprint_path.name} må ha tom default"


@pytest.mark.parametrize("blueprint_path", LASTKUTT_BLUEPRINTS)
def test_restore_er_ikke_gatet_av_bryteren(blueprint_path: Path):
    """Bryteren skal stoppe kutt, ikke tilbakestilling.

    Gatet vi også restore, kunne en last bli stående av fordi noen vippet
    bryteren mens kuttet pågikk. Derfor sitter condition-en inne i choose-
    grenene og aldri på toppnivå i en blueprint som slår noe på igjen.
    """
    data = _load(blueprint_path)
    assert "condition" not in data, f"{blueprint_path.name} gater hele automasjonen"


@pytest.mark.parametrize("blueprint_path", sorted(BLUEPRINTS_DIR.glob("*.yaml")))
def test_source_url_kan_importeres_av_home_assistant(blueprint_path: Path):
    """HA sin importer tar raw.githubusercontent.com eller en /blob/-url.

    En github.com/.../raw/...-url matcher ingen av dem, og import-dialogen
    svarer «Unsupported URL».
    """
    source_url = _load(blueprint_path)["blueprint"]["source_url"]
    assert source_url == RAW_BASE + blueprint_path.name, f"{blueprint_path.name} peker feil"


def test_import_lenkene_i_docs_peker_på_de_samme_filene():
    md = BLUEPRINTS_MD.read_text()
    lenket = set(re.findall(r"blueprint_url=https%3A%2F%2F([^)\s]+)", md))
    forventet = {
        (RAW_BASE + p.name).removeprefix("https://").replace("/", "%2F") for p in BLUEPRINTS_DIR.glob("*.yaml")
    }
    assert lenket == forventet


def test_docs_bruker_stien_blueprintene_faktisk_får():
    """use_blueprint: path: er mappen filen havnet i hos brukeren pluss
    filnavnet med .yaml, ikke filnavnet i dette repoet."""
    stier = re.findall(r"^\s*path:\s*(\S+)\s*$", BLUEPRINTS_MD.read_text(), re.MULTILINE)
    assert stier, "blueprints.md viser ingen use_blueprint-eksempler"

    filnavn = {p.name for p in BLUEPRINTS_DIR.glob("*.yaml")}
    for sti in stier:
        mappe, _, navn = sti.partition("/")
        assert mappe == INSTALLERT_MAPPE, f"{sti} har feil mappe"
        assert navn in filnavn, f"{sti} peker på en blueprint som ikke finnes"
    assert len(set(stier)) == len(filnavn), "alle fire blueprints skal ha et eksempel"


def test_finnes_minst_4_blueprints():
    paths = list(BLUEPRINTS_DIR.glob("*.yaml"))
    assert len(paths) >= 4


def test_blueprint_filnavn_matcher_konvensjon():
    """Alle blueprints skal ha snake_case-navn."""
    for path in BLUEPRINTS_DIR.glob("*.yaml"):
        name = path.stem
        assert name.islower(), f"{name} må være lowercase"
        assert " " not in name
