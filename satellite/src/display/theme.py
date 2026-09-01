"""
Visual theme — fonts, palette, per-state accent, and drawing helpers.

The whole UI is dark with a single accent colour that shifts with the voice
assistant state (idle → listening → processing → speaking → error). Keeping
the palette in one place makes every screen feel like one device.
"""

import math
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
# Tuned for the actual ST7796S: it crushes everything below ~8/255 into one
# murky grey, so the background floor stays above that, and each elevation
# step is wider than a good monitor would need.
BG_TOP    = (16, 19, 30)     # subtle vertical gradient, top
BG_BOTTOM = (7,  9, 16)      # bottom (dark, but above the panel's crush point)
INK       = (240, 244, 252)  # primary text (warm white)
INK_DIM   = (162, 170, 189)  # secondary text
INK_FAINT = (95, 103, 124)   # tertiary text
HAIRLINE  = (58,  66,  88)   # neutral card edge (NEVER accent) — defines surfaces
CARD      = (32, 37, 53)     # raised surface
CARD_HI   = (46, 53, 74)     # raised surface, pressed/active/selected

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
# The hero clock is Light, not Thin: at 1-2 px effective stroke, antialiasing
# on this low-contrast panel eats half the luminance of a Thin glyph.
F_CLOCK  = font("light",  150)   # ambient HH:MM hero
F_CLOCK_S = font("light",  42)   # ambient seconds (smaller, trailing)
F_CLOCK2 = font("light",  34)    # small clock (in radio/timer headers)
F_DATE   = font("light",  26)
F_TEMP   = font("light",  30)
F_TITLE  = font("medium", 24)
F_LABEL  = font("medium", 19)
F_BODY   = font("light",  20)
F_SMALL  = font("reg",    15)
F_RING   = font("light",  58)    # timer countdown digits
F_MICRO  = font("medium", 14)    # tracked uppercase micro-labels


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
        arr = _GRAD + _RADIAL[:, :, None] * (np.array(accent, np.float32) * 0.15)
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
        _bg_cache[key] = img
    return img.copy()


# ── Draw helpers ─────────────────────────────────────────────────────────────
def text_size(draw: ImageDraw.ImageDraw, s: str, fnt) -> tuple[int, int]:
    bb = draw.textbbox((0, 0), s, font=fnt)
    return bb[2] - bb[0], bb[3] - bb[1]


def tracked_width(draw, s: str, fnt, tracking: float) -> float:
    return sum(draw.textlength(c, font=fnt) + tracking for c in s) - tracking


def text_tracked(draw, cx, y, s, fnt, fill, tracking=3.0):
    """Uppercase letterspaced micro-label, centred at cx — the typographic cue
    that separates a product from a hobby screen. Draw per-glyph; PIL has no
    tracking of its own."""
    s = s.upper()
    x = cx - tracked_width(draw, s, fnt, tracking) / 2
    for c in s:
        draw.text((x, y), c, font=fnt, fill=fill)
        x += draw.textlength(c, font=fnt) + tracking


_hero_grad_cache: dict = {}


def hero_text(img, xy, s, fnt, top, bottom, anchor="ls"):
    """Text filled with a vertical gradient (top→bottom colour), Apple-watch
    style. Renders the glyphs to a mask and pastes a cached gradient through
    it — a few ms on the Pi, and the hero clock renders at most 2 Hz."""
    d = ImageDraw.Draw(img)
    bb = d.textbbox(xy, s, font=fnt, anchor=anchor)
    x0, y0, x1, y1 = (int(math.floor(bb[0])), int(math.floor(bb[1])),
                      int(math.ceil(bb[2])), int(math.ceil(bb[3])))
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return
    key = (w, h, top, bottom)
    grad = _hero_grad_cache.get(key)
    if grad is None:
        yy = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None, None]
        arr = (np.array(top, np.float32) * (1 - yy)
               + np.array(bottom, np.float32) * yy)
        grad = Image.fromarray(np.broadcast_to(
            arr.astype(np.uint8), (h, w, 3)).copy(), "RGB")
        _hero_grad_cache[key] = grad
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((xy[0] - x0, xy[1] - y0), s, font=fnt,
                              fill=255, anchor=anchor)
    img.paste(grad, (x0, y0), mask)


def text_center(draw, cx, y, s, fnt, fill, anchor="ma"):
    """Draw horizontally centred at cx. anchor 'ma' = middle/ascender top."""
    draw.text((cx, y), s, font=fnt, fill=fill, anchor=anchor)


def rounded(draw, box, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


# ── RGB565 conversion (big-endian, ST7796S byte order) ───────────────────────
# Ordered (Bayer 8×8) dithering before the 8→5/6-bit truncation. The dark
# background gradient spans only a handful of 5-bit levels, which bands
# visibly on the panel; the dither trades that for imperceptible noise.
# It is positional — keyed on absolute screen coords — so a pixel always
# converts to the same bytes no matter which dirty rectangle it arrives in.
_BAYER8 = np.array([
    [ 0, 32,  8, 40,  2, 34, 10, 42],
    [48, 16, 56, 24, 50, 18, 58, 26],
    [12, 44,  4, 36, 14, 46,  6, 38],
    [60, 28, 52, 20, 62, 30, 54, 22],
    [ 3, 35, 11, 43,  1, 33,  9, 41],
    [51, 19, 59, 27, 49, 17, 57, 25],
    [15, 47,  7, 39, 13, 45,  5, 37],
    [63, 31, 55, 23, 61, 29, 53, 21],
], dtype=np.int16)


def to_rgb565(img: Image.Image, origin=(0, 0)) -> bytes:
    """Convert to the panel's byte order. `origin` = the crop's top-left in
    screen coordinates (dirty-rect blits pass it to keep the dither aligned)."""
    a = np.asarray(img).astype(np.int16)
    h, w = a.shape[:2]
    x0, y0 = origin
    t = _BAYER8[np.ix_((np.arange(h) + y0) % 8, (np.arange(w) + x0) % 8)]
    r = (np.minimum(a[:, :, 0] + (t >> 3), 255) & 0xF8).astype(np.uint16) << 8
    g = (np.minimum(a[:, :, 1] + (t >> 4), 255) & 0xFC).astype(np.uint16) << 3
    b = np.minimum(a[:, :, 2] + (t >> 3), 255).astype(np.uint16) >> 3
    return (r | g | b).astype(">u2").tobytes()
