"""
Visual theme — fonts, palette, per-state accent, and drawing helpers.

The whole UI is dark with a single accent colour that shifts with the voice
assistant state (idle → listening → processing → speaking → error). Keeping
the palette in one place makes every screen feel like one device.
"""

import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from config import (
    DISPLAY_WIDTH, DISPLAY_HEIGHT,
    STATE_IDLE, STATE_LISTENING, STATE_PROCESSING, STATE_SPEAKING, STATE_ERROR,
)

W, H = DISPLAY_WIDTH, DISPLAY_HEIGHT
CX, CY = W // 2, H // 2

# ── Palette ─────────────────────────────────────────────────────────────────
BG_TOP    = (10, 12, 20)     # subtle vertical gradient, top
BG_BOTTOM = (3,  4,  9)      # bottom (near black)
INK       = (236, 240, 248)  # primary text (warm white)
INK_DIM   = (150, 158, 176)  # secondary text
INK_FAINT = (84,  92, 110)   # tertiary / hairlines
CARD      = (22, 26, 38)     # raised surface
CARD_HI   = (32, 38, 54)     # raised surface, pressed/active

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
F_CLOCK_S = font("thin",  60)    # ambient seconds (smaller, trailing)
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
