"""
Visual theme — fonts, palette, per-state accent, and drawing helpers.

The whole UI is dark with a single accent colour that shifts with the voice
assistant state (idle → listening → processing → speaking → error). Keeping
the palette in one place makes every screen feel like one device.
"""

import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from config import (
    DISPLAY_WIDTH, DISPLAY_HEIGHT,
    STATE_IDLE, STATE_LISTENING, STATE_PROCESSING, STATE_SPEAKING, STATE_ERROR,
)

W, H = DISPLAY_WIDTH, DISPLAY_HEIGHT
CX, CY = W // 2, H // 2

# ── Palette ─────────────────────────────────────────────────────────────────
# Surfaces sit ABOVE the background on contrast alone — no accent outlines.
# The step from BG → CARD → CARD_HI is what reads as elevation on the panel.
BG_TOP    = (12, 14, 22)     # subtle vertical gradient, top
BG_BOTTOM = (4,  5, 11)      # bottom (near black)
INK       = (237, 241, 249)  # primary text (warm white)
INK_DIM   = (150, 158, 176)  # secondary text
INK_FAINT = (78,  86, 104)   # tertiary text
HAIRLINE  = (46,  52,  70)   # neutral card edge (NEVER accent) — defines surfaces
CARD      = (26, 30, 43)     # raised surface
CARD_HI   = (38, 44, 61)     # raised surface, pressed/active/selected

# Accent per voice state — used for glow, active chips, sliders, waveform.
ACCENT = {
    STATE_IDLE:       (80, 150, 255),   # calm blue (ambient)
    STATE_LISTENING:  (0,  198, 255),   # vivid cyan
    STATE_PROCESSING: (170, 90,  255),  # violet
    STATE_SPEAKING:   (40,  220, 120),  # green
    STATE_ERROR:      (255, 70,  50),   # red
}

STATE_LABEL = {
    STATE_IDLE:       "",
    STATE_LISTENING:  "À L'ÉCOUTE",
    STATE_PROCESSING: "RÉFLEXION",
    STATE_SPEAKING:   "RÉPONSE",
    STATE_ERROR:      "ERREUR",
}

# ── Fonts ─────────────────────────────────────────────────────────────────
_RB = "/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF"
_DV = "/usr/share/fonts/truetype/dejavu"


def _find(*paths):
    for p in paths:
        if os.path.exists(p):
            return p
    return None


_F_THIN   = _find(f"{_RB}/Roboto-Thin.ttf",   f"{_DV}/DejaVuSans.ttf")
_F_LIGHT  = _find(f"{_RB}/Roboto-Light.ttf",  f"{_DV}/DejaVuSans.ttf")
_F_REG    = _find(f"{_RB}/Roboto-Regular.ttf", f"{_DV}/DejaVuSans.ttf")
_F_MEDIUM = _find(f"{_RB}/Roboto-Medium.ttf", f"{_DV}/DejaVuSans-Bold.ttf")


def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    path = {"thin": _F_THIN, "light": _F_LIGHT,
            "reg": _F_REG, "medium": _F_MEDIUM}.get(weight, _F_REG)
    return ImageFont.truetype(path, size) if path else ImageFont.load_default()


# Pre-built fonts used across screens
F_CLOCK  = font("thin",   150)   # ambient HH:MM hero
F_CLOCK_S = font("light",  42)   # ambient seconds (smaller, trailing)
F_CLOCK2 = font("thin",   34)    # small clock (in radio/timer headers)
F_DATE   = font("light",  26)
F_TEMP   = font("light",  30)
F_TITLE  = font("medium", 24)
F_LABEL  = font("medium", 19)
F_BODY   = font("light",  20)
F_SMALL  = font("reg",    15)
F_RING   = font("thin",   58)    # timer countdown digits


# ── Colour helpers ──────────────────────────────────────────────────────────
def mix(a, b, t: float):
    """Linear blend between two RGB tuples (t: 0→a, 1→b)."""
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def dim(color, f: float):
    f = max(0.0, min(1.0, f))
    return tuple(int(c * f) for c in color)


def lighten(color, f: float):
    """Blend a colour toward white by f (0→color, 1→white)."""
    f = max(0.0, min(1.0, f))
    return tuple(int(c + (255 - c) * f) for c in color)


# ── Elevation: cached soft drop-shadow sprites ───────────────────────────────
# A blurred shadow under each card is the single biggest "product vs DIY" cue,
# but a GaussianBlur per frame is far too expensive on the Pi. Sprites are keyed
# on (w, h, radius) and built once — menus/sub-screens reuse them every frame.
_shadow_cache: dict = {}


def _shadow(w: int, h: int, radius: int, blur: int = 9, alpha: int = 120):
    key = (w, h, radius, blur, alpha)
    spr = _shadow_cache.get(key)
    if spr is None:
        pad = blur * 3
        mask = Image.new("L", (w + pad * 2, h + pad * 2), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [pad, pad, pad + w, pad + h], radius=radius, fill=alpha)
        mask = mask.filter(ImageFilter.GaussianBlur(blur))
        spr = (mask, pad)
        _shadow_cache[key] = spr
    return spr


def card(img, draw, box, radius=18, fill=CARD, elevate=True,
         bevel=True, edge=HAIRLINE):
    """A filled, raised surface — the building block for every panel.

    Replaces the old accent-outlined boxes: depth comes from a soft shadow,
    a neutral hairline edge, and a faint top bevel — never a coloured border.
    """
    x0, y0, x1, y1 = (int(v) for v in box)
    if elevate:
        mask, pad = _shadow(x1 - x0, y1 - y0, radius)
        black = Image.new("RGB", mask.size, (0, 0, 0))
        img.paste(black, (x0 - pad, y0 - pad + 5), mask)   # offset down 5px
    draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=fill,
                           outline=edge, width=1)
    if bevel:
        draw.line([(x0 + radius, y0 + 1), (x1 - radius, y0 + 1)],
                  fill=lighten(fill, 0.11), width=1)


# ── Station icons (real broadcaster logos, see assets/radio/) ────────────────
_ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
_icon_cache: dict = {}


def station_icon(name: str, size: int):
    """Load a station logo tile as RGBA at `size`px. Cached; None if missing."""
    key = (name, size)
    if key not in _icon_cache:
        path = os.path.join(_ASSET_DIR, "radio", f"{name}.png")
        try:
            im = Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
        except Exception:
            im = None
        _icon_cache[key] = im
    return _icon_cache[key]


# ── Background (built once per accent, cached) ───────────────────────────────
_Y = np.linspace(0.0, 1.0, H, dtype=np.float32)[:, None, None]
_GRAD = (np.array(BG_TOP, np.float32)[None, None, :] * (1 - _Y)
         + np.array(BG_BOTTOM, np.float32)[None, None, :] * _Y)

_yy, _xx = np.mgrid[0:H, 0:W].astype(np.float32)
_RADIAL = np.exp(-(((_xx - CX) / 300.0) ** 2 + ((_yy - CY + 20) / 200.0) ** 2))

_bg_cache: dict = {}


def background(accent) -> Image.Image:
    """Dark vertical gradient + a soft accent glow behind the centre. Cached."""
    key = tuple(accent)
    img = _bg_cache.get(key)
    if img is None:
        arr = _GRAD + _RADIAL[:, :, None] * (np.array(accent, np.float32) * 0.10)
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
        _bg_cache[key] = img
    return img.copy()


# ── Draw helpers ─────────────────────────────────────────────────────────────
def text_size(draw: ImageDraw.ImageDraw, s: str, fnt) -> tuple[int, int]:
    bb = draw.textbbox((0, 0), s, font=fnt)
    return bb[2] - bb[0], bb[3] - bb[1]


def text_center(draw, cx, y, s, fnt, fill, anchor="ma"):
    """Draw horizontally centred at cx. anchor 'ma' = middle/ascender top."""
    draw.text((cx, y), s, font=fnt, fill=fill, anchor=anchor)


def rounded(draw, box, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


# ── RGB565 conversion (big-endian, ST7796S byte order) ───────────────────────
def to_rgb565(img: Image.Image) -> bytes:
    a = np.asarray(img, dtype=np.uint16)
    r = (a[:, :, 0] & 0xF8) << 8
    g = (a[:, :, 1] & 0xFC) << 3
    b = (a[:, :, 2]) >> 3
    return (r | g | b).astype(">u2").tobytes()
