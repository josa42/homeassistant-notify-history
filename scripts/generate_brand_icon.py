#!/usr/bin/env python3
"""Generate the Home Assistant brand assets for this integration.

Kept in the repo so the mark can be tweaked and regenerated rather than being
an opaque binary nobody can change. Run it from the repository root:

    venv/bin/python scripts/generate_brand_icon.py
"""

from __future__ import annotations

import pathlib

from PIL import Image, ImageDraw

OUT = pathlib.Path("custom_components/notify_history/brand")

# Drawn at 4x and downsampled, which is cheaper than hand-rolling antialiasing.
SUPERSAMPLE = 4
BASE = 256

BACKGROUND = (3, 105, 161, 255)  # sky blue, reads well on light and dark
CARD = (245, 247, 250, 255)  # near white
# The older messages fade into the background.
OLDER = (125, 186, 222, 255)
OLDEST = (64, 146, 194, 255)
LINE = (3, 105, 161, 255)
DOT = (255, 194, 77, 255)  # amber


def draw(size: int) -> Image.Image:
    """Draw the mark: a stack of message cards, the newest one on top."""
    s = size * SUPERSAMPLE
    unit = s / BASE
    image = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    canvas = ImageDraw.Draw(image, "RGBA")

    def box(x0: float, y0: float, x1: float, y1: float) -> list[float]:
        return [x0 * unit, y0 * unit, x1 * unit, y1 * unit]

    canvas.rounded_rectangle(box(0, 0, 255, 255), radius=int(56 * unit), fill=BACKGROUND)

    # The older messages, peeking out below the newest one.
    canvas.rounded_rectangle(box(72, 150, 184, 208), radius=int(16 * unit), fill=OLDEST)
    canvas.rounded_rectangle(box(56, 130, 200, 186), radius=int(18 * unit), fill=OLDER)

    # The newest message: a card with two lines of text and an unread dot.
    canvas.rounded_rectangle(box(40, 52, 216, 160), radius=int(20 * unit), fill=CARD)
    canvas.rounded_rectangle(box(64, 82, 164, 98), radius=int(7 * unit), fill=LINE)
    canvas.rounded_rectangle(box(64, 114, 140, 130), radius=int(7 * unit), fill=LINE)
    canvas.ellipse(box(178, 34, 226, 82), fill=DOT)

    return image.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, size in (("icon.png", 256), ("icon@2x.png", 512)):
        image = draw(size)
        image.save(OUT / name, "PNG", optimize=True)
        print(f"  {OUT / name}  {size}x{size}")


if __name__ == "__main__":
    main()
