"""
Display UI renderer — ambient voice-assistant watchfaces.

Three original variations (pick one via `VARIATION` env var or the constant):

  VARIATION = "aurora"  — liquid gradient field, hue shifts by state
  VARIATION = "ember"   — breathing warm orb at center
  VARIATION = "signal"  — mono slate + single signal color, fluid waveform band

All three render into a 240×240 round GC9A01 at ~10 FPS. Peripheral info
(WiFi, volume, timer, radio, date) is preserved; French state labels kept.

Drop-in replacement for the previous ui.py. `render_frame(...)` and the
helpers `_read_wifi_dbm()`, `_read_volume_pct()`, `media_scroll_text(...)`
keep the same signatures used by the display daemon.
"""

import math
import os
import re
import subprocess
from datetime import datetime

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from config import (
    DISPLAY_WIDTH, DISPLAY_HEIGHT, DISPLAY_CX, DISPLAY_CY,
    STATE_IDLE, STATE_LISTENING, STATE_PROCESSING,
    STATE_SPEAKING, STATE_ERROR,
)

_VARIATION_FILE = "/tmp/va_watchface"
_VARIATION_DEFAULT = os.environ.get("VA_WATCHFACE", "aurora").lower()
_VALID_VARIATIONS = {"aurora", "ember", "signal"}


def _get_variation() -> str:
    try:
        v = open(_VARIATION_FILE).read().strip().lower()
        if v in _VALID_VARIATIONS:
            return v
    except OSError:
        pass
    return _VARIATION_DEFAULT

# ── Precomputed pixel grids ────────────────────────────────────────────
_Y, _X  = np.mgrid[0:DISPLAY_HEIGHT, 0:DISPLAY_WIDTH]
_DX     = (_X - DISPLAY_CX).astype(np.float32)
_DY     = (_Y - DISPLAY_CY).astype(np.float32)
_DIST   = np.sqrt(_DX ** 2 + _DY ** 2)
_ANGLE  = np.arctan2(_DY, _DX)
_CIRCLE = _DIST <= 119.0

# Edge falloff used by several variations (0 at center, 1 at rim).
_EDGE   = np.clip((_DIST - 25.0) / 80.0, 0.0, 1.0)


# ── Fonts ──────────────────────────────────────────────────────────────
_FONT_BOLD_PATHS = [
    "/usr/share/fonts/truetype/roboto/Roboto-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
_FONT_REG_PATHS = [
    "/usr/share/fonts/truetype/roboto/Roboto-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]
_FONT_LIGHT_PATHS = [
    "/usr/share/fonts/truetype/roboto/Roboto-Light.ttf",
    "/usr/share/fonts/truetype/roboto/Roboto-Thin.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
_FONT_MONO_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
]
_FONT_SYM_TIMER_PATHS = ["/usr/share/fonts/truetype/noto/NotoSansSymbols2-Regular.ttf"]
_FONT_SYM_RADIO_PATHS = [
    "/usr/share/fonts/truetype/noto/NotoSansSymbols-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _find(paths):
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def _load(path, size):
    return ImageFont.truetype(path, size) if path else ImageFont.load_default()


_FP_BOLD  = _find(_FONT_BOLD_PATHS)
_FP_REG   = _find(_FONT_REG_PATHS)
_FP_LIGHT = _find(_FONT_LIGHT_PATHS)
_FP_MONO  = _find(_FONT_MONO_PATHS)
_FP_T     = _find(_FONT_SYM_TIMER_PATHS)
_FP_R     = _find(_FONT_SYM_RADIO_PATHS)

_FONT_TIME_L  = _load(_FP_LIGHT or _FP_REG,  40)   # Aurora/Signal large digital
_FONT_TIME_M  = _load(_FP_BOLD,               26)  # Ember compact digital
_FONT_LABEL   = _load(_FP_REG,                13)
_FONT_LABEL_S = _load(_FP_MONO or _FP_REG,    11)
_FONT_TINY    = _load(_FP_REG,                11)
_FONT_DATE    = _load(_FP_REG,                12)
_FONT_SYM_T   = _load(_FP_T or _FP_REG,       14)
_FONT_SYM_R   = _load(_FP_R or _FP_REG,       14)


_JOURS = ["dim", "lun", "mar", "mer", "jeu", "ven", "sam"]
_MOIS  = ["jan", "fév", "mar", "avr", "mai", "jun",
          "jul", "aoû", "sep", "oct", "nov", "déc"]

STATE_TEXT = {
    STATE_LISTENING:  "Écoute...",
    STATE_PROCESSING: "Traitement...",
    STATE_SPEAKING:   "Parle...",
    STATE_ERROR:      "Erreur",
}


# ── Sensor helpers ─────────────────────────────────────────────────────
def _read_wifi_dbm() -> float:
    try:
        with open("/proc/net/wireless") as f:
            for line in f:
                if "wlan0" in line:
                    val = float(line.split()[3].rstrip("."))
                    return val if val < 0 else val - 100
    except Exception:
        pass
    return -100.0


def _read_volume_pct() -> int:
    try:
        out = subprocess.check_output(
            ["amixer", "get", "Master"],
            stderr=subprocess.DEVNULL, text=True,
        )
        m = re.search(r"\[(\d+)%\]", out)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return 50


# ── RGB565 ─────────────────────────────────────────────────────────────
def to_rgb565(img: Image.Image) -> bytes:
    arr = np.array(img, dtype=np.uint8)
    r = (arr[:, :, 0] >> 3).astype(np.uint16)
    g = (arr[:, :, 1] >> 2).astype(np.uint16)
    b = (arr[:, :, 2] >> 3).astype(np.uint16)
    return ((r << 11) | (g << 5) | b).astype(np.uint16).byteswap().tobytes()


# ── Scrolling text ─────────────────────────────────────────────────────
_SCROLL_WINDOW = 16


def _fmt_timer(remaining_s: int, name: str) -> str:
    m, s = divmod(max(0, remaining_s), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{name} {h}:{m:02d}:{s:02d}"
    return f"{name} {m}:{s:02d}"


def _scroll(full: str, offset: int) -> str:
    if len(full) <= _SCROLL_WINDOW:
        return full
    padded = full + "   "
    pos = offset % len(padded)
    return (padded * 2)[pos:pos + _SCROLL_WINDOW]


def media_scroll_text(title: str, artist: str) -> str:
    return f"{title} \u2013 {artist}" if artist else title


def _centered(draw, text, cx, y, font, color):
    bb = draw.textbbox((0, 0), text, font=font)
    draw.text((cx - (bb[2] - bb[0]) // 2, y), text, font=font, fill=color)


# ── Per-state palettes per variation ───────────────────────────────────
AURORA = {
    # (hue_deg, sat_frac, lightness_frac) for the primary gradient
    STATE_IDLE:       (205, 0.55, 0.42),
    STATE_LISTENING:  (175, 0.80, 0.48),
    STATE_PROCESSING: (260, 0.70, 0.50),
    STATE_SPEAKING:   (140, 0.75, 0.48),
    STATE_ERROR:      ( 10, 0.85, 0.52),
}

EMBER = {
    # core RGB, outer RGB
    STATE_IDLE:       ((255, 180,  90), (180,  70,  30)),
    STATE_LISTENING:  ((255, 230, 130), (220, 140,  40)),
    STATE_PROCESSING: ((255, 140, 200), (180,  60, 140)),
    STATE_SPEAKING:   ((140, 230, 180), ( 50, 160, 120)),
    STATE_ERROR:      ((255,  90,  70), (190,  30,  20)),
}

SIGNAL = {
    STATE_IDLE:       (100, 116, 139),   # slate-500
    STATE_LISTENING:  ( 34, 211, 238),   # cyan-400
    STATE_PROCESSING: (167, 139, 250),   # violet-400
    STATE_SPEAKING:   ( 74, 222, 128),   # green-400
    STATE_ERROR:      (248, 113, 113),   # red-400
}


def _hsl_to_rgb(h_deg, s, l):
    """Return (r,g,b) 0-255 floats. h_deg in [0,360], s/l in [0,1]."""
    c = (1 - abs(2 * l - 1)) * s
    h = (h_deg % 360) / 60.0
    x = c * (1 - abs((h % 2) - 1))
    if   h < 1: r, g, b = c, x, 0
    elif h < 2: r, g, b = x, c, 0
    elif h < 3: r, g, b = 0, c, x
    elif h < 4: r, g, b = 0, x, c
    elif h < 5: r, g, b = x, 0, c
    else:       r, g, b = c, 0, x
    m = l - c / 2
    return (r + m) * 255, (g + m) * 255, (b + m) * 255


# ── V1: Aurora ─────────────────────────────────────────────────────────
# Three moving radial gaussians at state-hue, additive, then vignette.
def _bg_aurora(step: int, state: int) -> np.ndarray:
    h0, sat, lit = AURORA.get(state, AURORA[STATE_IDLE])
    amp = {STATE_LISTENING: 1.3, STATE_PROCESSING: 1.1, STATE_ERROR: 1.6}.get(state, 0.95)

    # State-driven breath: calm at idle, dramatic otherwise
    profile = {
        STATE_IDLE:       (0.09, 1.0, 1.0, 1.0),
        STATE_LISTENING:  (0.22, 1.8, 1.5, 1.4),
        STATE_PROCESSING: (0.17, 1.6, 1.3, 1.6),
        STATE_SPEAKING:   (0.28, 2.0, 1.7, 1.3),
        STATE_ERROR:      (0.40, 2.2, 1.9, 1.8),
    }.get(state, (0.09, 1.0, 1.0, 1.0))
    rate, rK, aK, dK = profile

    t = step * 0.012
    breath_raw = math.sin(step * rate)
    breath = 0.5 + 0.5 * breath_raw
    bs = breath_raw

    out = np.zeros((DISPLAY_HEIGHT, DISPLAY_WIDTH, 3), dtype=np.float32)

    blob_specs = [
        (  0,
         (math.cos(0.9 * t) * 55 + math.sin(0.31 * t) * 20) * dK + bs * 10 * dK,
         (math.sin(1.1 * t) * 45 + math.cos(0.23 * t) * 22) * dK - bs * 8 * dK,
         55.0 + breath * 27 * rK,
         0.55 + breath * 0.55 * aK),
        ( 30,
         (math.cos(1.3 * t + 2.0) * 62 + math.sin(0.41 * t + 1.1) * 18) * dK - bs * 12 * dK,
         (math.sin(0.8 * t + 1.0) * 56 + math.cos(0.27 * t + 2.3) * 20) * dK + bs * 10 * dK,
         80.0 - breath * 27 * rK,
         1.10 - breath * 0.55 * aK),
        (-25,
         (math.cos(0.7 * t + 4.0) * 50 + math.sin(0.37 * t + 3.1) * 22) * dK,
         (math.sin(1.4 * t + 3.0) * 54 + math.cos(0.19 * t + 0.8) * 26) * dK,
         60.0 + math.sin(step * 0.07 + 3.1) * 17 * rK,
         0.75 + math.sin(step * 0.06 + 2.0) * 0.35 * aK),
    ]

    for dh, ox, oy, rr, a_mul in blob_specs:
        cx = DISPLAY_CX + ox
        cy = DISPLAY_CY + oy
        d2 = (_X - cx) ** 2 + (_Y - cy) ** 2
        g  = np.exp(-d2 / (2.0 * rr * rr)) * amp * max(0.0, a_mul)
        r, gg, b = _hsl_to_rgb(h0 + dh, sat, lit)
        out[:, :, 0] += r * g
        out[:, :, 1] += gg * g
        out[:, :, 2] += b * g

    # Vignette darkening toward center (keeps digital time readable)
    center_mask = np.exp(-(_DIST ** 2) / (2.0 * 55.0 ** 2)) * 0.75
    out *= (1.0 - center_mask)[:, :, None]

    np.clip(out, 0, 255, out=out)
    out[~_CIRCLE] = 0
    return out.astype(np.uint8)


def _render_aurora(img, draw, step, state, now, vol_pct, wifi_dbm, ha_ctx, radio_off):
    cx, cy = DISPLAY_CX, DISPLAY_CY
    h0, sat, lit = AURORA.get(state, AURORA[STATE_IDLE])
    r_a, g_a, b_a = _hsl_to_rgb(h0, sat, 0.70)
    accent = (int(r_a), int(g_a), int(b_a))
    dim    = (22, 26, 36)

    # Faint full ring + 12 tick marks
    for i in range(12):
        a = i / 12 * 2 * math.pi - math.pi / 2
        r1 = 107
        r2 = 100 if i % 3 == 0 else 104
        col = (120, 135, 160) if i % 3 == 0 else (55, 65, 85)
        w = 2 if i % 3 == 0 else 1
        draw.line(
            [(int(cx + r1 * math.cos(a)), int(cy + r1 * math.sin(a))),
             (int(cx + r2 * math.cos(a)), int(cy + r2 * math.sin(a)))],
            fill=col, width=w,
        )
    draw.ellipse([(cx - 113, cy - 113), (cx + 113, cy + 113)],
                 outline=(35, 40, 55), width=1)

    # Second-progress arc on rim (fills each minute) + leading glow dot
    s_frac = (now.second + now.microsecond / 1e6) / 60.0
    start_deg = -90
    end_deg   = start_deg + s_frac * 360
    draw.arc([(cx - 113, cy - 113), (cx + 113, cy + 113)],
             start=start_deg, end=end_deg, fill=accent, width=3)
    sa = s_frac * 2 * math.pi - math.pi / 2
    sx = int(cx + 113 * math.cos(sa))
    sy = int(cy + 113 * math.sin(sa))
    r_hi, g_hi, b_hi = _hsl_to_rgb(h0, sat, 0.88)
    glow = (int(r_hi), int(g_hi), int(b_hi))
    draw.ellipse([(sx - 4, sy - 4), (sx + 4, sy + 4)], fill=glow)
    draw.ellipse([(sx - 2, sy - 2), (sx + 2, sy + 2)], fill=(255, 255, 255))

    # Processing: rotating orbital arc (ember-style), inset from rim
    if state == STATE_PROCESSING:
        orb_r = 96
        start = (step * 7) % 360 - 180
        draw.arc(
            [(cx - orb_r, cy - orb_r), (cx + orb_r, cy + orb_r)],
            start=start, end=start + 200, fill=accent, width=3,
        )
        # trailing comet tip
        tip_a = math.radians(start + 200)
        tx = int(cx + orb_r * math.cos(tip_a))
        ty = int(cy + orb_r * math.sin(tip_a))
        draw.ellipse([(tx - 4, ty - 4), (tx + 4, ty + 4)], fill=glow)
        draw.ellipse([(tx - 2, ty - 2), (tx + 2, ty + 2)], fill=(255, 255, 255))

    # Digital time — low-center, light weight
    _centered(draw, now.strftime("%H:%M"), cx, cy - 24, _FONT_TIME_L,
              (232, 238, 250))

    # Secondary line: state / timer / media / date
    ringing = next(
        (t for t in (ha_ctx or {}).get("timers", []) if t.get("ringing")),
        None,
    )
    stxt = STATE_TEXT.get(state)
    y2 = cy + 22
    if ringing:
        pulse = int(220 + 35 * math.sin(step * 0.5))
        draw.text((cx, y2), "", font=_FONT_SYM_T)   # ensure loaded
        _centered(draw, f"\u23f1 {ringing['name']}  +5 min ?", cx, y2,
                  _FONT_LABEL, (pulse, pulse // 3, 0))
    elif stxt:
        pulse = 0.65 + 0.35 * (0.5 + 0.5 * math.sin(step * 0.18))
        col = tuple(min(255, int(c * pulse)) for c in accent)
        _centered(draw, stxt, cx, y2, _FONT_LABEL, col)
    elif ha_ctx and ha_ctx.get("timers"):
        t  = ha_ctx["timers"][0]
        tx = _fmt_timer(t["remaining_s"], t["name"])
        _centered(draw, f"\u23f1 {tx}", cx, y2, _FONT_LABEL, (255, 190, 110))
    elif ha_ctx and ha_ctx.get("media"):
        m  = ha_ctx["media"]
        tx = _scroll(media_scroll_text(m["title"], m["artist"]), radio_off)
        _centered(draw, f"\u266a {tx}", cx, y2, _FONT_LABEL, (120, 200, 255))
    else:
        _centered(draw, f"{_JOURS[now.weekday()]} {now.day:02d} {_MOIS[now.month - 1]}",
                  cx, y2, _FONT_DATE, (120, 135, 160))

    # WiFi fan — top
    _draw_wifi_fan(draw, cx, cy - 80, wifi_dbm, accent, dim)

    # Volume dots — bottom
    _draw_vol_dots(draw, cx, cy + 78, vol_pct, accent, dim)


# ── V2: Ember ──────────────────────────────────────────────────────────
def _bg_ember(step: int, state: int) -> np.ndarray:
    core, outer = EMBER.get(state, EMBER[STATE_IDLE])

    # Ambient warm bed + breathing central glow
    breath_rate = {
        STATE_LISTENING: 0.22, STATE_PROCESSING: 0.35,
        STATE_SPEAKING:  0.16, STATE_ERROR: 0.45,
    }.get(state, 0.08)
    breath = 0.5 + 0.5 * math.sin(step * breath_rate)
    orb_r = 32 + breath * 14

    # Ambient bed (outer color, very low)
    bed = np.exp(-(_DIST ** 2) / (2.0 * 95.0 ** 2)) * 0.18
    # Glow around orb
    glow = np.exp(-((_DIST - 0) ** 2) / (2.0 * (orb_r + 30) ** 2)) * 0.60
    # Orb core
    core_mask = np.clip(1.0 - _DIST / orb_r, 0, 1)

    out = np.zeros((DISPLAY_HEIGHT, DISPLAY_WIDTH, 3), dtype=np.float32)
    for ch in range(3):
        out[:, :, ch] = (
            bed  * outer[ch]
            + glow * (0.5 * core[ch] + 0.5 * outer[ch])
            + core_mask * (0.8 * core[ch] + 0.2 * 255)
        )

    # Speaking ripples
    if state == STATE_SPEAKING:
        for i in range(3):
            phase = (step * 0.04 + i / 3.0) % 1.0
            rr    = orb_r + 10 + phase * 70
            alpha = (1.0 - phase) * 0.35
            ring = np.exp(-((_DIST - rr) ** 2) / (2.0 * 4.0 ** 2)) * alpha
            for ch in range(3):
                out[:, :, ch] += ring * core[ch]

    np.clip(out, 0, 255, out=out)
    out[~_CIRCLE] = 0
    return out.astype(np.uint8)


def _render_ember(img, draw, step, state, now, vol_pct, wifi_dbm, ha_ctx, radio_off):
    cx, cy = DISPLAY_CX, DISPLAY_CY
    core, outer = EMBER.get(state, EMBER[STATE_IDLE])
    dim = (30, 20, 15)

    # Processing rotating arc around orb
    breath_rate = {
        STATE_LISTENING: 0.22, STATE_PROCESSING: 0.35,
        STATE_SPEAKING:  0.16, STATE_ERROR: 0.45,
    }.get(state, 0.08)
    breath = 0.5 + 0.5 * math.sin(step * breath_rate)
    orb_r  = 32 + breath * 14
    if state == STATE_PROCESSING:
        start  = (step * 7) % 360 - 180
        draw.arc(
            [(cx - (orb_r + 18), cy - (orb_r + 18)),
             (cx + (orb_r + 18), cy + (orb_r + 18))],
            start=start, end=start + 200, fill=core, width=2,
        )

    # Seconds: faint ring around orb + traveling dot
    rr = int(orb_r + 10)
    draw.ellipse([(cx - rr, cy - rr), (cx + rr, cy + rr)],
                 outline=(int(outer[0] * 0.5), int(outer[1] * 0.5),
                          int(outer[2] * 0.5)), width=1)
    s_frac = (now.second + now.microsecond / 1e6) / 60.0
    sa = s_frac * 2 * math.pi - math.pi / 2
    sx = int(cx + rr * math.cos(sa))
    sy = int(cy + rr * math.sin(sa))
    draw.ellipse([(sx - 3, sy - 3), (sx + 3, sy + 3)], fill=core)
    draw.ellipse([(sx - 1, sy - 1), (sx + 1, sy + 1)], fill=(255, 245, 220))

    # Tick marks — warm, cardinal-accented
    for i in range(60):
        a = i / 60 * 2 * math.pi - math.pi / 2
        if i % 15 == 0:
            r1, w, col = 100, 2, core
        elif i % 5 == 0:
            r1, w, col = 107, 1, (200, 160, 110)
        else:
            r1, w, col = 111, 1, (90, 65, 50)
        r2 = 115
        draw.line(
            [(int(cx + r1 * math.cos(a)), int(cy + r1 * math.sin(a))),
             (int(cx + r2 * math.cos(a)), int(cy + r2 * math.sin(a)))],
            fill=col, width=w,
        )

    # Digital time — small, below orb
    _centered(draw, now.strftime("%H:%M"), cx, cy + 52, _FONT_TIME_M,
              (250, 235, 215))

    # Top label
    ringing = next(
        (t for t in (ha_ctx or {}).get("timers", []) if t.get("ringing")),
        None,
    )
    stxt = STATE_TEXT.get(state)
    y_top = cy - 78
    if ringing:
        pulse = int(220 + 35 * math.sin(step * 0.5))
        _centered(draw, f"\u23f1 {ringing['name']}", cx, y_top,
                  _FONT_LABEL, (pulse, pulse // 3, 0))
    elif stxt:
        pulse = 0.65 + 0.35 * (0.5 + 0.5 * math.sin(step * 0.20))
        col = tuple(min(255, int(c * pulse)) for c in core)
        _centered(draw, stxt.upper(), cx, y_top, _FONT_LABEL_S, col)
    elif ha_ctx and ha_ctx.get("timers"):
        t = ha_ctx["timers"][0]
        _centered(draw, f"\u23f1 {_fmt_timer(t['remaining_s'], t['name'])}",
                  cx, y_top, _FONT_LABEL, (255, 200, 120))
    elif ha_ctx and ha_ctx.get("media"):
        m  = ha_ctx["media"]
        tx = _scroll(media_scroll_text(m["title"], m["artist"]), radio_off)
        _centered(draw, f"\u266a {tx}", cx, y_top, _FONT_LABEL, (240, 180, 140))
    else:
        _centered(draw,
                  f"{_JOURS[now.weekday()]} {now.day:02d} {_MOIS[now.month - 1]}".upper(),
                  cx, y_top, _FONT_LABEL_S, (180, 150, 120))

    # WiFi fan — top-left
    _draw_wifi_fan(draw, cx - 58, cy - 68, wifi_dbm, core, dim)

    # Volume — vertical column on right
    active = round(vol_pct / 100.0 * 8)
    for i in range(8):
        dy = cy - 28 + i * 7
        col = core if i < active else (60, 40, 30)
        draw.ellipse([(cx + 91, dy - 2), (cx + 95, dy + 2)], fill=col)


# ── V3: Signal ─────────────────────────────────────────────────────────
def _bg_signal(step: int, state: int) -> np.ndarray:
    """Slate base with a fluid waveform band at mid-height."""
    r_a, g_a, b_a = SIGNAL.get(state, SIGNAL[STATE_IDLE])

    # Slate wash — slight top bias
    wash = np.exp(-((_Y - (DISPLAY_CY - 20)) ** 2) / (2.0 * 110.0 ** 2)) * 0.50
    out = np.zeros((DISPLAY_HEIGHT, DISPLAY_WIDTH, 3), dtype=np.float32)
    out[:, :, 0] = 30 * wash
    out[:, :, 1] = 36 * wash
    out[:, :, 2] = 48 * wash

    # Waveform band — 4 layered sine curves, drawn as thin bands
    amp = {STATE_LISTENING: 18.0, STATE_PROCESSING: 10.0,
           STATE_SPEAKING: 22.0, STATE_ERROR: 16.0}.get(state, 6.0)
    freq = {STATE_LISTENING: 0.07, STATE_PROCESSING: 0.05,
            STATE_SPEAKING: 0.05, STATE_ERROR: 0.09}.get(state, 0.04)
    speed = {STATE_LISTENING: 0.25, STATE_PROCESSING: 0.30,
             STATE_SPEAKING: 0.18, STATE_ERROR: 0.40}.get(state, 0.06)

    band_y = float(DISPLAY_CY)
    x = np.arange(DISPLAY_WIDTH, dtype=np.float32)
    edge = 1.0 - np.clip(np.abs(x - DISPLAY_CX) / 119.0, 0, 1) ** 2

    for layer in range(4):
        phase = step * speed + layer * 1.3
        la    = amp * (1.0 - layer * 0.15)
        alpha = 0.55 - layer * 0.1
        y_line = (band_y
                  + np.sin(x * freq + phase) * la * edge
                  + np.sin(x * freq * 1.7 + phase * 0.7 + layer) * la * 0.4 * edge)
        # Paint thin band (~2px) at each x
        yi = y_line.astype(np.int32)
        for dy in (-1, 0, 1):
            mask = (yi + dy >= 0) & (yi + dy < DISPLAY_HEIGHT)
            xs = np.arange(DISPLAY_WIDTH)[mask]
            ys = (yi + dy)[mask]
            a  = alpha * (1.0 - 0.4 * abs(dy))
            out[ys, xs, 0] = np.minimum(255, out[ys, xs, 0] + r_a * a)
            out[ys, xs, 1] = np.minimum(255, out[ys, xs, 1] + g_a * a)
            out[ys, xs, 2] = np.minimum(255, out[ys, xs, 2] + b_a * a)

    np.clip(out, 0, 255, out=out)
    out[~_CIRCLE] = 0
    return out.astype(np.uint8)


def _render_signal(img, draw, step, state, now, vol_pct, wifi_dbm, ha_ctx, radio_off):
    cx, cy = DISPLAY_CX, DISPLAY_CY
    accent = SIGNAL.get(state, SIGNAL[STATE_IDLE])
    dim    = (35, 42, 56)

    # Faint rim + 4 cardinal marks
    draw.ellipse([(cx - 113, cy - 113), (cx + 113, cy + 113)],
                 outline=(35, 42, 56), width=1)
    for i in range(4):
        a = i / 4 * 2 * math.pi - math.pi / 2
        draw.line(
            [(int(cx + 103 * math.cos(a)), int(cy + 103 * math.sin(a))),
             (int(cx + 113 * math.cos(a)), int(cy + 113 * math.sin(a)))],
            fill=(140, 155, 185), width=2,
        )

    # Second-dot on rim
    s_frac = (now.second + now.microsecond / 1e6) / 60.0
    sa = s_frac * 2 * math.pi - math.pi / 2
    sx = int(cx + 108 * math.cos(sa)); sy = int(cy + 108 * math.sin(sa))
    draw.ellipse([(sx - 2, sy - 2), (sx + 2, sy + 2)], fill=accent)

    # Digital time — top block
    _centered(draw, now.strftime("%H:%M"), cx, cy - 72, _FONT_TIME_L,
              (228, 234, 246))

    # Bottom block — state/timer/media/date
    ringing = next(
        (t for t in (ha_ctx or {}).get("timers", []) if t.get("ringing")),
        None,
    )
    stxt = STATE_TEXT.get(state)
    y_b = cy + 50
    if ringing:
        pulse = int(220 + 35 * math.sin(step * 0.5))
        _centered(draw, f"\u23f1 {ringing['name']} +5?", cx, y_b,
                  _FONT_LABEL, (pulse, pulse // 3, 0))
    elif stxt:
        # Dot + label (left-aligned after dot, centered as a unit)
        label = stxt.upper()
        bb = draw.textbbox((0, 0), label, font=_FONT_LABEL_S)
        tw = bb[2] - bb[0]
        total = tw + 14
        x0 = cx - total // 2
        draw.ellipse([(x0, y_b + 3), (x0 + 6, y_b + 9)], fill=accent)
        draw.text((x0 + 14, y_b), label, font=_FONT_LABEL_S, fill=accent)
    elif ha_ctx and ha_ctx.get("timers"):
        t = ha_ctx["timers"][0]
        _centered(draw, f"\u23f1 {_fmt_timer(t['remaining_s'], t['name'])}",
                  cx, y_b, _FONT_LABEL, (255, 200, 120))
    elif ha_ctx and ha_ctx.get("media"):
        m  = ha_ctx["media"]
        tx = _scroll(media_scroll_text(m["title"], m["artist"]), radio_off)
        _centered(draw, f"\u266a {tx}", cx, y_b, _FONT_LABEL, (180, 220, 255))
    else:
        _centered(draw,
                  f"{_JOURS[now.weekday()]} {now.day:02d} {_MOIS[now.month - 1]}".upper(),
                  cx, y_b, _FONT_LABEL_S, (120, 138, 165))

    # WiFi fan (top-left of circle)
    _draw_wifi_fan(draw, cx - 58, cy - 70, wifi_dbm, accent, dim)

    # Tiny vol row top-right, short spacing
    active = round(vol_pct / 100.0 * 8)
    for i in range(8):
        dx = cx + 42 + i * 3
        col = accent if i < active else dim
        draw.ellipse([(dx - 1, cy - 71), (dx + 1, cy - 69)], fill=col)


# ── Shared peripheral widgets ──────────────────────────────────────────
def _draw_wifi_fan(draw, x, y, wifi_dbm, accent, dim):
    arcs = (3 if wifi_dbm > -55 else
            2 if wifi_dbm > -67 else
            1 if wifi_dbm > -80 else 0)
    center_c = (40, 110, 235) if arcs > 0 else dim
    draw.ellipse([(x - 1, y - 1), (x + 1, y + 1)], fill=center_c)
    for ai, r in enumerate([4, 7, 11]):
        col = accent if ai < arcs else dim
        # Arc -50..+50 deg around top (angle 0 = +X, so shift by -90)
        for ang in range(-50, 51, 10):
            rad = math.radians(ang - 90.0)
            px = x + int(round(r * math.cos(rad)))
            py = y + int(round(r * math.sin(rad)))
            if 0 <= px < DISPLAY_WIDTH and 0 <= py < DISPLAY_HEIGHT:
                draw.point((px, py), fill=col)


def _draw_vol_dots(draw, x, y, vol_pct, accent, dim):
    active = round(vol_pct / 100.0 * 8)
    for i in range(8):
        dx = x - 21 + i * 6
        col = accent if i < active else dim
        draw.ellipse([(dx - 2, y - 2), (dx + 2, y + 2)], fill=col)


# ── Public entrypoint ──────────────────────────────────────────────────
_BG_FNS = {
    "aurora": _bg_aurora,
    "ember":  _bg_ember,
    "signal": _bg_signal,
}
_OVERLAY_FNS = {
    "aurora": _render_aurora,
    "ember":  _render_ember,
    "signal": _render_signal,
}


def render_frame(step: int, state: int, now: datetime,
                 vol_pct: int, wifi_dbm: float,
                 ha_context: dict | None = None,
                 radio_offset: int = 0) -> bytes:
    variation  = _get_variation()
    bg_fn      = _BG_FNS.get(variation, _bg_aurora)
    overlay_fn = _OVERLAY_FNS.get(variation, _render_aurora)

    img  = Image.fromarray(bg_fn(step, state), "RGB")
    draw = ImageDraw.Draw(img)
    overlay_fn(img, draw, step, state, now, vol_pct, wifi_dbm,
               ha_context, radio_offset)

    return to_rgb565(img)
