"""Convert docs/screenshots/app-icon.png into a multi-size Windows ICO + PNG."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "screenshots" / "app-icon.png"
ICO = Path(__file__).resolve().parent / "icon.ico"
PNG = Path(__file__).resolve().parent / "icon.png"
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def main() -> None:
    if not SRC.is_file():
        raise SystemExit(f"missing {SRC}")
    src = Image.open(SRC).convert("RGBA")
    PNG.write_bytes(SRC.read_bytes())
    src.save(ICO, format="ICO", sizes=SIZES)
    print(f"wrote {ICO} ({ICO.stat().st_size} bytes) sizes={SIZES} from {SRC}")


if __name__ == "__main__":
    main()
