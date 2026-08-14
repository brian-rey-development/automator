"""Generate the Automator icon (brand isotype) in .ico and .png formats.

Draws the chartreuse tile with the dark bolt (the same isotype as the sidebar) and
exports it in several sizes. Used in packaging (PyInstaller/installer).

Usage:
    python scripts/generate_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

_ACCENT = (201, 242, 77, 255)  # #C9F24D chartreuse
_DARK = (22, 24, 29, 255)  # #16181D almost black
# Normalized coordinates of the bolt (same as the sidebar isotype).
_BOLT = (0.56, 0.14, 0.31, 0.55, 0.47, 0.55, 0.42, 0.86, 0.69, 0.43, 0.51, 0.43, 0.60, 0.14)
_ICO_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def render(size: int = 256) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * 0.22), fill=_ACCENT)
    points = [(_BOLT[i] * size, _BOLT[i + 1] * size) for i in range(0, len(_BOLT), 2)]
    draw.polygon(points, fill=_DARK)
    return image


def main() -> None:
    out_dir = Path(__file__).resolve().parent.parent / "assets"
    out_dir.mkdir(parents=True, exist_ok=True)
    base = render(256)
    base.save(out_dir / "automator.ico", sizes=_ICO_SIZES)
    base.save(out_dir / "automator.png")
    print(f"Icono generado en {out_dir}")


if __name__ == "__main__":
    main()
