"""
Display UI — 480×320 "Horizon Rising" voice assistant

The waveform lives at the bottom of the screen, anchored like a horizon.
In idle it is a thin breathing band. On activation it rises upward, filling
the screen from below. A single `morph` float (0=idle, 1=active) drives
both the waveform geometry and all text cross-fades simultaneously.
"""

import math
import os
import re
import subprocess
from datetime import datetime

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from config import (
    DISPLAY_WIDTH, DISPLAY_HEIGHT,
    STATE_IDLE, STATE_LISTENING, STATE_PROCESSING,
    STATE_SPEAKING, STATE_ERROR,
)

# ── Geometry ──────────────────────────────────────────────────────────────
_CX = DISPLAY_WIDTH  // 2   # 240
_CY = DISPLAY_HEIGHT // 2   # 160

# ── Pre-computed pixel grids ──────────────────────────────────────────────
_Y_g = np.arange(DISPLAY_HEIGHT, dtype=np.float32)[:, np.newaxis]   # (H, 1)
_X_g = np.arange(DISPLAY_WIDTH,  dtype=np.float32)[np.newaxis, :]   # (1, W)

# Elliptical radial glow — 1.0 at screen centre, ~0 at corners
_RADIAL = np.exp(-(
    (_X_g - _CX) ** 2 / (220.0 ** 2) +
    (_Y_g - _CY) ** 2 / (140.0 ** 2)
))

# ── Colors ────────────────────────────────────────────────────────────────
_BG = (5, 5, 12)

_ACCENT = {
    STATE_IDLE:       (  0,  55, 140),  # muted deep blue
    STATE_LISTENING:  (  0, 190, 255),  # vivid cyan
    STATE_PROCESSING: (185,   0, 255),  # electric violet
    STATE_SPEAKING:   (  0, 255,  85),  # electric green
    STATE_ERROR:      (255,  35,   0),  # vivid orange-red
}

_BG_BASE   = np.array(_BG, dtype=np.float32)
_BG_RADIAL = {
    s: _RADIAL[:, :, np.newaxis] * np.array(list(c), dtype=np.float32)
    for s, c in _ACCENT.items()
}

_GLOW_INT = {
    STATE_IDLE:       0.35,
    STATE_LISTENING:  0.30,
    STATE_PROCESSING: 0.28,
    STATE_SPEAKING:   0.25,
    STATE_ERROR:      0.38,
}

# ── Gaussian glow constants ───────────────────────────────────────────────
_INV2_SCORE = 1.0 / (2.0 * 2.5 ** 2)    # σ_core = 2.5 px
_INV2_SGLOW = 1.0 / (2.0 * 14.0 ** 2)   # σ_glow = 14 px  (wide soft halo)

# ── French date strings ───────────────────────────────────────────────────
_DAY_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_MON_FR = {
    1: "jan", 2: "fév",  3: "mar",  4: "avr",
    5: "mai", 6: "juin", 7: "juil", 8: "août",
    9: "sep", 10: "oct", 11: "nov", 12: "déc",
}

_STATE_LABEL = {
    STATE_IDLE:       "",
    STATE_LISTENING:  "EN ÉCOUTE",
    STATE_PROCESSING: "RÉFLEXION",
    STATE_SPEAKING:   "EN PAROLE",
    STATE_ERROR:      "ERREUR",
}

# ── Fonts ─────────────────────────────────────────────────────────────────
def _find(*paths):
    for p in paths:
        if os.path.exists(p):
            return p
    return None

_F_BOLD = _find(
    "/usr/share/fonts/truetype/roboto/Roboto-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)
_F_REG = _find(
    "/usr/share/fonts/truetype/roboto/Roboto-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)
_F_MONO = _find(
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
)

def _font(path, size):
    return ImageFont.truetype(path, size) if path else ImageFont.load_default()

_FONT_CLOCK = _font(_F_MONO, 96)   # idle hero
_FONT_TSML  = _font(_F_MONO, 20)   # active small clock
_FONT_DATE  = _font(_F_REG,  19)   # idle date
_FONT_STATE = _font(_F_BOLD, 20)   # active state label
_FONT_MEDIA = _font(_F_REG,  14)   # media / timer text
_FONT_STAT  = _font(_F_REG,  12)   # status corners


# ── Helpers ───────────────────────────────────────────────────────────────
def to_rgb565(img: Image.Image) -> bytes:
    a = np.array(img, dtype=np.uint16)
    r, g, b = a[:, :, 0] >> 3, a[:, :, 1] >> 2, a[:, :, 2] >> 3
    return ((r << 11) | (g << 5) | b).astype(np.uint16).byteswap().tobytes()


def _centered(draw, text, cx, y, font, color):
    bb = draw.textbbox((0, 0), text, font=font)
    draw.text((cx - (bb[2] - bb[0]) // 2, y), text, font=font, fill=color)


def _right_aligned(draw, text, x_right, y, font, color):
    bb = draw.textbbox((0, 0), text, font=font)
    draw.text((x_right - (bb[2] - bb[0]), y), text, font=font, fill=color)


def _tint(color, f: float):
    f = max(0.0, min(1.0, f))
    return tuple(int(c * f) for c in color)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * max(0.0, min(1.0, t))


def _read_wifi_dbm() -> int | None:
    try:
        out = subprocess.check_output(
            ["iwconfig", "wlan0"], stderr=subprocess.DEVNULL, text=True, timeout=2
        )
        m = re.search(r"Signal level=(-\d+)", out)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def _wifi_dot(dbm) -> str:
    if dbm is None:   return "?"
    if dbm >= -70:    return "●"
    if dbm >= -80:    return "◐"
    return "○"


def media_scroll_text(title: str, artist: str) -> str:
    return f"{title} — {artist}" if artist else title


def _pulse(state: int, step: int) -> float:
    t = step * 0.1
    if state == STATE_IDLE:       return 0.22 + 0.08 * math.sin(t * 0.30)
    if state == STATE_LISTENING:  return 0.72 + 0.26 * math.sin(t * 2.00)
    if state == STATE_PROCESSING: return 0.55 + 0.25 * math.sin(t * 1.50)
    if state == STATE_SPEAKING:   return 0.60 + 0.20 * math.sin(t * 0.80)
    if state == STATE_ERROR:      return 0.90 if (step % 8) < 4 else 0.25
    return 0.20


# ── Waveform patterns ─────────────────────────────────────────────────────
def _wave_y(state: int, step: int) -> np.ndarray:
    """Normalized per-pixel amplitude (0–1), shape (W,)."""
    x = np.linspace(0.0, 2.0 * math.pi, DISPLAY_WIDTH, dtype=np.float32)
    t = float(step) * 0.1

    if state == STATE_IDLE:
        y = (0.075
             + 0.025 * np.sin(x * 1.50 + t * 0.17)
             + 0.018 * np.sin(x * 2.31 + t * 0.29)
             + 0.010 * np.sin(x * 3.77 - t * 0.11))

    elif state == STATE_LISTENING:
        env = 0.5 + 0.5 * abs(math.sin(t * 0.55))
        y = env * (
            0.50 * np.sin(x * 2  + t * 2.40) +
            0.30 * np.sin(x * 5  - t * 3.10) +
            0.15 * np.sin(x * 9  + t * 4.70) +
            0.08 * np.sin(x * 17 - t * 6.50)
        )

    elif state == STATE_PROCESSING:
        y = 0.55 * np.sin(x * 3 - t * 2.8) * (0.5 + 0.5 * np.cos(x - t * 0.3))

    elif state == STATE_SPEAKING:
        y = (0.55 * np.sin(x * 4  + t * 3.20) +
             0.30 * np.sin(x * 9  - t * 2.50) +
             0.15 * np.sin(x * 15 + t * 5.10))

    elif state == STATE_ERROR:
        y = np.where(np.abs(np.sin(x * 16 - t * 8)) > 0.90, 0.80, 0.03)

    else:
        y = np.zeros(DISPLAY_WIDTH, dtype=np.float32)

    return np.clip(np.abs(y), 0.0, 1.0)


def _render_waveform(arr: np.ndarray, state: int, step: int,
                     anchor_y: float, max_h: float, fill_alpha: float):
    """
    Bottom-anchored waveform: the wave line rises *above* anchor_y.
    Asymmetric glow: brighter above the line (upward energy), dimmer below.
    Solid fill between wave line and anchor creates the 'rising water' zone.
    """
    accent = np.array(list(_ACCENT[state]), dtype=np.float32)
    yw = _wave_y(state, step) * max_h          # (W,) pixels above anchor
    wave_line = (anchor_y - yw)[np.newaxis, :] # (1, W)

    dist = _Y_g - wave_line                    # (H, W): neg=above line, pos=below

    above = (dist < 0).astype(np.float32)
    below = (dist >= 0).astype(np.float32)

    glow = (
        1.60 * np.exp(-dist ** 2 * _INV2_SCORE)         +   # tight core both sides
        0.55 * above * np.exp(-dist ** 2 * _INV2_SGLOW)  +   # soft halo above only
        0.10 * below * np.exp(-dist ** 2 * _INV2_SGLOW)      # dim halo below
    )

    fill = ((_Y_g >= wave_line) & (_Y_g <= anchor_y)).astype(np.float32) * fill_alpha

    arr += (glow + fill)[:, :, np.newaxis] * accent


# ── Text overlay (morph-driven single function) ───────────────────────────
def _draw_overlay(draw: ImageDraw.ImageDraw, now: datetime, state: int,
                  ha_ctx, radio_offset: int, vol_pct: int, wifi_dbm,
                  morph: float):
    accent = _ACCENT[state]

    # Opacity schedule
    clock_alpha  = max(0.0, 1.0 - morph * 1.5)           # big clock fades by morph=0.67
    date_alpha   = max(0.0, 1.0 - morph * 3.0)            # date fades by morph=0.33
    sml_alpha    = min(1.0, morph * 2.0) * 0.70           # small clock in by morph=0.5
    label_alpha  = max(0.0, (morph - 0.35) / 0.65)        # state label in after 0.35
    status_alpha = max(0.18, 1.0 - morph * 0.65)          # corners always present

    # ── Status corners (always rendered) ─────────────────────────────────
    draw.text((14, 8),  _wifi_dot(wifi_dbm), font=_FONT_STAT,
              fill=_tint(accent, status_alpha))
    draw.text((DISPLAY_WIDTH - 56, 8), f"{vol_pct}%", font=_FONT_STAT,
              fill=_tint(accent, status_alpha))

    # ── IDLE hero: large centred clock ────────────────────────────────────
    if clock_alpha > 0.01:
        _centered(draw, now.strftime("%H:%M:%S"), _CX, 75,
                  _FONT_CLOCK, _tint(accent, clock_alpha))

    # ── IDLE date ─────────────────────────────────────────────────────────
    if date_alpha > 0.01:
        date_str = f"{_DAY_FR[now.weekday()]} · {now.day} {_MON_FR[now.month]} {now.year}"
        _centered(draw, date_str, _CX, 207, _FONT_DATE, _tint(accent, date_alpha * 0.65))

    # ── ACTIVE: small clock top-left ──────────────────────────────────────
    if sml_alpha > 0.01:
        draw.text((14, 8), now.strftime("%H:%M:%S"), font=_FONT_TSML,
                  fill=_tint(accent, sml_alpha))

    # ── ACTIVE: state label top-right ─────────────────────────────────────
    if label_alpha > 0.01:
        _right_aligned(draw, _STATE_LABEL.get(state, ""), DISPLAY_WIDTH - 14, 8,
                       _FONT_STATE, _tint(accent, label_alpha))

    # ── Context bar (shown when active) ──────────────────────────────────
    if morph > 0.5:
        ctx_alpha = (morph - 0.5) * 2.0
        timers = (ha_ctx or {}).get("timers", [])
        media  = (ha_ctx or {}).get("media")

        if timers:
            s = timers[0]["remaining_s"]
            m, s = divmod(s, 60)
            h, m = divmod(m, 60)
            label = f"⏱  {h}h{m:02d}m{s:02d}" if h else f"⏱  {m}:{s:02d}"
            _centered(draw, label, _CX, 295, _FONT_MEDIA,
                      _tint(accent, ctx_alpha * 0.90))
        elif media:
            full   = media_scroll_text(media["title"], media.get("artist", ""))
            offset = radio_offset % max(1, len(full))
            txt    = "♪  " + (full + "   " + full)[offset:offset + 40]
            _centered(draw, txt, _CX, 295, _FONT_MEDIA,
                      _tint(accent, ctx_alpha * 0.75))

    # ── IDLE media scroll (when playing, morph < 0.5) ────────────────────
    elif morph < 0.5:
        media = (ha_ctx or {}).get("media")
        if media:
            idle_ctx_alpha = (1.0 - morph * 2) * 0.60
            full   = media_scroll_text(media["title"], media.get("artist", ""))
            offset = radio_offset % max(1, len(full))
            txt    = "♪  " + (full + "   " + full)[offset:offset + 36]
            _centered(draw, txt, _CX, 295, _FONT_MEDIA, _tint(accent, idle_ctx_alpha))


# ── Public API ────────────────────────────────────────────────────────────
def render_frame(step: int, state: int, now: datetime,
                 vol_pct: int, wifi_dbm, ha_ctx: dict | None,
                 radio_offset: int, morph: float = 0.0) -> bytes:

    p = _pulse(state, step)

    arr = _BG_BASE + _BG_RADIAL[state] * (_GLOW_INT[state] * p)

    # Waveform geometry driven by morph
    anchor_y   = _lerp(295.0, 190.0, morph)
    max_h      = _lerp(35.0,  138.0, morph)
    fill_alpha = _lerp(0.05,   0.22, morph)

    _render_waveform(arr, state, step, anchor_y, max_h, fill_alpha)

    img  = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    draw = ImageDraw.Draw(img)

    _draw_overlay(draw, now, state, ha_ctx, radio_offset, vol_pct, wifi_dbm, morph)

    return to_rgb565(img)
