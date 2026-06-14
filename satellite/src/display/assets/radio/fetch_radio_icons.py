#!/usr/bin/env python3
"""
Build the radio station icon tiles from each broadcaster's official favicon /
apple-touch-icon. Run on a dev machine *with internet* — the satellite never
touches the network; only the generated PNGs in this folder are shipped.

    python3 fetch_radio_icons.py

Each source logo is trimmed, flattened onto its own brand background (or a dark
chip if it has transparent margins), centred, and given uniform rounded corners
so every station reads as a consistent 64×64 "app icon" tile.
"""

import io
import os
import urllib.request

from PIL import Image, ImageDraw

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")

# station id → official logo URL (favicon / apple-touch-icon)
SOURCES = {
    "france_inter": "https://www.radiofrance.fr/external/favicons/franceinter/favicon.png",
    "france_info":  "https://www.radiofrance.fr/external/favicons/franceinfo/favicon.png",
    "rtl":          "https://www.rtl.fr/apple-touch-icon.png",
    "rtl2":         "https://www.rtl2.fr/apple-touch-icon.png",
    "europe2":      "https://www.europe2.fr/wp-content/themes/melty/europeradio/"
                    "assets/images/favicons/favicon64.png",
    "nova":         "https://www.nova.fr/wp-content/thumbnails/uploads/sites/2/"
                    "2024/08/cropped-favicon-4-t-384x384.png",
}

SIZE = 64        # tile size shipped (downscaled at runtime)
RADIUS = 14      # rounded-corner radius
PAD = 6          # inner padding around the logo
CHIP = (26, 30, 43)   # fallback tile colour for logos with transparent margins

HERE = os.path.dirname(os.path.abspath(__file__))


def _fetch(url: str) -> Image.Image:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return Image.open(io.BytesIO(r.read())).convert("RGBA")


def _corner_bg(im: Image.Image):
    px = im.load()
    counts: dict = {}
    for c in [(0, 0), (im.width - 1, 0), (0, im.height - 1), (im.width - 1, im.height - 1)]:
        p = px[c]
        if p[3] > 200:
            counts[p[:3]] = counts.get(p[:3], 0) + 1
    return max(counts, key=counts.get) if counts else CHIP


def build(name: str, url: str):
    im = _fetch(url)
    bbox = im.split()[3].getbbox()      # trim transparent border
    if bbox:
        im = im.crop(bbox)
    alpha = im.split()[3]
    opaque = sum(1 for a in alpha.get_flattened_data() if a > 200) / (im.width * im.height)
    bg = _corner_bg(im) if opaque > 0.85 else CHIP

    tile = Image.new("RGBA", (SIZE, SIZE), (*bg, 255))
    logo = im.copy()
    logo.thumbnail((SIZE - PAD * 2, SIZE - PAD * 2), Image.LANCZOS)
    tile.alpha_composite(logo, ((SIZE - logo.width) // 2, (SIZE - logo.height) // 2))

    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], RADIUS, fill=255)
    tile.putalpha(mask)

    out = os.path.join(HERE, f"{name}.png")
    tile.save(out)
    print(f"{name}: {out}")


if __name__ == "__main__":
    for n, u in SOURCES.items():
        build(n, u)
