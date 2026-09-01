#!/usr/bin/env python3
"""
Pre-render the boot splash to a raw RGB565 frame.

The splash has to be on the panel before Python can afford to import numpy and
Pillow (together ~2s from a cold page cache on this Pi), so the pixels are
rendered ahead of time here and the boot path only streams the bytes. Run once
at deploy time — the output is a build artefact, not something to commit:

    python3 src/display/make_splash.py            # → assets/boot_splash.rgb565
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PIL import ImageDraw

from config import STATE_IDLE
from display import theme as T
from display.theme import W, H

OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..",
                                   "assets", "boot_splash.rgb565"))


def render():
    """The LED-ring motif: three lit dots inside a halo, wordmark underneath."""
    accent = T.ACCENT[STATE_IDLE]
    img = T.background(accent)
    draw = ImageDraw.Draw(img)

    cx, cy, r = T.CX, 132, 52
    # Concentric rings, fading outward — the glow the LED strip actually makes.
    for i, f in enumerate((0.10, 0.18, 0.34)):
        rr = r + 26 - i * 13
        draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr],
                     outline=T.mix(T.BG_TOP, accent, f), width=2)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                 outline=T.mix(T.BG_TOP, accent, 0.55), width=3)

    # Three dots = the three WS2812Bs on the front of the case.
    for k, dx in enumerate((-24, 0, 24)):
        rad = 9 if dx == 0 else 6
        col = accent if dx == 0 else T.mix(T.BG_TOP, accent, 0.75)
        draw.ellipse([cx + dx - rad, cy - rad, cx + dx + rad, cy + rad], fill=col)

    T.text_center(draw, cx, cy + r + 44, "pi-satellite", T.F_TITLE, T.INK)
    T.text_center(draw, cx, cy + r + 78, "assistant vocal", T.F_SMALL, T.INK_FAINT)
    return img


def main():
    img = render()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "wb") as f:
        f.write(T.to_rgb565(img))
    print(f"{OUT}  {W}x{H}  {os.path.getsize(OUT)} bytes  "
          f"({datetime.now():%Y-%m-%d %H:%M})")


if __name__ == "__main__":
    main()
