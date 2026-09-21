"""Rendre integrasjonsikonet fra images/icon.svg til brand/-mappen.

Home Assistant leser brand-bilder for custom integrations fra
custom_components/effektvakt/brand/ foer den gaar til brands-CDN-en, og HACS godtar
brand/icon.png i stedet for en oppfoering i home-assistant/brands. PNG-ene der er
generert og aldri redigert for haand:

    python3 scripts/generate_brand_images.py          # skriv PNG-ene
    python3 scripts/generate_brand_images.py --sjekk  # exit 1 hvis de er utdaterte

Rendringen trenger rsvg-convert (librsvg). Ingenting annet gjoer det: hver PNG baerer
SHA-256-en av SVG-en den kom fra i en tEXt-chunk, saa tests/test_brand_images.py kan
skille en utdatert PNG fra en fersk med standardbiblioteket alene.

PNG-en skrives om etter rendring: bKGD-chunken fra rsvg-convert droppes (en viser kan
male den fargen bak det gjennomsiktige ikonet), kildehashen legges til, og bildedataene
komprimeres paa nytt med zlib-nivaa 9.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_SVG = REPO_ROOT / "images" / "icon.svg"
BRAND_DIR = REPO_ROOT / "custom_components" / "effektvakt" / "brand"

# Filnavn -> kantlengde i piksler, fra ikonreglene i home-assistant/brands.
OUTPUTS = {"icon.png": 256, "icon@2x.png": 512}

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SOURCE_HASH_KEY = b"effektvakt-source-sha256"


def source_hash(svg: Path = SOURCE_SVG) -> str:
    return hashlib.sha256(svg.read_bytes()).hexdigest()


def read_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    """Del en PNG i (type, innhold)-par, og sjekk signaturen."""
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("ikke en PNG-fil")
    chunks = []
    pos = len(PNG_SIGNATURE)
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        kind = data[pos + 4 : pos + 8]
        chunks.append((kind, data[pos + 8 : pos + 8 + length]))
        pos += 12 + length
    return chunks


def text_chunks(data: bytes) -> dict[bytes, bytes]:
    return dict(payload.split(b"\0", 1) for kind, payload in read_chunks(data) if kind == b"tEXt")


def pixel_stream(data: bytes) -> bytes:
    """De dekomprimerte, fortsatt filtrerte bildedataene: like stroemmer er like piksler."""
    idat = b"".join(payload for kind, payload in read_chunks(data) if kind == b"IDAT")
    return zlib.decompress(idat)


def _chunk(kind: bytes, payload: bytes) -> bytes:
    crc = struct.pack(">I", zlib.crc32(kind + payload))
    return struct.pack(">I", len(payload)) + kind + payload + crc


def rewrite_png(rendered: bytes, svg_hash: str) -> bytes:
    """Behold IHDR og pikslene, legg til kildehashen, dropp alt annet."""
    chunks = read_chunks(rendered)
    header = next(payload for kind, payload in chunks if kind == b"IHDR")
    pixels = pixel_stream(rendered)
    return (
        PNG_SIGNATURE
        + _chunk(b"IHDR", header)
        + _chunk(b"tEXt", SOURCE_HASH_KEY + b"\0" + svg_hash.encode("ascii"))
        + _chunk(b"IDAT", zlib.compress(pixels, 9))
        + _chunk(b"IEND", b"")
    )


def render(size: int, svg: Path = SOURCE_SVG) -> bytes:
    rsvg = shutil.which("rsvg-convert")
    if rsvg is None:
        sys.exit(
            "rsvg-convert ble ikke funnet. Den foelger med librsvg: "
            "`brew install librsvg` paa macOS, `apt install librsvg2-bin` paa Debian og Ubuntu."
        )
    result = subprocess.run(
        [rsvg, "--width", str(size), "--height", str(size), "--format", "png", str(svg)],
        capture_output=True,
        check=True,
    )
    return rewrite_png(result.stdout, source_hash(svg))


def _matcher(data: bytes) -> tuple[object, object, object]:
    """Det som avgjoer om to PNG-er er like: header, metadata og piksler."""
    return read_chunks(data)[0], text_chunks(data), pixel_stream(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--sjekk",
        action="store_true",
        help="sammenlign med filene paa disk i stedet for aa skrive",
    )
    args = parser.parse_args()

    stale = []
    for name, size in OUTPUTS.items():
        fresh = render(size)
        target = BRAND_DIR / name
        if args.sjekk:
            # Sammenlign piksler og metadata, ikke komprimerte bytes, som kan sprike
            # mellom zlib-bygg.
            current = target.read_bytes() if target.is_file() else b""
            if not current or _matcher(current) != _matcher(fresh):
                stale.append(name)
            continue
        BRAND_DIR.mkdir(parents=True, exist_ok=True)
        target.write_bytes(fresh)
        print(f"skrev {target.relative_to(REPO_ROOT)} ({size}x{size}, {len(fresh)} bytes)")

    if stale:
        navn = ", ".join(stale)
        hint = "kjoer python3 scripts/generate_brand_images.py"
        print(f"utdaterte brand-bilder: {navn}; {hint}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
