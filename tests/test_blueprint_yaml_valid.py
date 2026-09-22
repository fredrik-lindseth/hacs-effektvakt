"""Verifiser at alle blueprints er gyldig YAML og har nødvendige felt."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

BLUEPRINTS_DIR = Path(__file__).parent.parent / "docs" / "blueprints"


class _BlueprintLoader(yaml.SafeLoader):
    """SafeLoader som tolererer HA's !input-tag."""


_BlueprintLoader.add_constructor("!input", lambda loader, node: loader.construct_scalar(node))


def _load(path: Path) -> dict:
    return yaml.load(path.read_text(), Loader=_BlueprintLoader)


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
def test_lastkutt_blueprints_har_max_off_minutes(blueprint_path: Path):
    """Lastkutt-blueprints (alle unntatt kun_varsel) må ha max_off_minutes."""
    data = _load(blueprint_path)
    inputs = data["blueprint"]["input"]
    assert "max_off_minutes" in inputs, f"{blueprint_path.name} mangler max_off_minutes failsafe-input"


@pytest.mark.parametrize("blueprint_path", sorted(BLUEPRINTS_DIR.glob("*.yaml")))
def test_alle_blueprints_sjekker_automatikk_bryteren(blueprint_path: Path):
    """Hovedbryteren skal virke fra ett sted, så ingen blueprint får slippe unna."""
    data = _load(blueprint_path)
    assert "automatikk_switch" in data["blueprint"]["input"], f"{blueprint_path.name} leser ikke hovedbryteren"
    assert "automatikk_switch" in data["variables"], f"{blueprint_path.name} mangler variabelen"
    gate = "is_state(automatikk_switch, 'on')"
    assert gate in blueprint_path.read_text(), f"{blueprint_path.name} har input men ingen condition"


@pytest.mark.parametrize("blueprint_path", sorted(BLUEPRINTS_DIR.glob("*.yaml")))
def test_automatikk_bryteren_er_valgfri(blueprint_path: Path):
    """Uten default ville hver eksisterende automasjon brekt ved oppdatering.

    Tom streng er den eneste defaulten som gir mening: den peker ikke på en
    entitets-id som avhenger av config entryen, og condition-en slipper den
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


def test_finnes_minst_4_blueprints():
    paths = list(BLUEPRINTS_DIR.glob("*.yaml"))
    assert len(paths) >= 4


def test_blueprint_filnavn_matcher_konvensjon():
    """Alle blueprints skal ha snake_case-navn."""
    for path in BLUEPRINTS_DIR.glob("*.yaml"):
        name = path.stem
        assert name.islower(), f"{name} må være lowercase"
        assert " " not in name
