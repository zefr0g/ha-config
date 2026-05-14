"""
Display UI — 480×320 modern voice assistant
Minimal, typography-first design with animated waveform feedback.

States:
  IDLE:   Hero clock (HH:MM + :SS), subtle waveform glow, date + status
  ACTIVE: Full waveform (listening/processing/speaking), top strip, context bar
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

# ── Geometry ─────────────────────────────────────────────────────────────
_CX    = DISPLAY_WIDTH  // 2   # 240
_CY    = DISPLAY_HEIGHT // 2   # 160

# Waveform height: subtle in idle, bold in active
_MAX_H_IDLE   = 18
_MAX_H_ACTIVE = 130

# ── Pre-computed pixel grids ──────────────────────────────────────────────
_Y_g = np.arange(DISPLAY_HEIGHT, dtype=np.float32)[:, np.newaxis]   # (H, 1)
_X_g = np.arange(DISPLAY_WIDTH,  dtype=np.float32)[np.newaxis, :]   # (1, W)

# Elliptical radial glow kernel — 1.0 at screen centre, ~0 at corners
_RADIAL = np.exp(-(
    (_X_g - _CX) ** 2 / (220.0 ** 2) +
    (_Y_g - _CY) ** 2 / (140.0 ** 2)
))  # (H, W)

# ── Colors ────────────────────────────────────────────────────────────────
_BG = (6, 6, 14)

_ACCENT = {
    STATE_IDLE:       (  0,  80, 160),
    STATE_LISTENING:  (  0, 160, 255),
    STATE_PROCESSING: (200,   0, 255),
    STATE_SPEAKING:   (  0, 240,  90),
    STATE_ERROR:      (255,  60,   0),
}

# Pre-cache per-state radial glow arrays
_BG_BASE   = np.array(_BG, dtype=np.float32)
_BG_RADIAL = {
    s: _RADIAL[:, :, np.newaxis] * np.array(list(c), dtype=np.float32)
    for s, c in _ACCENT.items()
}

# Glow intensity per state
_GLOW_INT = {
    STATE_IDLE:       0.50,
    STATE_LISTENING:  0.28,
    STATE_PROCESSING: 0.30,
    STATE_SPEAKING:   0.25,
    STATE_ERROR:      0.35,
}

# ── Gaussian glow constants ───────────────────────────────────────────────
_INV2_SCORE = 1.0 / (2.0 * 2.5 ** 2)   # σ_core = 2.5 px  (tight bright line)
_INV2_SGLOW = 1.0 / (2.0 * 12.0 ** 2)  # σ_glow = 12.0 px (wide soft halo)

# ── Labels / date strings ─────────────────────────────────────────────────
_STATE_LABEL = {
    STATE_IDLE:       "",
    STATE_LISTENING:  "EN ÉCOUTE",
    STATE_PROCESSING: "RÉFLEXION",
    STATE_SPEAKING:   "EN PAROLE",
    STATE_ERROR:      "ERREUR",
}

_DAY_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_MON_FR = {
    1: "jan", 2: "fév",  3: "mar",  4: "avr",
    5: "mai", 6: "juin", 7: "juil", 8: "août",
    9: "sep", 10: "oct", 11: "nov", 12: "déc",
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

# Typography: typography-first design
_FONT_CLOCK = _font(_F_MONO, 96)   # IDLE: hero clock HH:MM
_FONT_SECS  = _font(_F_MONO, 36)   # IDLE: small seconds :SS
_FONT_DATE  = _font(_F_REG,  19)   # IDLE: date below clock
_FONT_TSML  = _font(_F_MONO, 20)   # ACTIVE: small clock top-left
_FONT_STATE = _font(_F_BOLD, 20)   # ACTIVE: state label top-right
_FONT_MEDIA = _font(_F_REG,  14)   # media / radio text
_FONT_STAT  = _font(_F_REG,  12)   # status: wifi + volume (top corners)


# ── Helpers ───────────────────────────────────────────────────────────────
def to_rgb565(img: Image.Image) -> bytes:
    a = np.array(img, dtype=np.uint16)
    r, g, b = a[:, :, 0] >> 3, a[:, :, 1] >> 2, a[:, :, 2] >> 3
    return ((r << 11) | (g << 5) | b).astype(np.uint16).byteswap().tobytes()


def _centered(draw, text, cx, y, font, color):
    bb = draw.textbbox((0, 0), text, font=font)
    draw.text((cx - (bb[2] - bb[0]) // 2, y), text, font=font, fill=color)


def _tint(color, f):
    return tuple(min(255, int(c * f)) for c in color)


def _read_wifi_dbm() -> int | None:
    try:
        out = subprocess.check_output(
            ["iwconfig", "wlan0"], stderr=subprocess.DEVNULL, text=True, timeout=2
        )
        m = re.search(r"Signal level=(-\d+)", out)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def _wifi_indicator(dbm) -> str:
    """Return wifi status as single character: ● (good) / ◐ (weak) / ○ (poor)."""
    if dbm is None:
        return "?"
    if dbm >= -70:
        return "●"
    if dbm >= -80:
        return "◐"
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
    """Per-pixel waveform amplitude, shape (W,), always non-negative, in px."""
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


def _render_waveform(arr: np.ndarray, state: int, step: int, max_h: float):
    """Add gaussian glow waveform to float32 frame array in-place."""
    accent = np.array(list(_ACCENT[state]), dtype=np.float32)
    y_norm = _wave_y(state, step)             # (W,), normalized 0–1
    yw     = y_norm * max_h                   # (W,), scaled by max_h

    wave_up = (_CY - yw)[np.newaxis, :]      # (1, W)  upper line y-coords
    wave_dn = (_CY + yw)[np.newaxis, :]      # (1, W)  lower mirror y-coords

    dist_up = _Y_g - wave_up                 # (H, W)
    dist_dn = _Y_g - wave_dn                 # (H, W)

    # Four gaussian layers: bright core + wide halo, for each line
    glow = (
        1.50 * np.exp(-dist_up ** 2 * _INV2_SCORE) +  # upper core
        0.40 * np.exp(-dist_up ** 2 * _INV2_SGLOW) +  # upper halo
        0.12 * np.exp(-dist_dn ** 2 * _INV2_SCORE) +  # mirror core (dimmer)
        0.05 * np.exp(-dist_dn ** 2 * _INV2_SGLOW)    # mirror halo (subtler)
    )  # (H, W)

    # Subtle fill between upper wave and baseline
    fill  = ((_Y_g >= wave_up) & (_Y_g <= _CY)).astype(np.float32) * 0.07
    fill += ((_Y_g >= _CY)     & (_Y_g <= wave_dn)).astype(np.float32) * 0.03

    arr += (glow + fill)[:, :, np.newaxis] * accent


# ── Text overlays ─────────────────────────────────────────────────────────
def _draw_idle(draw: ImageDraw.ImageDraw, now: datetime, state: int,
               ha_ctx, radio_offset: int, vol_pct: int, wifi_dbm):
    """IDLE: hero clock + date, subtle waveform at bottom, simple status."""
    accent = _ACCENT[state]

    # Top strip: wifi dot (top-left) + volume % (top-right)
    wifi_char = _wifi_indicator(wifi_dbm)
    draw.text((18, 8), wifi_char, font=_FONT_STAT, fill=_tint(accent, 0.5))
    draw.text((DISPLAY_WIDTH - 60, 8), f"{vol_pct}%", font=_FONT_STAT, fill=_tint(accent, 0.5))

    # Hero: HH:MM centred, large
    hm = now.strftime("%H:%M")
    _centered(draw, hm, _CX, 50, _FONT_CLOCK, accent)

    # Seconds: :SS below-right of the clock
    ss = now.strftime(":%S")
    bb = draw.textbbox((0, 0), hm, font=_FONT_CLOCK)
    clock_width = bb[2] - bb[0]
    ss_x = _CX + (clock_width // 2) - 20  # Align near the right edge of HH:MM
    draw.text((ss_x, 160), ss, font=_FONT_SECS, fill=_tint(accent, 0.65))

    # Date: below clock
    date_str = f"{_DAY_FR[now.weekday()]} · {now.day} {_MON_FR[now.month]} {now.year}"
    _centered(draw, date_str, _CX, 245, _FONT_DATE, _tint(accent, 0.65))

    # Media or empty space at bottom
    media = (ha_ctx or {}).get("media")
    if media:
        full   = media_scroll_text(media["title"], media.get("artist", ""))
        offset = radio_offset % max(1, len(full))
        txt    = "♪  " + (full + "   " + full)[offset:offset + 36]
        _centered(draw, txt, _CX, 300, _FONT_MEDIA, _tint(accent, 0.55))


def _draw_active(draw: ImageDraw.ImageDraw, now: datetime, state: int,
                 ha_ctx, radio_offset: int, vol_pct: int, wifi_dbm):
    """ACTIVE: top strip (clock + state), big waveform, bottom context bar."""
    accent = _ACCENT[state]

    # Top strip: clock left, state label right
    draw.text((12, 8), now.strftime("%H:%M"), font=_FONT_TSML, fill=_tint(accent, 0.6))
    _centered(draw, _STATE_LABEL[state], DISPLAY_WIDTH - 100, 8, _FONT_STATE, accent)

    # Bottom context bar: timer > media > empty
    timers = (ha_ctx or {}).get("timers", [])
    media  = (ha_ctx or {}).get("media")

    if timers:
        s = timers[0]["remaining_s"]
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        label = f"⏱  {h}h{m:02d}m{s:02d}" if h else f"⏱  {m}:{s:02d}"
        _centered(draw, label, _CX, 295, _FONT_MEDIA, _tint(accent, 0.85))
    elif media:
        full   = media_scroll_text(media["title"], media.get("artist", ""))
        offset = radio_offset % max(1, len(full))
        txt    = "♪  " + (full + "   " + full)[offset:offset + 38]
        _centered(draw, txt, _CX, 295, _FONT_MEDIA, _tint(accent, 0.72))


# ── Public API ────────────────────────────────────────────────────────────
def render_frame(step: int, state: int, now: datetime,
                 vol_pct: int, wifi_dbm, ha_ctx: dict | None,
                 radio_offset: int) -> bytes:

    p = _pulse(state, step)

    # Background: pre-cached per-state glow, scaled by pulse
    arr = _BG_BASE + _BG_RADIAL[state] * (_GLOW_INT[state] * p)

    # Waveform: idle=subtle, active=bold
    max_h = _MAX_H_IDLE if state == STATE_IDLE else _MAX_H_ACTIVE
    _render_waveform(arr, state, step, max_h)

    # Clip → PIL → text
    img  = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    draw = ImageDraw.Draw(img)

    if state == STATE_IDLE:
        _draw_idle(draw, now, state, ha_ctx, radio_offset, vol_pct, wifi_dbm)
    else:
        _draw_active(draw, now, state, ha_ctx, radio_offset, vol_pct, wifi_dbm)

    return to_rgb565(img)
