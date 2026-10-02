"""Export the shared application logo as macOS PNG, Windows ICO and README PNG."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "renderer" / "src" / "assets" / "brand" / "app-logo.png"
ICO = Path(__file__).resolve().parent / "icon.ico"
PNG = Path(__file__).resolve().parent / "icon.png"
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def main() -> None:
    if not SRC.is_file():
        raise SystemExit(f"missing {SRC}")
    src = Image.open(SRC).convert("RGBA")
    src.resize((1024, 1024), Image.Resampling.LANCZOS).save(PNG)
    src.resize((512, 512), Image.Resampling.LANCZOS).save(ROOT / "docs" / "screenshots" / "app-icon.png")
    src.save(ICO, format="ICO", sizes=SIZES)
    print(f"wrote {ICO} ({ICO.stat().st_size} bytes) sizes={SIZES} from {SRC}")


if __name__ == "__main__":
    main()
