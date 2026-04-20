"""
Display UI renderer — full-circle watchface with state animations.

Layout (240×240 round, r=119):
  Background: dark navy base + per-state animation (edge-weighted, fills full circle)
  Tick marks: r 103–115 (minute), 106–115 (hour), 102–115 (quarter)
  Analog hands: minute=84, hour=58, second=90
  Digital HH:MM: below center (bold)
  Date/state text: below digital time
  Volume dots: bottom-center row (8 segments)
  WiFi fan: top (12-o'clock area)
"""

import math
import os
import subprocess
from datetime import datetime

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from config import (
    DISPLAY_WIDTH, DISPLAY_HEIGHT, DISPLAY_CX, DISPLAY_CY,
    ACCENT_COLORS, STATE_IDLE, STATE_LISTENING, STATE_PROCESSING,
    STATE_SPEAKING, STATE_ERROR,
)

# ── Precomputed pixel grids ────────────────────────────────────────────
_Y, _X  = np.mgrid[0:DISPLAY_HEIGHT, 0:DISPLAY_WIDTH]
_DX     = (_X - DISPLAY_CX).astype(np.float32)
_DY     = (_Y - DISPLAY_CY).astype(np.float32)
_DIST   = np.sqrt(_DX**2 + _DY**2)
_ANGLE  = np.arctan2(_DY, _DX)
_CIRCLE = _DIST <= 119.0
# Animation weight: 0 near center → 1 at edges (keeps clock face readable)
_EDGE   = np.clip((_DIST - 25.0) / 75.0, 0.0, 1.0)


# ── Fonts ──────────────────────────────────────────────────────────────
_FONT_BOLD_PATHS = [
    "/usr/share/fonts/truetype/roboto/Roboto-Bold.ttf",
    "/usr/share/fonts/truetype/roboto/hinted/Roboto-Bold.ttf",
    "/usr/share/fonts/google/roboto/Roboto-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    "/usr/share/fonts/truetype/ubuntu-font-family/Ubuntu-B.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
_FONT_REG_PATHS = [
    "/usr/share/fonts/truetype/roboto/Roboto-Regular.ttf",
    "/usr/share/fonts/truetype/roboto/hinted/Roboto-Regular.ttf",
    "/usr/share/fonts/google/roboto/Roboto-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
    "/usr/share/fonts/truetype/ubuntu-font-family/Ubuntu-R.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]

def _find_font(paths):
    for p in paths:
        if os.path.exists(p):
            return p
    return None

_FONT_SYM_TIMER_PATHS = [   # ⏱ U+23F1 — only in Symbols2
    "/usr/share/fonts/truetype/noto/NotoSansSymbols2-Regular.ttf",
]
_FONT_SYM_RADIO_PATHS = [   # ♪ U+266A — in Symbols and DejaVu
    "/usr/share/fonts/truetype/noto/NotoSansSymbols-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

_FP_BOLD      = _find_font(_FONT_BOLD_PATHS)
_FP_REG       = _find_font(_FONT_REG_PATHS)
_FP_SYM_TIMER = _find_font(_FONT_SYM_TIMER_PATHS)
_FP_SYM_RADIO = _find_font(_FONT_SYM_RADIO_PATHS)

def _load(path, size):
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default()

_FONT_TIME      = _load(_FP_BOLD, 42)
_FONT_DATE      = _load(_FP_REG,  16)
_FONT_SYM_TIMER = _load(_FP_SYM_TIMER or _FP_REG, 16)  # ⏱ — NotoSansSymbols2
_FONT_SYM_RADIO = _load(_FP_SYM_RADIO or _FP_REG, 16)  # ♪ — NotoSansSymbols/DejaVu

_JOURS = ["dim", "lun", "mar", "mer", "jeu", "ven", "sam"]
_MOIS  = ["jan", "fév", "mar", "avr", "mai", "jun",
          "jul", "aoû", "sep", "oct", "nov", "déc"]

STATE_TEXT = {
    STATE_LISTENING:  "Écoute...",
    STATE_PROCESSING: "Traitement...",
    STATE_SPEAKING:   "Parle...",
    STATE_ERROR:      "Erreur",
}


# ── Background animations (return float intensity array H×W) ──────────
# Each function returns values 0..1; _make_bg multiplies by accent color.
# _EDGE weighting pushes animation toward the display edge so the dark
# center stays readable.

def _bg_idle(step: int) -> np.ndarray:
    """Slow aurora rings — subtle, calm."""
    t     = step * 0.04
    rings = (np.sin(_DIST / 14.0 - t) + 1.0) * 0.5
    ang   = (np.sin(_ANGLE * 2.0 + t * 0.6) + 1.0) * 0.5 * 0.35 + 0.65
    fade  = np.clip(1.0 - _DIST / 132.0, 0.0, 1.0)
    return rings * ang * fade * 0.55 * _EDGE


def _bg_listening(step: int) -> np.ndarray:
    """Sonar ripples expanding from center."""
    t    = step * 0.22
    r1   = (np.sin(_DIST / 12.0 - t) + 1.0) * 0.5
    r2   = (np.sin(_DIST /  7.0 - t * 1.5) + 1.0) * 0.5
    fade = np.clip(1.0 - _DIST / 122.0, 0.0, 1.0) ** 0.5
    return (r1 * 0.6 + r2 * 0.4) * fade * 0.85


def _bg_processing(step: int) -> np.ndarray:
    """Clockwise radar sweep with fading trail."""
    t     = (step * 0.10) % (2.0 * math.pi)
    diff  = (_ANGLE - t + math.pi) % (2.0 * math.pi)
    trail = np.clip(1.0 - diff / (math.pi * 0.75), 0.0, 1.0) ** 1.5
    fade  = np.clip(1.0 - _DIST / 122.0, 0.0, 1.0)
    rings = (np.sin(_DIST / 18.0 - step * 0.03) + 1.0) * 0.5 * 0.14
    near  = np.clip(_DIST / 15.0, 0.0, 1.0)
    return (trail * fade * 0.90 + rings) * near


def _bg_speaking(step: int) -> np.ndarray:
    """Three Gaussian rings breathing at different phases."""
    t   = step * 0.16
    p1  = (np.sin(t) + 1.0) * 0.5
    p2  = (np.sin(t * 1.4 + 1.0) + 1.0) * 0.5
    p3  = (np.sin(t * 0.8 + 2.1) + 1.0) * 0.5
    sig = 8.0
    g1  = np.exp(-((_DIST - (35 + p1 * 30)) ** 2) / (2 * sig ** 2))
    g2  = np.exp(-((_DIST - (70 + p2 * 25)) ** 2) / (2 * sig ** 2))
    g3  = np.exp(-((_DIST - (100 + p3 * 15)) ** 2) / (2 * sig ** 2))
    return g1 * 0.90 + g2 * 0.75 + g3 * 0.60


def _bg_error(step: int) -> np.ndarray:
    """Rapid radial pulse with bright edge ring."""
    flash  = (np.sin(step * 0.45) + 1.0) * 0.5
    radial = np.clip(1.0 - _DIST / 122.0, 0.0, 1.0) ** 0.6
    ring   = np.exp(-((_DIST - 105) ** 2) / (2 * 6.0 ** 2)) * 0.90
    return (radial * 0.40 + ring) * (0.40 + flash * 0.60)


_BG_FN = {
    STATE_IDLE:       _bg_idle,
    STATE_LISTENING:  _bg_listening,
    STATE_PROCESSING: _bg_processing,
    STATE_SPEAKING:   _bg_speaking,
    STATE_ERROR:      _bg_error,
}


def _make_bg(step: int, state: int, accent: tuple) -> np.ndarray:
    intensity = _BG_FN.get(state, _bg_idle)(step)
    arr = np.empty((DISPLAY_HEIGHT, DISPLAY_WIDTH, 3), dtype=np.float32)
    # Dark navy base keeps text readable; animation adds state color on top
    arr[:, :, 0] = 3.0  + accent[0] * intensity
    arr[:, :, 1] = 5.0  + accent[1] * intensity
    arr[:, :, 2] = 12.0 + accent[2] * intensity
    np.clip(arr, 0, 255, out=arr)
    arr[~_CIRCLE] = 0
    return arr.astype(np.uint8)


# ── Drawing helpers ────────────────────────────────────────────────────

def _hand(draw, cx, cy, angle_deg, length, tail, width, color, tip_r=0):
    rad = math.radians(angle_deg - 90.0)
    cs, ss = math.cos(rad), math.sin(rad)
    x2, y2 = cx + length * cs, cy + length * ss
    x1, y1 = cx - tail   * cs, cy - tail   * ss
    draw.line([(int(x1), int(y1)), (int(x2), int(y2))], fill=color, width=width)
    if tip_r:
        draw.ellipse(
            [(int(x2) - tip_r, int(y2) - tip_r),
             (int(x2) + tip_r, int(y2) + tip_r)],
            fill=color,
        )


def _centered(draw, text, cx, y, font, color):
    bb = draw.textbbox((0, 0), text, font=font)
    draw.text((cx - (bb[2] - bb[0]) // 2, y), text, font=font, fill=color)


# ── Sensor helpers ─────────────────────────────────────────────────────

def _read_wifi_dbm() -> float:
    try:
        with open("/proc/net/wireless") as f:
            for line in f:
                if "wlan0" in line:
                    parts = line.split()
                    val = float(parts[3].rstrip("."))
                    return val if val < 0 else val - 100
    except Exception:
        pass
    return -100.0


def _read_volume_pct() -> int:
    try:
        out = subprocess.check_output(
            ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
            stderr=subprocess.DEVNULL, text=True,
        )
        for part in out.split():
            if part.endswith("%"):
                return int(part.rstrip("%"))
    except Exception:
        pass
    return 50


# ── RGB565 conversion ──────────────────────────────────────────────────

def to_rgb565(img: Image.Image) -> bytes:
    arr = np.array(img, dtype=np.uint8)
    r   = (arr[:, :, 0] >> 3).astype(np.uint16)
    g   = (arr[:, :, 1] >> 2).astype(np.uint16)
    b   = (arr[:, :, 2] >> 3).astype(np.uint16)
    return ((r << 11) | (g << 5) | b).astype(np.uint16).byteswap().tobytes()


# ── Main render ────────────────────────────────────────────────────────

_SCROLL_WINDOW = 16   # chars visible in the date-line slot


def _fmt_timer(remaining_s: int, name: str) -> str:
    m, s = divmod(max(0, remaining_s), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{name} {h}:{m:02d}:{s:02d}"
    return f"{name} {m}:{s:02d}"


def _scroll_text(full: str, offset: int) -> str:
    """Return a _SCROLL_WINDOW-wide slice of `full` looping at offset."""
    if len(full) <= _SCROLL_WINDOW:
        return full
    padded = full + "   "   # gap before loop-around
    loop = padded * 2
    pos = offset % len(padded)
    return loop[pos:pos + _SCROLL_WINDOW]


def media_scroll_text(title: str, artist: str) -> str:
    """Full string for radio scrolling (no icon — drawn separately)."""
    return f"{title} \u2013 {artist}" if artist else title


def _draw_icon_text(draw, icon: str, text: str, cx, y, color, icon_font):
    """Draw icon (symbol font) + text (regular font) centered as one unit."""
    ib = draw.textbbox((0, 0), icon + " ", font=icon_font)
    tb = draw.textbbox((0, 0), text,       font=_FONT_DATE)
    iw = ib[2] - ib[0]
    tw = tb[2] - tb[0]
    x0 = cx - (iw + tw) // 2
    # Align icon top to text top (different fonts have different ascent offsets)
    icon_y = y + (tb[1] - ib[1])
    draw.text((x0,      icon_y), icon + " ", font=icon_font,  fill=color)
    draw.text((x0 + iw, y),      text,       font=_FONT_DATE, fill=color)


def render_frame(step: int, state: int, now: datetime,
                 vol_pct: int, wifi_dbm: float,
                 ha_context: dict | None = None,
                 radio_offset: int = 0) -> bytes:
    cx, cy = DISPLAY_CX, DISPLAY_CY
    accent = ACCENT_COLORS.get(state, ACCENT_COLORS[STATE_IDLE])

    # ── Animated background (full circle, no inner mask) ─────────────
    img  = Image.fromarray(_make_bg(step, state, accent), "RGB")
    draw = ImageDraw.Draw(img)

    # ── Thin outer glow ring (state color) ───────────────────────────
    for r, alpha in [(119, 0.15), (118, 0.35), (117, 0.55), (116, 0.45)]:
        c = tuple(min(255, int(accent[i] * alpha + 20)) for i in range(3))
        draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], outline=c)

    # ── Tick marks (all 60 positions) ────────────────────────────────
    for m in range(60):
        if m % 15 == 0:             # quarter-hour: long + bright
            r_i, r_o, w = 102, 115, 3
            col = tuple(min(255, c + 100) for c in accent)
        elif m % 5 == 0:            # hour: medium
            r_i, r_o, w = 106, 115, 2
            col = (90, 115, 165)
        else:                       # minute: short + dim
            r_i, r_o, w = 111, 115, 1
            col = (35, 44, 62)
        rad = math.radians(m * 6.0 - 90.0)
        draw.line(
            [(int(cx + r_i * math.cos(rad)), int(cy + r_i * math.sin(rad))),
             (int(cx + r_o * math.cos(rad)), int(cy + r_o * math.sin(rad)))],
            fill=col, width=w,
        )

    # ── Clock hands ───────────────────────────────────────────────────
    frac = now.microsecond / 1_000_000
    ss   = now.second + frac
    sm   = now.minute + ss   / 60.0
    sh   = (now.hour % 12)  + sm / 60.0

    _hand(draw, cx, cy, sm * 6.0,  84, 10, 3, (215, 228, 255), tip_r=2)   # minute
    _hand(draw, cx, cy, sh * 30.0, 58, 10, 5, (245, 248, 255), tip_r=3)   # hour
    sec_col = tuple(min(255, c + 80) for c in accent) if state != STATE_IDLE else (255, 75, 50)
    _hand(draw, cx, cy, ss * 6.0,  90, 18, 1, sec_col)                     # second + tail

    # Centre cap
    draw.ellipse([(cx - 6, cy - 6), (cx + 6, cy + 6)], fill=(255, 255, 255))
    draw.ellipse([(cx - 3, cy - 3), (cx + 3, cy + 3)], fill=(8, 10, 20))

    # ── Digital HH:MM ─────────────────────────────────────────────────
    time_col = (
        tuple(min(255, c + 90) for c in accent)
        if state != STATE_IDLE else (160, 200, 255)
    )
    _centered(draw, now.strftime("%H:%M"), cx, cy + 20, _FONT_TIME, time_col)

    # ── State text, HA context, or date ──────────────────────────────
    # Ringing timers take priority over everything — stay visible even during
    # listening/processing so the user can say "+5 minutes"
    ringing = next(
        (t for t in (ha_context or {}).get("timers", []) if t.get("ringing")),
        None,
    )
    state_txt = STATE_TEXT.get(state)
    if ringing:
        # Urgent orange pulse + timer name + hint to extend
        pulse = int(220 + 35 * math.sin(step * 0.5))
        col   = (pulse, pulse // 3, 0)
        _draw_icon_text(draw, "\u23f1", ringing["name"], cx, cy + 58, col, _FONT_SYM_TIMER)
        hint_pulse = int(160 + 60 * math.sin(step * 0.4 + 1.0))
        _centered(draw, "+5 min ?", cx, cy + 76, _FONT_DATE, (hint_pulse, hint_pulse // 2, 0))
    elif state_txt:
        glow = int(190 + 65 * math.sin(step * 0.28))
        gc   = tuple(min(255, int(c * glow / 255)) for c in accent)
        _centered(draw, state_txt, cx, cy + 66, _FONT_DATE, gc)
    elif ha_context and ha_context.get("timers"):
        t     = ha_context["timers"][0]
        txt   = _fmt_timer(t["remaining_s"], t["name"])
        pulse = int(200 + 55 * math.sin(step * 0.20))
        _draw_icon_text(draw, "\u23f1", txt, cx, cy + 66, (pulse, pulse // 2, 30), _FONT_SYM_TIMER)
    elif ha_context and ha_context.get("media"):
        m    = ha_context["media"]
        full = media_scroll_text(m["title"], m["artist"])
        txt  = _scroll_text(full, radio_offset)
        _draw_icon_text(draw, "\u266a", txt, cx, cy + 66, (30, 180, 255), _FONT_SYM_RADIO)
    else:
        date_str = f"{_JOURS[now.weekday()]} {now.day:02d} {_MOIS[now.month - 1]}"
        _centered(draw, date_str, cx, cy + 66, _FONT_DATE, (50, 70, 105))

    # ── Volume indicator (8-dot row, bottom-center) ───────────────────
    # Centered at (cx, cy+90); 8 dots × 6px spacing = 42px wide
    active_dots = round(vol_pct / 100.0 * 8)
    for i in range(8):
        dx = cx - 21 + i * 6
        dy = cy + 90
        if i < active_dots:
            vc = tuple(min(255, int(c * 0.85) + 15) for c in accent)
        else:
            vc = (16, 19, 32)
        draw.ellipse([(dx - 2, dy - 2), (dx + 2, dy + 2)], fill=vc)

    # ── WiFi fan (top, 12-o'clock area) ──────────────────────────────
    wifi_arcs = (3 if wifi_dbm > -55 else
                 2 if wifi_dbm > -67 else
                 1 if wifi_dbm > -80 else 0)
    wx, wy = cx, cy - 85
    dot_c = (40, 110, 235) if wifi_arcs > 0 else (28, 30, 48)
    draw.ellipse([(wx - 1, wy - 1), (wx + 1, wy + 1)], fill=dot_c)
    for ai, r in enumerate([4, 7, 11]):
        arc_c = (
            tuple(min(255, int(c * 0.70)) for c in accent)
            if ai < wifi_arcs else (22, 24, 40)
        )
        for ang in range(-50, 51, 10):
            rad = math.radians(ang - 90.0)
            px  = wx + int(round(r * math.cos(rad)))
            py  = wy + int(round(r * math.sin(rad)))
            if 0 <= px < DISPLAY_WIDTH and 0 <= py < DISPLAY_HEIGHT:
                draw.point((px, py), fill=arc_c)

    return to_rgb565(img)
