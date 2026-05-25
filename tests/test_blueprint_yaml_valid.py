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


@pytest.mark.parametrize("blueprint_path", sorted(BLUEPRINTS_DIR.glob("*.yaml")))
def test_shed_blueprints_har_max_off_minutes(blueprint_path: Path):
    """Shed-blueprints (alle unntatt kun_varsel) må ha max_off_minutes."""
    if "kun_varsel" in blueprint_path.name:
        pytest.skip("kun_varsel trenger ikke max_off_minutes")
    data = _load(blueprint_path)
    inputs = data["blueprint"]["input"]
    assert "max_off_minutes" in inputs, f"{blueprint_path.name} mangler max_off_minutes failsafe-input"


def test_finnes_minst_4_blueprints():
    paths = list(BLUEPRINTS_DIR.glob("*.yaml"))
    assert len(paths) >= 4


def test_blueprint_filnavn_matcher_konvensjon():
    """Alle blueprints skal ha snake_case-navn."""
    for path in BLUEPRINTS_DIR.glob("*.yaml"):
        name = path.stem
        assert name.islower(), f"{name} må være lowercase"
        assert " " not in name
