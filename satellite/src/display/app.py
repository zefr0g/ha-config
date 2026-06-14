"""
UI controller + screens for the ST7796S 480×320 voice satellite.

Design: a calm, full-bleed ambient clock (Echo-Show style). Tapping anywhere
opens a two-button menu (Radio / Minuteur). Each opens a focused control
screen that drives Home Assistant. When the assistant is talking/listening, a
voice waveform rises from the bottom and the accent colour shifts.

The controller always renders a full 480×320 image; the daemon diffs it against
what's on the panel and only pushes the changed rectangle over SPI, so idle is
nearly free and interactions feel instant.
"""

import math
import time
from datetime import datetime

import numpy as np
from PIL import Image, ImageDraw

from display import theme as T
from config import (
    STATE_IDLE, STATE_LISTENING, STATE_PROCESSING, STATE_SPEAKING, STATE_ERROR,
)
from display.ha_actions import (
    STATIONS, play_radio, stop_radio, set_volume, start_timer, cancel_timers,
)

W, H = T.W, T.H
_DAY_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_MON_FR = {1: "janvier", 2: "février", 3: "mars", 4: "avril", 5: "mai", 6: "juin",
           7: "juillet", 8: "août", 9: "septembre", 10: "octobre",
           11: "novembre", 12: "décembre"}

MENU_TIMEOUT = 12.0   # seconds of no touch before the menu/sub-screens return home
TIMER_PRESETS = [1, 4, 8, 11]   # quick-add minutes (5th button = custom)
CUSTOM_MIN, CUSTOM_MAX = 1, 90  # bounds for custom duration

# Power-off button + confirm dialog geometry (inside the menu overlay)
OFF_BTN_BOX     = (140, 262, 340, 306)   # "Éteindre" button under the two cards
OFF_CARD_BOX    = (50, 84, 430, 250)     # confirm dialog card
OFF_CANCEL_BOX  = (80, 190, 230, 238)
OFF_CONFIRM_BOX = (250, 190, 400, 238)

# Clock layout: anchor the HH:MM right edge (= the MM/SS junction) and the
# seconds left edge at fixed x, so per-digit width changes never shift the
# layout (Roboto figures aren't tabular). Centred using nominal widths.
_CLK_GAP = 16
_dd = ImageDraw.Draw(Image.new("RGB", (1, 1)))
_WM_NOM = _dd.textlength("00:00", font=T.F_CLOCK)
_WS_NOM = _dd.textlength("00", font=T.F_CLOCK_S)
_CLOCK_RIGHT = int(T.CX + (_WM_NOM - _CLK_GAP - _WS_NOM) / 2)


def _hit(box, x, y):
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


# ── Procedural weather icon (crisp at any accent, no font glyph roulette) ────
def _weather_icon(draw: ImageDraw.ImageDraw, cx, cy, r, condition, accent):
    sun = T.mix(accent, (255, 210, 120), 0.7)
    cloud = (200, 208, 224)
    c = (condition or "").lower()
    if "night" in c:
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=sun)
        draw.ellipse([cx - r + r * 0.5, cy - r, cx + r + r * 0.5, cy + r], fill=T.BG_TOP)
        return
    if "sunny" in c or "clear" in c:
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=sun)
        return
    if any(k in c for k in ("rain", "pour", "snow")):
        draw.ellipse([cx - r, cy - r * 0.4, cx + r * 0.6, cy + r * 0.7], fill=cloud)
        draw.ellipse([cx - r * 0.2, cy - r, cx + r, cy + r * 0.4], fill=cloud)
        for i in range(3):
            x = cx - r * 0.5 + i * r * 0.5
            draw.line([x, cy + r * 0.7, x - r * 0.2, cy + r * 1.3], fill=accent, width=3)
        return
    # default: partly cloudy
    draw.ellipse([cx - r * 0.2, cy - r, cx + r * 0.8, cy], fill=sun)
    draw.ellipse([cx - r, cy - r * 0.2, cx + r * 0.5, cy + r], fill=cloud)
    draw.ellipse([cx - r * 0.1, cy - r * 0.5, cx + r, cy + r * 0.7], fill=cloud)


# ── Voice waveform (bounded bottom band; cheap) ──────────────────────────────
_BAND_TOP = 150
_X = np.linspace(0, 2 * math.pi, W, dtype=np.float32)
_yb, _xb = np.mgrid[_BAND_TOP:H, 0:W].astype(np.float32)


def _wave_amp(state, t):
    x = _X
    if state == STATE_LISTENING:
        env = 0.55 + 0.45 * abs(math.sin(t * 0.6))
        y = env * (0.5 * np.sin(x * 2 + t * 2.4) + 0.3 * np.sin(x * 5 - t * 3.1)
                   + 0.15 * np.sin(x * 9 + t * 4.7))
    elif state == STATE_PROCESSING:
        y = 0.5 * np.sin(x * 3 - t * 2.8) * (0.5 + 0.5 * np.cos(x - t * 0.3))
    elif state == STATE_SPEAKING:
        y = (0.5 * np.sin(x * 4 + t * 3.2) + 0.3 * np.sin(x * 9 - t * 2.5)
             + 0.15 * np.sin(x * 15 + t * 5.1))
    elif state == STATE_ERROR:
        y = np.where(np.abs(np.sin(x * 16 - t * 8)) > 0.9, 0.8, 0.04)
    else:
        y = 0.06 + 0.03 * np.sin(x * 1.5 + t * 0.3)
    return np.clip(np.abs(y), 0, 1)


def _draw_waveform(img: Image.Image, state, t, accent, strength=1.0):
    """Composite a glowing bottom-anchored waveform into the band [_BAND_TOP, H]."""
    amp = _wave_amp(state, t) * 95.0 * strength
    line = (H - 8) - amp[None, :]                       # baseline near bottom
    dist = _yb - line                                   # <0 above, >0 below
    core = 1.5 * np.exp(-(dist ** 2) / (2 * 3.0 ** 2))
    halo = 0.5 * (dist < 0) * np.exp(-(dist ** 2) / (2 * 22.0 ** 2))
    fill = ((_yb >= line) & (_yb <= H - 8)) * 0.18
    glow = np.clip(core + halo + fill, 0, 2.2)[:, :, None] * np.array(accent, np.float32)

    band = np.asarray(img.crop((0, _BAND_TOP, W, H)), np.float32)
    band = np.clip(band + glow, 0, 255).astype(np.uint8)
    img.paste(Image.fromarray(band, "RGB"), (0, _BAND_TOP))


class App:
    def __init__(self):
        self.screen = "home"          # home | radio | timer | shutdown
        self.menu_open = False
        self.menu_confirm_off = False    # power-off confirm dialog showing
        self.shutdown_requested = False  # daemon polls this → graceful poweroff
        self.last_touch = time.monotonic()
        self.active_station = None     # station id currently playing (optimistic)
        self._vol = 50
        self._vol_set_at = 0.0
        self._toast = ""
        self._toast_until = 0.0
        self._timer_init: dict[str, int] = {}   # id → initial seconds (for ring)
        self._home_radio_box = None              # tappable status pills on home
        self._home_timer_box = None
        self._home_vol_box = None                # tappable volume slider on home
        self._home_ring_box = None               # "Arrêter" button shown while ringing
        self.timer_custom = False                # custom-duration entry mode
        self.custom_min = 15
        self.t0 = time.monotonic()

    # ── helpers ──────────────────────────────────────────────────────────────
    def _toast_msg(self, msg, secs=1.6):
        self._toast = msg
        self._toast_until = time.monotonic() + secs

    def _volume(self, ctx):
        # Optimistic: show the value we just set until HA catches up (~6 s).
        if time.monotonic() - self._vol_set_at < 6.0:
            return self._vol
        return (ctx or {}).get("volume_pct", self._vol)

    def is_animating(self, state):
        return (state != STATE_IDLE
                or self.menu_open
                or time.monotonic() < self._toast_until)

    def note_touch(self):
        self.last_touch = time.monotonic()

    def maybe_timeout(self):
        if self.screen == "shutdown":
            return    # terminal screen — never auto-dismiss
        if (self.screen != "home" or self.menu_open) and \
           time.monotonic() - self.last_touch > MENU_TIMEOUT:
            self.screen = "home"
            self.menu_open = False
            self.menu_confirm_off = False

    # ── touch routing ────────────────────────────────────────────────────────
    def handle_tap(self, x, y, ctx):
        self.note_touch()
        print(f"[UI] tap ({x},{y}) screen={self.screen} menu={self.menu_open}", flush=True)
        if self.screen == "home":
            if self.menu_open:
                self._tap_menu(x, y)
            elif self._home_ring_box and _hit(self._home_ring_box, x, y):
                print("[UI] dismiss ringing timer (home button)", flush=True)
                if cancel_timers():
                    self._toast_msg("Minuteur arrêté")
            elif self._home_vol_box and _hit(self._home_vol_box, x, y):
                pct = max(0, min(100, int(round((x - 90) / 300 * 100))))
                self._vol, self._vol_set_at = pct, time.monotonic()
                print(f"[UI] home volume -> {pct}", flush=True)
                set_volume(pct)
            elif self._home_radio_box and _hit(self._home_radio_box, x, y):
                self.screen = "radio"
            elif self._home_timer_box and _hit(self._home_timer_box, x, y):
                self.screen = "timer"
            else:
                self.menu_open = True
                self.menu_confirm_off = False
        elif self.screen == "radio":
            self._tap_radio(x, y, ctx)
        elif self.screen == "timer":
            self._tap_timer(x, y, ctx)

    def _tap_menu(self, x, y):
        if self.menu_confirm_off:                       # power-off confirm dialog
            if _hit(OFF_CONFIRM_BOX, x, y):
                print("[UI] poweroff confirmed", flush=True)
                self.shutdown_requested = True
                self.screen, self.menu_open = "shutdown", False
            elif _hit(OFF_CANCEL_BOX, x, y):
                self.menu_confirm_off = False
            return
        if _hit((30, 96, 232, 248), x, y):
            self.screen, self.menu_open = "radio", False
        elif _hit((248, 96, 450, 248), x, y):
            self.screen, self.menu_open = "timer", False
        elif _hit(OFF_BTN_BOX, x, y):
            self.menu_confirm_off = True
        else:
            self.menu_open = False

    def _tap_radio(self, x, y, ctx):
        if _hit((0, 0, 70, 56), x, y):              # back chevron
            self.screen = "home"
            return
        for i, st in enumerate(STATIONS):           # station grid
            box = self._station_box(i)
            if _hit(box, x, y):
                if play_radio(st["url"]):
                    self.active_station = st["id"]
                    self._toast_msg(f"Lecture · {st['label']}")
                return
        if _hit((392, 258, 462, 308), x, y):        # stop
            print("[UI] stop_radio (stop button)", flush=True)
            if stop_radio():
                self.active_station = None
                self._toast_msg("Radio arrêtée")
            return
        if _hit((18, 262, 372, 304), x, y):         # volume slider
            pct = int(round((x - 30) / (360 - 30) * 100))
            pct = max(0, min(100, pct))
            self._vol, self._vol_set_at = pct, time.monotonic()
            set_volume(pct)

    def _tap_timer(self, x, y, ctx):
        if _hit((0, 0, 70, 56), x, y):
            self.screen = "home"
            self.timer_custom = False
            return
        if self.timer_custom:
            if _hit((60, 90, 120, 150), x, y):           # −1
                self.custom_min = max(CUSTOM_MIN, self.custom_min - 1)
            elif _hit((360, 90, 420, 150), x, y):        # +1
                self.custom_min = min(CUSTOM_MAX, self.custom_min + 1)
            elif _hit((150, 176, 230, 214), x, y):       # −5
                self.custom_min = max(CUSTOM_MIN, self.custom_min - 5)
            elif _hit((250, 176, 330, 214), x, y):       # +5
                self.custom_min = min(CUSTOM_MAX, self.custom_min + 5)
            elif _hit((110, 250, 370, 302), x, y):       # Démarrer
                print(f"[UI] start_timer {self.custom_min} (custom)", flush=True)
                if start_timer(self.custom_min):
                    self._toast_msg(f"Minuteur · {self.custom_min} min")
                    self.timer_custom = False
            return
        if (ctx or {}).get("timers") and _hit((294, 170, 346, 222), x, y):  # cancel ✕
            print("[UI] cancel_timers", flush=True)
            if cancel_timers():
                self._toast_msg("Minuteurs annulés")
            return
        for i in range(5):
            if _hit(self._preset_box(i), x, y):
                if i < 4:
                    print(f"[UI] start_timer {TIMER_PRESETS[i]}", flush=True)
                    if start_timer(TIMER_PRESETS[i]):
                        self._toast_msg(f"Minuteur · {TIMER_PRESETS[i]} min")
                else:
                    self.timer_custom = True
                return

    # ── geometry ──────────────────────────────────────────────────────────────
    def _station_box(self, i):
        col, row = i % 2, i // 2
        x0 = 18 + col * 234
        y0 = 70 + row * 56
        return (x0, y0, x0 + 210, y0 + 46)

    def _preset_box(self, i):       # 4 presets + "Perso" (5 across)
        x0 = 18 + i * 90
        return (x0, 250, x0 + 80, 304)

    # ── rendering ──────────────────────────────────────────────────────────────
    def render(self, state, now: datetime, ctx) -> Image.Image:
        self.maybe_timeout()
        accent = T.ACCENT.get(state, T.ACCENT[STATE_IDLE])
        img = T.background(accent)
        draw = ImageDraw.Draw(img)

        if self.screen == "shutdown":
            self._icon_power(draw, T.CX, H // 2 - 44, (255, 140, 110), r=20)
            T.text_center(draw, T.CX, H // 2 + 4, "Arrêt en cours…", T.F_TITLE, T.INK)
            T.text_center(draw, T.CX, H // 2 + 40,
                          "Débranchez une fois l'écran éteint", T.F_SMALL, T.INK_DIM)
            return img

        if self.screen == "home":
            self._render_home(draw, img, state, now, ctx, accent)
        elif self.screen == "radio":
            self._render_radio(draw, img, now, ctx, accent)
        elif self.screen == "timer":
            self._render_timer(draw, img, now, ctx, accent)

        # Voice waveform overlay (home) or top strip (sub-screens)
        t = time.monotonic() - self.t0
        if state != STATE_IDLE:
            if self.screen == "home" and not self.menu_open:
                _draw_waveform(img, state, t, accent, strength=1.0)
                lbl = T.STATE_LABEL.get(state, "")
                if lbl:
                    T.text_center(draw, T.CX, 168, lbl, T.F_LABEL, accent)
            else:
                draw.rectangle([0, 0, W, 4], fill=accent)

        self._render_toast(draw)
        return img

    # ── HOME (ambient) ──────────────────────────────────────────────────────
    def _render_home(self, draw, img, state, now, ctx, accent):
        self._home_radio_box = self._home_timer_box = self._home_vol_box = None
        self._home_ring_box = None
        timers = (ctx or {}).get("timers", [])
        ringing = any(t.get("ringing") for t in timers)
        # status: weather (top-right)
        weather = (ctx or {}).get("weather") or {}
        temp, cond = weather.get("temp"), weather.get("condition")
        if temp is not None:
            _weather_icon(draw, W - 96, 30, 16, cond, accent)
            draw.text((W - 18, 14), f"{temp}°", font=T.F_TEMP, fill=T.INK, anchor="ra")

        voice_active = state != STATE_IDLE and not self.menu_open
        f = 0.25 if voice_active else 1.0
        yb = 138 if voice_active else 196          # text baseline
        col = T.dim(T.INK, f)
        # HH:MM hero + smaller trailing seconds, baseline-aligned
        draw.text((_CLOCK_RIGHT, yb), now.strftime("%H:%M"),
                  font=T.F_CLOCK, fill=col, anchor="rs")
        draw.text((_CLOCK_RIGHT + _CLK_GAP, yb), now.strftime("%S"),
                  font=T.F_CLOCK_S, fill=T.dim(col, 0.62), anchor="ls")

        playing = bool((ctx or {}).get("sat_playing"))
        # Date when ambient; hidden while playing (the now-playing pill + volume
        # slider take the space) or while a timer is ringing (the stop button does).
        if not voice_active and not playing and not ringing:
            date_str = f"{_DAY_FR[now.weekday()]} {now.day} {_MON_FR[now.month]}"
            T.text_center(draw, T.CX, 232, date_str, T.F_DATE, T.INK_DIM)

        if ringing and not self.menu_open:
            # A finished timer takes over the lower band with a direct stop button.
            self._render_ring_stop(draw)
        elif not voice_active and not self.menu_open:
            self._status_pills(draw, ctx, accent, y=248 if playing else 280)
            if playing:
                self._home_volume(draw, ctx, accent)

        if self.menu_open:
            self._render_menu(draw, img, accent)

    def _station_label(self):
        for st in STATIONS:
            if st["id"] == self.active_station:
                return st["label"]
        return None

    def _status_pills(self, draw, ctx, accent, y=280):
        """Tappable pills on home reflecting a running timer / playing radio."""
        pills = []
        timers = (ctx or {}).get("timers", [])
        if timers:
            r = max(0, timers[0].get("remaining_s", 0))
            m, s = divmod(r, 60)
            pills.append(("timer", f"{m}:{s:02d}" if m < 60 else f"{m//60}h{m%60:02d}"))
        if (ctx or {}).get("sat_playing"):
            pills.append(("radio", self._station_label() or "Radio"))
        if not pills:
            return

        PAD, ICON, GAP, h = 14, 20, 12, 32
        widths = [int(PAD + ICON + 8 + draw.textlength(t, font=T.F_SMALL) + PAD)
                  for _, t in pills]
        x = T.CX - (sum(widths) + GAP * (len(pills) - 1)) // 2
        for (kind, txt), w in zip(pills, widths):
            box = (x, y, x + w, y + h)
            T.rounded(draw, box, h // 2, fill=T.CARD, outline=T.dim(accent, 0.7))
            icx, icy = x + PAD + ICON // 2, y + h // 2
            if kind == "radio":
                draw.ellipse([icx - 9, icy - 9, icx + 9, icy + 9], outline=accent, width=2)
                draw.polygon([(icx - 3, icy - 4), (icx - 3, icy + 4), (icx + 4, icy)], fill=accent)
                self._home_radio_box = box
            else:
                draw.ellipse([icx - 9, icy - 9, icx + 9, icy + 9], outline=accent, width=2)
                draw.line([icx, icy, icx, icy - 6], fill=accent, width=2)
                draw.line([icx, icy, icx + 4, icy], fill=accent, width=2)
                self._home_timer_box = box
            draw.text((x + PAD + ICON + 8, icy), txt, font=T.F_SMALL, fill=T.INK, anchor="lm")
            x += w + GAP

    def _home_volume(self, draw, ctx, accent):
        """Tappable volume slider on home, shown while audio plays."""
        vx0, vx1, vy = 90, 390, 298
        pct = self._volume(ctx)
        # small speaker glyph
        sx = 56
        draw.polygon([(sx - 6, vy - 5), (sx, vy - 5), (sx + 7, vy - 11),
                      (sx + 7, vy + 11), (sx, vy + 5), (sx - 6, vy + 5)], fill=T.INK_DIM)
        draw.line([vx0, vy, vx1, vy], fill=T.INK_FAINT, width=4)
        fillx = vx0 + int((vx1 - vx0) * pct / 100)
        draw.line([vx0, vy, fillx, vy], fill=accent, width=4)
        draw.ellipse([fillx - 9, vy - 9, fillx + 9, vy + 9], fill=T.INK)
        draw.text((vx1 + 12, vy), f"{pct}%", font=T.F_SMALL, fill=T.INK_DIM, anchor="lm")
        self._home_vol_box = (vx0 - 12, vy - 22, vx1 + 12, vy + 22)

    def _render_ring_stop(self, draw):
        """Direct 'stop the alarm' button on home while a timer is ringing."""
        red = (255, 80, 60)
        T.text_center(draw, T.CX, 230, "Minuteur terminé", T.F_LABEL, red)
        box = (120, 256, 360, 306)
        T.rounded(draw, box, 18, fill=T.mix(T.CARD, red, 0.22), outline=red, width=2)
        cy = (box[1] + box[3]) // 2
        self._icon_bell(draw, box[0] + 42, cy, red)
        T.text_center(draw, (box[0] + 64 + box[2]) // 2, cy, "Arrêter",
                      T.F_LABEL, T.INK, anchor="mm")
        self._home_ring_box = box

    def _icon_bell(self, draw, cx, cy, color):
        draw.pieslice([cx - 10, cy - 12, cx + 10, cy + 6], 180, 360, fill=color)
        draw.rectangle([cx - 12, cy + 4, cx + 12, cy + 8], fill=color)
        draw.ellipse([cx - 3, cy + 8, cx + 3, cy + 14], fill=color)

    def _render_menu(self, draw, img, accent):
        # Dim the ambient home behind the menu (in place, keeps `draw` valid).
        img.paste(Image.blend(img, Image.new("RGB", img.size, (3, 4, 9)), 0.9))
        if self.menu_confirm_off:
            self._render_confirm_off(draw, accent)
            return
        for box, icon, label in (
            ((30, 96, 232, 248), "radio", "Radio"),
            ((248, 96, 450, 248), "timer", "Minuteur"),
        ):
            T.rounded(draw, box, 22, fill=T.CARD, outline=T.dim(accent, 0.9), width=2)
            cx = (box[0] + box[2]) // 2
            if icon == "radio":
                self._icon_radio(draw, cx, 150, accent)
            else:
                self._icon_timer(draw, cx, 150, accent)
            T.text_center(draw, cx, 200, label, T.F_TITLE, T.INK)

        # Power-off button under the two cards.
        red = (255, 130, 100)
        T.rounded(draw, OFF_BTN_BOX, 22, fill=T.CARD, outline=T.dim(red, 0.9), width=2)
        cy = (OFF_BTN_BOX[1] + OFF_BTN_BOX[3]) // 2
        self._icon_power(draw, OFF_BTN_BOX[0] + 32, cy, red, r=13)
        draw.text((OFF_BTN_BOX[0] + 56, cy), "Éteindre", font=T.F_LABEL,
                  fill=T.INK, anchor="lm")

    def _render_confirm_off(self, draw, accent):
        red = (255, 110, 90)
        T.rounded(draw, OFF_CARD_BOX, 22, fill=T.CARD, outline=T.dim(red, 0.8), width=2)
        self._icon_power(draw, T.CX, 124, red, r=18)
        T.text_center(draw, T.CX, 162, "Éteindre le satellite ?", T.F_TITLE, T.INK)
        T.rounded(draw, OFF_CANCEL_BOX, 16, fill=T.CARD_HI, outline=T.INK_FAINT)
        T.text_center(draw, (OFF_CANCEL_BOX[0] + OFF_CANCEL_BOX[2]) // 2,
                      (OFF_CANCEL_BOX[1] + OFF_CANCEL_BOX[3]) // 2,
                      "Annuler", T.F_LABEL, T.INK, anchor="mm")
        T.rounded(draw, OFF_CONFIRM_BOX, 16, fill=T.CARD, outline=red, width=2)
        T.text_center(draw, (OFF_CONFIRM_BOX[0] + OFF_CONFIRM_BOX[2]) // 2,
                      (OFF_CONFIRM_BOX[1] + OFF_CONFIRM_BOX[3]) // 2,
                      "Éteindre", T.F_LABEL, red, anchor="mm")

    # ── RADIO ─────────────────────────────────────────────────────────────────
    def _render_radio(self, draw, img, now, ctx, accent):
        self._header(draw, "Radio", now)
        # Highlight strictly the station we last started (no substring matching —
        # "rtl" is a substring of "rtl2"). Cleared when playback stops.
        playing = (ctx or {}).get("sat_playing")

        for i, st in enumerate(STATIONS):
            box = self._station_box(i)
            active = playing and self.active_station == st["id"]
            fill = T.CARD_HI if active else T.CARD
            T.rounded(draw, box, 12, fill=fill,
                      outline=st["color"] if active else T.INK_FAINT,
                      width=2 if active else 1)
            cy = (box[1] + box[3]) // 2
            draw.ellipse([box[0] + 14, cy - 6, box[0] + 26, cy + 6], fill=st["color"])
            draw.text((box[0] + 40, cy), st["label"], font=T.F_LABEL,
                      fill=T.INK if active else T.INK_DIM, anchor="lm")
            if active:
                bx = box[2] - 22
                draw.polygon([(bx, cy - 7), (bx, cy + 7), (bx + 12, cy)], fill=accent)

        # volume slider
        vx0, vx1, vy = 30, 360, 283
        pct = self._volume(ctx)
        draw.line([vx0, vy, vx1, vy], fill=T.INK_FAINT, width=4)
        fillx = vx0 + int((vx1 - vx0) * pct / 100)
        draw.line([vx0, vy, fillx, vy], fill=accent, width=4)
        draw.ellipse([fillx - 9, vy - 9, fillx + 9, vy + 9], fill=T.INK)
        draw.text((vx0, vy - 30), "Volume", font=T.F_SMALL, fill=T.INK_DIM)
        draw.text((vx1, vy - 30), f"{pct}%", font=T.F_SMALL, fill=T.INK_DIM, anchor="ra")

        # stop button
        T.rounded(draw, (392, 258, 462, 308), 12, fill=T.CARD, outline=T.INK_FAINT)
        draw.rectangle([418, 277, 436, 289], fill=T.mix(accent, (255, 80, 60), 0.6))

    # ── TIMER ───────────────────────────────────────────────────────────────
    def _render_timer(self, draw, img, now, ctx, accent):
        self._header(draw, "Minuteur", now)
        if self.timer_custom:
            self._render_custom(draw, accent)
            return

        timers = (ctx or {}).get("timers", [])
        if timers:
            t0 = timers[0]
            key = t0.get("id") or t0.get("name", "timer")
            rem = max(0, t0.get("remaining_s", 0))
            self._timer_init[key] = max(self._timer_init.get(key, 0), rem)
            frac = rem / self._timer_init[key] if self._timer_init[key] else 0
            self._ring(draw, 120, 150, 78, frac, rem, t0.get("ringing"), accent)
            for j, tm in enumerate(timers[1:3]):
                r = max(0, tm.get("remaining_s", 0))
                m, s = divmod(r, 60)
                draw.text((262, 96 + j * 34), f"• {m}:{s:02d}",
                          font=T.F_BODY, fill=T.INK_DIM)
            self._cancel_btn(draw)
        else:
            T.text_center(draw, T.CX, 150, "Aucun minuteur", T.F_BODY, T.INK_DIM)

        # 4 quick presets + "Perso" (custom)
        for i in range(5):
            box = self._preset_box(i)
            cx = (box[0] + box[2]) // 2
            T.rounded(draw, box, 12, fill=T.CARD, outline=T.dim(accent, 0.8))
            if i < 4:
                draw.text((cx, box[1] + 12), str(TIMER_PRESETS[i]),
                          font=T.F_TITLE, fill=T.INK, anchor="ma")
                draw.text((cx, box[1] + 36), "min", font=T.F_SMALL,
                          fill=T.INK_DIM, anchor="ma")
            else:
                draw.text((cx, (box[1] + box[3]) // 2), "Perso",
                          font=T.F_LABEL, fill=T.INK, anchor="mm")

    def _cancel_btn(self, draw):
        cx, cy, red = 320, 196, (255, 90, 70)
        draw.ellipse([cx - 26, cy - 26, cx + 26, cy + 26], outline=red, width=3)
        draw.line([cx - 9, cy - 9, cx + 9, cy + 9], fill=red, width=3)
        draw.line([cx - 9, cy + 9, cx + 9, cy - 9], fill=red, width=3)
        draw.text((cx, cy + 34), "Annuler", font=T.F_SMALL, fill=T.INK_DIM, anchor="ma")

    def _render_custom(self, draw, accent):
        # big value
        T.text_center(draw, T.CX - 20, 120, str(self.custom_min), T.F_RING, T.INK, anchor="mm")
        draw.text((T.CX + 64, 120), "min", font=T.F_BODY, fill=T.INK_DIM, anchor="lm")
        # −1 / +1 round buttons (drawn glyphs, no font risk)
        for cx2, plus in ((90, False), (390, True)):
            draw.ellipse([cx2 - 30, 90, cx2 + 30, 150], outline=accent, width=3)
            draw.line([cx2 - 12, 120, cx2 + 12, 120], fill=T.INK, width=3)
            if plus:
                draw.line([cx2, 108, cx2, 132], fill=T.INK, width=3)
        # −5 / +5 pills
        for bx, label in (((150, 176, 230, 214), "-5"), ((250, 176, 330, 214), "+5")):
            T.rounded(draw, bx, 14, fill=T.CARD, outline=T.dim(accent, 0.7))
            draw.text(((bx[0] + bx[2]) // 2, (bx[1] + bx[3]) // 2), label,
                      font=T.F_LABEL, fill=T.INK, anchor="mm")
        # Démarrer
        T.rounded(draw, (110, 250, 370, 302), 16, fill=T.CARD_HI, outline=accent, width=2)
        T.text_center(draw, T.CX, (250 + 302) // 2,
                      f"Démarrer · {self.custom_min} min", T.F_LABEL, T.INK, anchor="mm")

    def _ring(self, draw, cx, cy, r, frac, rem, ringing, accent):
        col = (255, 70, 50) if ringing else accent
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=T.CARD, width=10)
        frac = 1.0 if ringing else max(0.0, min(1.0, frac))
        end = -90 + 360 * frac
        draw.arc([cx - r, cy - r, cx + r, cy + r], -90, end, fill=col, width=10)
        m, s = divmod(rem, 60)
        txt = f"{m}:{s:02d}" if m < 60 else f"{m//60}:{m%60:02d}:{s:02d}"
        T.text_center(draw, cx, cy, txt, T.F_RING, T.INK, anchor="mm")

    # ── shared chrome ─────────────────────────────────────────────────────────
    def _header(self, draw, title, now):
        draw.text((22, 28), "‹", font=T.font("thin", 44), fill=T.INK, anchor="lm")
        T.text_center(draw, T.CX, 14, title, T.F_TITLE, T.INK)
        draw.text((W - 18, 28), now.strftime("%H:%M"), font=T.F_CLOCK2,
                  fill=T.INK_DIM, anchor="rm")

    def _render_toast(self, draw):
        if time.monotonic() >= self._toast_until or not self._toast:
            return
        w, _ = T.text_size(draw, self._toast, T.F_LABEL)
        box = (T.CX - w // 2 - 20, H - 46, T.CX + w // 2 + 20, H - 12)
        T.rounded(draw, box, 17, fill=T.CARD_HI)
        T.text_center(draw, T.CX, H - 40, self._toast, T.F_LABEL, T.INK)

    # ── menu icons ─────────────────────────────────────────────────────────────
    def _icon_radio(self, draw, cx, cy, accent):
        draw.rounded_rectangle([cx - 30, cy - 8, cx + 30, cy + 26], 6,
                               outline=accent, width=3)
        draw.line([cx - 18, cy - 8, cx + 6, cy - 26], fill=accent, width=3)
        draw.ellipse([cx + 8, cy + 2, cx + 24, cy + 18], outline=accent, width=3)

    def _icon_timer(self, draw, cx, cy, accent):
        draw.arc([cx - 24, cy - 22, cx + 24, cy + 26], 0, 360, fill=accent, width=3)
        draw.line([cx - 8, cy - 30, cx + 8, cy - 30], fill=accent, width=3)
        draw.line([cx, cy + 2, cx, cy - 12], fill=accent, width=3)

    def _icon_power(self, draw, cx, cy, color, r=14):
        # Standard power symbol: ring open at the top + vertical stem.
        w = max(2, r // 5)
        draw.arc([cx - r, cy - r, cx + r, cy + r], -60, 240, fill=color, width=w)
        draw.line([cx, cy - r - w, cx, cy + 1], fill=color, width=w)
