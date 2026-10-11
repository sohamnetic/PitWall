"""Generate the PitWall app icons (PWA + favicon) into frontend/public/icons.

Run once after changing the design:  backend/.venv/Scripts/python scripts/make_icons.py
Needs Pillow (`pip install pillow`). The generated PNGs are committed, so building the app
does not need this script.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "frontend" / "public" / "icons"
RED = (225, 6, 0)
INK = (21, 21, 30)
WHITE = (255, 255, 255)


def draw_icon(size: int, maskable: bool = False) -> Image.Image:
    """PitWall mark: a slanted red tile with three rising white bars (a forecast) on dark."""
    scale = 4  # draw large, then downsample for smooth edges
    s = size * scale
    img = Image.new(
        "RGB" if maskable else "RGBA", (s, s), INK if maskable else (0, 0, 0, 0)
    )
    d = ImageDraw.Draw(img)
    if not maskable:
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=INK)
    # Maskable icons get cropped to a circle: keep the mark in the central ~60%.
    box = s * (0.58 if maskable else 0.70)
    ox, oy = (s - box) / 2, (s - box) / 2
    k = box / 32  # the mark is designed on a 32-unit grid (same as the header logo)

    def pt(x: float, y: float) -> tuple[float, float]:
        return (ox + x * k, oy + y * k)

    d.polygon([pt(7, 2), pt(30, 2), pt(25, 30), pt(2, 30)], fill=RED)
    shear = 0.176  # skewX(-10deg), matching the logo's slant
    for x, top in ((9, 19), (14.5, 14), (20, 8)):
        bottom, w = 25, 3.2
        d.polygon(
            [pt(x - top * shear + 2.6, top), pt(x + w - top * shear + 2.6, top),
             pt(x + w - bottom * shear + 2.6, bottom), pt(x - bottom * shear + 2.6, bottom)],
            fill=WHITE,
        )  # fmt: skip
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for size in (192, 512):
        draw_icon(size).save(OUT / f"icon-{size}.png")
        draw_icon(size, maskable=True).save(OUT / f"maskable-{size}.png")
    draw_icon(180, maskable=True).save(
        OUT / "apple-touch-icon.png"
    )  # iOS adds its own mask
    draw_icon(32).save(OUT / "favicon-32.png")
    print("icons ->", OUT)


if __name__ == "__main__":
    main()
