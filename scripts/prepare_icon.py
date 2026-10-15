"""Build matching PNG and multi-resolution ICO from the repository's icon master.

The source is a normal WebP image tracked in Git. All generated images
come from this single source.
Run once before the React build and before Nuitka compilation.
"""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "spare_parts.webp"
PNG = ROOT / "frontend" / "src" / "assets" / "spare_parts.png"
ICO = ROOT / "assets" / "spare_parts.ico"
ICON_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48),
              (64, 64), (128, 128), (256, 256)]


def main():
    with Image.open(SOURCE) as source:
        artwork = source.convert("RGBA").resize((256, 256), Image.Resampling.LANCZOS)
    PNG.parent.mkdir(parents=True, exist_ok=True)
    ICO.parent.mkdir(parents=True, exist_ok=True)
    artwork.save(PNG, format="PNG", optimize=True)
    artwork.save(ICO, format="ICO", sizes=ICON_SIZES)
    with Image.open(ICO) as icon:
        assert set(ICON_SIZES) <= icon.info["sizes"], "ICO resolution missing"
    print(f"Generated UI icon: {PNG}")
    print(f"Generated Windows EXE icon: {ICO}")


if __name__ == "__main__":
    main()
