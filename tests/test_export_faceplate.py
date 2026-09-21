"""Tester for scripts/export_faceplate.py."""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "export_faceplate.py"


def _last_script() -> ModuleType:
    """Last eksportscriptet som modul, slik scriptet selv laster dso.py."""
    spec = importlib.util.spec_from_file_location("export_faceplate", SCRIPT)
    assert spec is not None and spec.loader is not None
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


export_faceplate = _last_script()


def test_skriver_svg_til_fil(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ut = tmp_path / "bkk.svg"
    kode = export_faceplate.main(["--dso", "bkk", "--out", str(ut)])
    assert kode == 0
    svg = ut.read_text(encoding="utf-8")
    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")
    assert 'data-maks-kw="15"' in svg
    assert "BKK" in svg
    assert str(ut) in capsys.readouterr().out


def test_viewbox_er_hundre_millimeter(tmp_path: Path) -> None:
    ut = tmp_path / "bkk.svg"
    export_faceplate.main(["--dso", "bkk", "--out", str(ut)])
    # 1000 enheter der en enhet er 0,1 mm, altså 100 mm i faktisk størrelse.
    assert 'viewBox="0 0 1000 1000"' in ut.read_text(encoding="utf-8")


def test_print_er_uten_visere_og_card_har_dem(tmp_path: Path) -> None:
    trykk = tmp_path / "print.svg"
    kort = tmp_path / "card.svg"
    export_faceplate.main(["--dso", "bkk", "--variant", "print", "--out", str(trykk)])
    export_faceplate.main(["--dso", "bkk", "--variant", "card", "--out", str(kort)])
    assert 'id="viser-rod"' not in trykk.read_text(encoding="utf-8")
    assert 'id="viser-rod"' in kort.read_text(encoding="utf-8")


def test_lager_kataloger_som_mangler(tmp_path: Path) -> None:
    ut = tmp_path / "trykk" / "2026" / "bkk.svg"
    assert export_faceplate.main(["--dso", "bkk", "--out", str(ut)]) == 0
    assert ut.exists()


def test_standard_filnavn_i_arbeidskatalogen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert export_faceplate.main(["--dso", "bkk"]) == 0
    assert (tmp_path / "geha-meter-bkk-print.svg").exists()


def test_maks_kw_rundes_opp_og_sies_fra(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ut = tmp_path / "bkk.svg"
    export_faceplate.main(["--dso", "bkk", "--maks-kw", "22", "--out", str(ut)])
    utskrift = capsys.readouterr().out
    assert "30" in utskrift
    assert 'data-maks-kw="30"' in ut.read_text(encoding="utf-8")


def test_ugyldig_maks_kw(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    kode = export_faceplate.main(["--dso", "bkk", "--maks-kw", "0", "--out", str(tmp_path / "x.svg")])
    assert kode == 2
    assert "maks-kw" in capsys.readouterr().err


def test_ukjent_dso_foreslar_naermeste(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    kode = export_faceplate.main(["--dso", "bkkk", "--out", str(tmp_path / "x.svg")])
    assert kode == 2
    feil = capsys.readouterr().err
    assert "bkk" in feil
    assert "--liste" in feil
    assert not (tmp_path / "x.svg").exists()


def test_dso_kan_oppgis_som_navn(tmp_path: Path) -> None:
    ut = tmp_path / "bkk.svg"
    assert export_faceplate.main(["--dso", "BKK", "--out", str(ut)]) == 0
    assert ut.exists()


def test_manglende_dso_peker_paa_liste(capsys: pytest.CaptureFixture[str]) -> None:
    assert export_faceplate.main([]) == 2
    assert "--liste" in capsys.readouterr().err


def test_liste_viser_id_og_navn(capsys: pytest.CaptureFixture[str]) -> None:
    assert export_faceplate.main(["--liste"]) == 0
    utskrift = capsys.readouterr().out
    assert "bkk" in utskrift
    assert "BKK" in utskrift
    assert "NO5" in utskrift


def test_finn_dso_og_forslag() -> None:
    tabell, _ = export_faceplate.last_moduler()
    assert export_faceplate.finn_dso(tabell, "  BkK ") == "bkk"
    assert export_faceplate.finn_dso(tabell, "finnes-ikke") is None
    assert "bkk" in export_faceplate.forslag(tabell, "bkk-nett")


def test_png_feiler_pent_uten_rsvg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(export_faceplate.shutil, "which", lambda _navn: None)
    with pytest.raises(SystemExit) as feil:
        export_faceplate.til_png(tmp_path / "bkk.svg")
    assert "librsvg" in str(feil.value)


@pytest.mark.skipif(shutil.which("rsvg-convert") is None, reason="rsvg-convert mangler")
def test_png_renderes_naar_rsvg_finnes(tmp_path: Path) -> None:
    ut = tmp_path / "bkk.svg"
    assert export_faceplate.main(["--dso", "bkk", "--out", str(ut), "--png"]) == 0
    png = ut.with_suffix(".png")
    assert png.exists()
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
