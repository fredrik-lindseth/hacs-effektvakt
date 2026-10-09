"""Kjør språkregresjoner mot den ekte kortfilen når Node er tilgjengelig."""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="Kortets JavaScript-regresjoner krever Node")
def test_kortets_spraak_og_synlige_tekster():
    resultat = subprocess.run(
        ["node", "--test", str(Path(__file__).with_name("card_sprak.cjs"))],
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultat.returncode == 0, resultat.stdout + resultat.stderr
