"""Brand-bildene Home Assistant og HACS leser fra custom_components/effektvakt/brand/.

HA serverer dem gjennom Brands Proxy API-et naar `brand` ligger blant filene paa
toppnivaa i integrasjonsmappen (`integration.has_branding` i loader.py), og HACS sin
brands-sjekk gaar gjennom naar brand/icon.png finnes. PNG-ene rendres fra images/icon.svg
av scripts/generate_brand_images.py. CI har ingen rsvg-convert, saa disse testene bruker
bare standardbiblioteket: PNG-headeren for stoerrelse og fargetype, kildehashen scriptet
skriver inn i en tEXt-chunk for ferskhet, og en liten dekoder for gjennomsikt og trimming.
"""

from __future__ import annotations

import importlib.util
import re
import struct
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts/generate_brand_images.py"
_spec = importlib.util.spec_from_file_location("generate_brand_images", SCRIPT)
assert _spec is not None and _spec.loader is not None
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)

# Filnavnene Brands Proxy API-et leter etter; alt annet i brand/ er stoey.
_PREFIXES = ("", "dark_")
_KINDS = ("icon", "logo")
_SCALES = ("", "@2x")
ALLOWED_NAMES = {f"{p}{k}{s}.png" for p in _PREFIXES for k in _KINDS for s in _SCALES}

# Home Assistants lyse og moerke sidebakgrunn.
LIGHT_BACKGROUND = "#ffffff"
DARK_BACKGROUND = "#111111"
# WCAG 1.4.11: grafiske objekter trenger 3:1 mot det de ligger paa.
MIN_CONTRAST = 3.0


def _header(path: Path) -> tuple[int, int, int, int, int]:
    """Bredde, hoeyde, bitdybde, fargetype og interlace fra IHDR."""
    data = path.read_bytes()
    assert data.startswith(gen.PNG_SIGNATURE), f"{path.name} er ingen PNG"
    assert data[12:16] == b"IHDR", f"{path.name} starter ikke med IHDR"
    width, height, depth, colour, _comp, _filter, interlace = struct.unpack(">IIBBBBB", data[16:29])
    return width, height, depth, colour, interlace


def _alpha_rows(path: Path) -> list[bytes]:
    """Alfakanalen per rad i en 8-bits RGBA-PNG uten interlace."""
    width, height, depth, colour, interlace = _header(path)
    assert (depth, colour, interlace) == (8, 6, 0)
    stream = gen.pixel_stream(path.read_bytes())
    stride = width * 4
    rows: list[bytes] = []
    previous = bytearray(stride)
    for y in range(height):
        start = y * (stride + 1)
        kind = stream[start]
        row = bytearray(stream[start + 1 : start + 1 + stride])
        for i in range(stride):
            left = row[i - 4] if i >= 4 else 0
            up = previous[i]
            up_left = previous[i - 4] if i >= 4 else 0
            if kind == 1:
                row[i] = (row[i] + left) & 0xFF
            elif kind == 2:
                row[i] = (row[i] + up) & 0xFF
            elif kind == 3:
                row[i] = (row[i] + (left + up) // 2) & 0xFF
            elif kind == 4:
                p = left + up - up_left
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - up_left)
                pred = left if pa <= pb and pa <= pc else up if pb <= pc else up_left
                row[i] = (row[i] + pred) & 0xFF
        rows.append(bytes(row[3::4]))
        previous = row
    return rows


def _luminance(hex_colour: str) -> float:
    channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _svg_tokens() -> dict[str, str]:
    """Klassenavn -> farge fra style-blokken oeverst i SVG-en."""
    style = re.search(r"<style>(.*?)</style>", gen.SOURCE_SVG.read_text(), re.S)
    assert style, "images/icon.svg har ingen <style>-blokk med fargetoken"
    rule = r"\.([\w-]+)\s*\{\s*(?:fill|stroke)\s*:\s*(#[0-9A-Fa-f]{6})\s*;"
    return dict(re.findall(rule, style.group(1)))


def test_brand_mappen_har_bare_navn_brands_api_et_leser():
    names = {p.name for p in gen.BRAND_DIR.iterdir() if not p.name.startswith(".")}
    assert names <= ALLOWED_NAMES, f"uventede filer i brand/: {sorted(names - ALLOWED_NAMES)}"


def test_brand_mappen_ligger_paa_toppnivaa_i_integrasjonen():
    """has_branding i loader.py er sann naar 'brand' ligger rett i integrasjonsmappen."""
    assert gen.BRAND_DIR.name == "brand"
    assert (gen.BRAND_DIR.parent / "manifest.json").is_file()


@pytest.mark.parametrize(("name", "size"), gen.OUTPUTS.items())
def test_ikonet_er_en_kvadratisk_rgba_png_i_riktig_stoerrelse(name, size):
    path = gen.BRAND_DIR / name
    assert path.is_file(), f"{name} mangler; kjoer python3 scripts/generate_brand_images.py"
    width, height, depth, colour, _interlace = _header(path)
    assert (width, height) == (size, size)
    assert (depth, colour) == (8, 6), "ventet 8-bits RGBA saa bakgrunnen forblir gjennomsiktig"


@pytest.mark.parametrize("name", gen.OUTPUTS)
def test_ikonet_ble_rendret_fra_dagens_svg(name):
    chunks = gen.text_chunks((gen.BRAND_DIR / name).read_bytes())
    utdatert = f"{name} ble ikke rendret fra dagens images/icon.svg; kjoer {SCRIPT.name} paa nytt"
    assert chunks.get(gen.SOURCE_HASH_KEY) == gen.source_hash().encode(), utdatert


def test_ikonet_er_gjennomsiktig_og_trimmet():
    rows = _alpha_rows(gen.BRAND_DIR / "icon.png")
    assert rows[0][0] == 0 and rows[-1][0] == 0, "hjoernene maa vaere gjennomsiktige"
    assert any(rows[0]) and any(rows[-1]), "motivet maa naa topp- og bunnkanten (trimmet)"
    assert any(row[0] for row in rows), "motivet maa naa venstrekanten (trimmet)"
    assert any(row[-1] for row in rows), "motivet maa naa hoeyrekanten (trimmet)"


def test_svg_farger_kommer_bare_fra_token_blokken():
    text = gen.SOURCE_SVG.read_text()
    # Kommentarene er unntatt: de begrunner fargevalget ved aa sitere paletten i
    # faceplate.py, og en hex der naar aldri en tegnet flate.
    outside = re.sub(r"<style>.*?</style>|<!--.*?-->", "", text, flags=re.S)
    assert not re.search(r"#[0-9A-Fa-f]{3,8}\b", outside), "skriv farger som klasseregler i <style>"
    assert not re.search(r"Gradient", text), "ikonet er flatt; ingen gradienter"


def test_svg_en_har_tekstalternativ():
    text = gen.SOURCE_SVG.read_text()
    assert "<title" in text and "<desc" in text, "SVG-en trenger title og desc"
    assert 'role="img"' in text and "aria-labelledby" in text


@pytest.mark.parametrize("background", [LIGHT_BACKGROUND, DARK_BACKGROUND])
def test_hvert_fargetoken_holder_kontrast_paa_begge_bakgrunner(background):
    tokens = _svg_tokens()
    assert tokens, "fant ingen fargetoken i images/icon.svg"
    for name, colour in tokens.items():
        ratio = _contrast(colour, background)
        assert ratio >= MIN_CONTRAST, f".{name} {colour} er {ratio:.2f}:1 paa {background}"
