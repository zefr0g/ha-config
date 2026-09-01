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
from display.bt_actions import read_bt_status, request_pairing, stop_pairing

W, H = T.W, T.H
_DAY_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_MON_FR = {1: "janvier", 2: "février", 3: "mars", 4: "avril", 5: "mai", 6: "juin",
           7: "juillet", 8: "août", 9: "septembre", 10: "octobre",
           11: "novembre", 12: "décembre"}

MENU_TIMEOUT = 12.0   # seconds of no touch before the menu/sub-screens return home
TIMER_PRESETS = [5, 10, 15, 30]   # quick-add minutes (5th button = custom)
CUSTOM_MIN, CUSTOM_MAX = 1, 90  # bounds for custom duration

# Menu tiles (box, icon, label, target screen) — three across.
MENU_CARDS = (
    ((16,  90, 157, 240), "radio",     "Radio",     "radio"),
    ((170, 90, 311, 240), "timer",     "Minuteur",  "timer"),
    ((323, 90, 464, 240), "bluetooth", "Bluetooth", "bluetooth"),
)

# Power-off button + confirm dialog geometry (inside the menu overlay)
OFF_BTN_BOX     = (140, 258, 340, 300)   # "Éteindre" button under the tiles
OFF_CARD_BOX    = (50, 84, 430, 250)     # confirm dialog card
OFF_CANCEL_BOX  = (80, 190, 230, 238)
OFF_CONFIRM_BOX = (250, 190, 400, 238)

# Timer screen: "Annuler", centred directly under the countdown ring
CANCEL_BTN_BOX = (150, 190, 330, 236)
# Radio screen: labelled stop button, right of the volume slider
STOP_BTN_BOX = (386, 250, 462, 308)
# Custom-duration screen: the −5 / +5 step pills
STEP5_BOXES = ((146, 168, 234, 216), (246, 168, 334, 216))

# Bluetooth screen geometry
BT_PAIR_BTN_BOX = (90, 150, 390, 220)    # primary "make discoverable" / "stop" button

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


def _short(s, n):
    """Truncate with an ellipsis so a long BT track title can't overflow a pill."""
    s = s or ""
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


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
    # Restrained glow: a crisp core with a short halo. A wide, bright bloom read
    # as "gaming RGB" against the calm palette of every other screen.
    core = 1.05 * np.exp(-(dist ** 2) / (2 * 2.6 ** 2))
    halo = 0.26 * (dist < 0) * np.exp(-(dist ** 2) / (2 * 15.0 ** 2))
    fill = ((_yb >= line) & (_yb <= H - 8)) * 0.14
    glow = np.clip(core + halo + fill, 0, 1.5)[:, :, None] * np.array(accent, np.float32)

    band = np.asarray(img.crop((0, _BAND_TOP, W, H)), np.float32)
    band = np.clip(band + glow, 0, 255).astype(np.uint8)
    img.paste(Image.fromarray(band, "RGB"), (0, _BAND_TOP))


class App:
    def __init__(self):
        self.screen = "home"          # home | radio | timer | bluetooth | shutdown
        self.menu_open = False
        self.menu_confirm_off = False    # power-off confirm dialog showing
        self.shutdown_requested = False  # daemon polls this → graceful poweroff
        self.last_touch = time.monotonic()
        self.active_station = None     # station id currently playing (optimistic)
        self._station_set_at = 0.0     # last on-screen radio tap (optimistic window)
        self._vol = 50
        self._vol_set_at = 0.0
        self._toast = ""
        self._toast_until = 0.0
        self._toast_error = False
        self._timer_init: dict[str, int] = {}   # id → initial seconds (for ring)
        self._home_radio_box = None              # tappable status pills on home
        self._home_timer_box = None
        self._home_bt_box = None                 # tappable bluetooth now-playing pill
        self._home_stop_box = None               # stop-radio button beside the radio pill
        self._home_vol_box = None                # tappable volume slider on home
        self.timer_custom = False                # custom-duration entry mode
        self.custom_min = 15
        self._bt = dict(read_bt_status())        # bluetooth status (refreshed on its screen)
        self._pairing_active = False             # discoverable window open (keeps screen up)
        self.t0 = time.monotonic()

    # ── helpers ──────────────────────────────────────────────────────────────
    def _toast_msg(self, msg, secs=1.6, error=False):
        self._toast = msg
        # errors linger a touch longer so they're not missed
        self._toast_until = time.monotonic() + (secs if not error else max(secs, 2.6))
        self._toast_error = error

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
        if self.screen == "bluetooth" and self._pairing_active:
            return    # keep the pairing screen up for the whole discoverable window
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
            elif self._home_vol_box and _hit(self._home_vol_box, x, y):
                pct = max(0, min(100, int(round((x - 90) / 300 * 100))))
                self._vol, self._vol_set_at = pct, time.monotonic()
                print(f"[UI] home volume -> {pct}", flush=True)
                if not set_volume(pct):
                    self._toast_msg("Volume indisponible", error=True)
            elif self._home_stop_box and _hit(self._home_stop_box, x, y):
                print("[UI] stop_radio (home pill)", flush=True)
                if stop_radio():
                    self.active_station = None
                    self._station_set_at = time.monotonic()
                    self._toast_msg("Radio arrêtée")
                else:
                    self._toast_msg("Échec de l'arrêt", error=True)
            elif self._home_radio_box and _hit(self._home_radio_box, x, y):
                self.screen = "radio"
            elif self._home_timer_box and _hit(self._home_timer_box, x, y):
                self.screen = "timer"
            elif self._home_bt_box and _hit(self._home_bt_box, x, y):
                self.screen = "bluetooth"
            else:
                self.menu_open = True
                self.menu_confirm_off = False
        elif self.screen == "radio":
            self._tap_radio(x, y, ctx)
        elif self.screen == "timer":
            self._tap_timer(x, y, ctx)
        elif self.screen == "bluetooth":
            self._tap_bluetooth(x, y)

    def _tap_menu(self, x, y):
        if self.menu_confirm_off:                       # power-off confirm dialog
            if _hit(OFF_CONFIRM_BOX, x, y):
                print("[UI] poweroff confirmed", flush=True)
                self.shutdown_requested = True
                self.screen, self.menu_open = "shutdown", False
            elif _hit(OFF_CANCEL_BOX, x, y):
                self.menu_confirm_off = False
            return
        for box, _icon, _label, target in MENU_CARDS:
            if _hit(box, x, y):
                self.screen, self.menu_open = target, False
                return
        if _hit(OFF_BTN_BOX, x, y):
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
                    self._station_set_at = time.monotonic()
                    self._toast_msg(f"Lecture · {st['label']}")
                else:
                    self._toast_msg("Lecture impossible", error=True)
                return
        if _hit(STOP_BTN_BOX, x, y):                # stop
            print("[UI] stop_radio (stop button)", flush=True)
            if stop_radio():
                self.active_station = None
                self._station_set_at = time.monotonic()
                self._toast_msg("Radio arrêtée")
            else:
                self._toast_msg("Échec de l'arrêt", error=True)
            return
        if _hit((20, 262, 348, 304), x, y):         # volume slider
            pct = int(round((x - 64) / (322 - 64) * 100))
            pct = max(0, min(100, pct))
            self._vol, self._vol_set_at = pct, time.monotonic()
            if not set_volume(pct):
                self._toast_msg("Volume indisponible", error=True)

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
            elif _hit(STEP5_BOXES[0], x, y):             # −5
                self.custom_min = max(CUSTOM_MIN, self.custom_min - 5)
            elif _hit(STEP5_BOXES[1], x, y):             # +5
                self.custom_min = min(CUSTOM_MAX, self.custom_min + 5)
            elif _hit((110, 250, 370, 302), x, y):       # Démarrer
                print(f"[UI] start_timer {self.custom_min} (custom)", flush=True)
                if start_timer(self.custom_min):
                    self._toast_msg(f"Minuteur · {self.custom_min} min")
                    self.timer_custom = False
                else:
                    self._toast_msg("Minuteur impossible", error=True)
            return
        if (ctx or {}).get("timers") and _hit(CANCEL_BTN_BOX, x, y):  # cancel
            print("[UI] cancel_timers", flush=True)
            if cancel_timers():
                self._toast_msg("Minuteurs annulés")
            else:
                self._toast_msg("Échec de l'annulation", error=True)
            return
        for i in range(5):
            if _hit(self._preset_box(i), x, y):
                if i < 4:
                    print(f"[UI] start_timer {TIMER_PRESETS[i]}", flush=True)
                    if start_timer(TIMER_PRESETS[i]):
                        self._toast_msg(f"Minuteur · {TIMER_PRESETS[i]} min")
                    else:
                        self._toast_msg("Minuteur impossible", error=True)
                else:
                    self.timer_custom = True
                return

    def _tap_bluetooth(self, x, y):
        if _hit((0, 0, 70, 56), x, y):              # back chevron
            self.screen = "home"
            return
        if _hit(BT_PAIR_BTN_BOX, x, y):             # toggle discoverable
            if self._bt.get("discoverable"):
                print("[UI] bt stop_pairing", flush=True)
                self._pairing_active = False
                if stop_pairing():
                    self._toast_msg("Recherche arrêtée")
                else:
                    self._toast_msg("Bluetooth indisponible", error=True)
            else:
                print("[UI] bt request_pairing", flush=True)
                if request_pairing():
                    self._pairing_active = True     # assume on until the bridge confirms
                    self._toast_msg("Détectable · 2 min")
                else:
                    self._toast_msg("Bluetooth indisponible", error=True)

    # ── geometry ──────────────────────────────────────────────────────────────
    def _station_box(self, i):       # 3×2 grid of logo tiles
        col, row = i % 3, i // 3
        x0 = 14 + col * 153
        y0 = 60 + row * 98
        return (x0, y0, x0 + 145, y0 + 90)

    def _preset_box(self, i):       # 4 presets + "Perso" (5 across)
        x0 = 18 + i * 90
        return (x0, 250, x0 + 80, 304)

    # ── rendering ──────────────────────────────────────────────────────────────
    def render(self, state, now: datetime, ctx) -> Image.Image:
        self._bt = read_bt_status()
        self._pairing_active = bool(self._bt.get("discoverable"))
        self.maybe_timeout()
        self._sync_station(ctx)
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
        elif self.screen == "bluetooth":
            self._render_bluetooth(draw, img, now, accent)

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
        self._home_bt_box = self._home_stop_box = None
        timers = (ctx or {}).get("timers", [])
        # Ring state comes from the LED daemon's log tail (HA hides finished timers).
        ringing = bool((ctx or {}).get("timer_ringing"))
        voice_active = state != STATE_IDLE and not self.menu_open
        # status: weather (top-right)
        weather = (ctx or {}).get("weather") or {}
        temp, cond = weather.get("temp"), weather.get("condition")
        if temp is not None and not voice_active:
            # Floating icon + temp — chipless reads calmer on the ambient screen.
            label = f"{temp}°"
            tw = draw.textlength(label, font=T.F_TEMP)
            _weather_icon(draw, int(W - 30 - tw - 22), 33, 13, cond, accent)
            draw.text((W - 24, 33), label, font=T.F_TEMP, fill=T.INK, anchor="rm")

        # Wi-Fi signal (top-left). Subtle when ambient; a red apex dot flags a
        # network drop. Hidden during voice so the waveform stays clean.
        if not voice_active:
            wifi = (ctx or {}).get("wifi") or {}
            self._wifi_icon(draw, 30, 46, wifi.get("quality", 0),
                            wifi.get("connected", False))

        f = 0.25 if voice_active else 1.0
        yb = 138 if voice_active else 196          # text baseline
        col = T.dim(T.INK, f)
        # HH:MM hero: digits carry a white→steel vertical gradient (dimmed flat
        # while a voice state animates over them), the colon carries the state
        # accent — the one place the accent lives on an idle home screen.
        hh, mm = now.strftime("%H"), now.strftime("%M")
        colon_col = T.dim(T.mix(accent, T.INK, 0.15), f)
        grad_top, grad_bot = (146, 158, 186), (246, 249, 255)
        x = _CLOCK_RIGHT - draw.textlength(f"{hh}:{mm}", font=T.F_CLOCK)
        for part, fill in ((hh, col), (":", colon_col), (mm, col)):
            if part != ":" and not voice_active:
                T.hero_text(img, (x, yb), part, T.F_CLOCK, grad_top, grad_bot)
            else:
                draw.text((x, yb), part, font=T.F_CLOCK, fill=fill, anchor="ls")
            x += draw.textlength(part, font=T.F_CLOCK)
        draw.text((_CLOCK_RIGHT + _CLK_GAP, yb), now.strftime("%S"),
                  font=T.F_CLOCK_S, fill=T.dim(col, 0.62), anchor="ls")

        playing = bool((ctx or {}).get("sat_playing"))
        bt_playing = bool(self._bt.get("playing"))
        media_active = playing or bt_playing
        # Date when ambient; hidden while audio plays (the now-playing pill + volume
        # slider take the space) or while a timer is ringing (the stop button does).
        if not voice_active and not media_active and not ringing:
            date_str = f"{_DAY_FR[now.weekday()]} {now.day} {_MON_FR[now.month]}"
            T.text_tracked(draw, T.CX, 238, date_str, T.F_MICRO, T.INK_DIM,
                           tracking=3.5)

        if ringing and not self.menu_open:
            # A finished timer takes over the lower band with a "say stop" hint.
            self._render_ring_hint(draw, img)
        elif not voice_active and not self.menu_open:
            self._status_pills(draw, img, ctx, accent, y=248 if playing else 280)
            if playing:
                self._home_volume(draw, ctx, accent)

        if self.menu_open:
            self._render_menu(draw, img, accent)

    def _sync_station(self, ctx):
        """Reconcile the optimistic station with HA's real playing state, so radio
        changes made by voice or the dashboard show up on screen too. HA's media
        content_id is authoritative; we honour a recent on-screen tap first since
        HA lags a few seconds behind."""
        if time.monotonic() - self._station_set_at < 6.0:
            return
        ctx = ctx or {}
        if not ctx.get("sat_playing"):
            self.active_station = None
            return
        cid = ((ctx.get("media") or {}).get("content_id") or "")
        for st in STATIONS:
            if st["url"] in cid:               # unambiguous: full stream URL match
                self.active_station = st["id"]
                return
        # Playing an unrecognised source (e.g. a voice response) — leave as-is.

    def _station_label(self):
        for st in STATIONS:
            if st["id"] == self.active_station:
                return st["label"]
        return None

    def _status_pills(self, draw, img, ctx, accent, y=280):
        """Tappable pills on home reflecting a running timer / playing radio."""
        pills = []
        timers = (ctx or {}).get("timers", [])
        if timers:
            r = max(0, timers[0].get("remaining_s", 0))
            m, s = divmod(r, 60)
            pills.append(("timer", f"{m}:{s:02d}" if m < 60 else f"{m//60}h{m%60:02d}"))
        if (ctx or {}).get("sat_playing"):
            pills.append(("radio", self._station_label() or "Radio"))
        if self._bt.get("playing"):
            pills.append(("bluetooth", _short(self._bt.get("title") or "Bluetooth", 20)))
        if not pills:
            return

        PAD, ICON, GAP, h = 16, 20, 12, 34
        widths = [int(PAD + ICON + 8 + draw.textlength(t, font=T.F_SMALL) + PAD)
                  for _, t in pills]
        # A round stop button rides beside the radio pill so playback can be killed
        # from home without a detour through the Radio screen.
        show_stop = any(k == "radio" for k, _ in pills)
        total = sum(widths) + GAP * (len(pills) - 1) + (GAP + h if show_stop else 0)
        x = T.CX - total // 2
        for (kind, txt), w in zip(pills, widths):
            box = (x, y, x + w, y + h)
            T.card(img, draw, box, radius=h // 2, fill=T.CARD_HI, elevate=False)
            icx, icy = x + PAD + ICON // 2, y + h // 2
            if kind == "radio":
                logo = T.station_icon(self.active_station, ICON)
                if logo is not None:
                    img.paste(logo, (icx - ICON // 2, icy - ICON // 2), logo)
                else:
                    draw.ellipse([icx - 9, icy - 9, icx + 9, icy + 9], outline=accent, width=2)
                    draw.polygon([(icx - 3, icy - 4), (icx - 3, icy + 4), (icx + 4, icy)], fill=accent)
                self._home_radio_box = box
            elif kind == "bluetooth":
                self._icon_bt(draw, icx, icy, accent, a=9, width=2)
                self._home_bt_box = box
            else:
                draw.ellipse([icx - 9, icy - 9, icx + 9, icy + 9], outline=accent, width=2)
                draw.line([icx, icy, icx, icy - 6], fill=accent, width=2)
                draw.line([icx, icy, icx + 4, icy], fill=accent, width=2)
                self._home_timer_box = box
            draw.text((x + PAD + ICON + 8, icy), txt, font=T.F_SMALL, fill=T.INK, anchor="lm")
            x += w + GAP
            if kind == "radio":
                sbox = (x, y, x + h, y + h)
                T.card(img, draw, sbox, radius=h // 2, fill=T.CARD_HI, elevate=False)
                scx, scy = x + h // 2, y + h // 2
                draw.rounded_rectangle([scx - 6, scy - 6, scx + 6, scy + 6], 2,
                                       fill=(255, 95, 72))
                # Slightly generous hit box (resistive panel), but padded away from
                # the pill on the left so a mis-tap opens Radio rather than stopping it.
                self._home_stop_box = (sbox[0], y - 8, sbox[2] + 10, y + h + 8)
                x += h + GAP

    def _home_volume(self, draw, ctx, accent):
        """Tappable volume slider on home, shown while audio plays."""
        vx0, vx1, vy = 90, 390, 298
        pct = self._volume(ctx)
        # small speaker glyph
        sx = 56
        draw.polygon([(sx - 6, vy - 5), (sx, vy - 5), (sx + 7, vy - 11),
                      (sx + 7, vy + 11), (sx, vy + 5), (sx - 6, vy + 5)], fill=T.INK_DIM)
        self._slider(draw, vx0, vx1, vy, pct, accent)
        draw.text((vx1 + 14, vy), f"{pct}%", font=T.F_SMALL, fill=T.INK_DIM, anchor="lm")
        self._home_vol_box = (vx0 - 12, vy - 22, vx1 + 12, vy + 22)

    def _render_ring_hint(self, draw, img):
        """Home hint while a timer is ringing. The sound is voice-only — saying
        the stop word is the thing that actually silences it — so this is a hint,
        not an action button. Tapping it only clears the finished timer card."""
        red = (255, 80, 60)
        T.text_center(draw, T.CX, 224, "Minuteur terminé", T.F_LABEL, red)
        box = (110, 252, 370, 304)
        T.card(img, draw, box, radius=18, fill=T.mix(T.CARD, red, 0.18),
               elevate=False)
        cy = (box[1] + box[3]) // 2
        self._icon_bell(draw, box[0] + 40, cy, red)
        T.text_center(draw, (box[0] + 60 + box[2]) // 2, cy, "Dites « stop »",
                      T.F_LABEL, T.INK, anchor="mm")

    def _icon_bell(self, draw, cx, cy, color):
        draw.pieslice([cx - 10, cy - 12, cx + 10, cy + 6], 180, 360, fill=color)
        draw.rectangle([cx - 12, cy + 4, cx + 12, cy + 8], fill=color)
        draw.ellipse([cx - 3, cy + 8, cx + 3, cy + 14], fill=color)

    def _render_menu(self, draw, img, accent):
        # The menu sits on a fresh background gradient (in place, keeps `draw`
        # valid) — any partial scrim leaves the giant clock glyphs ghosting
        # between the tiles, which reads as a rendering artifact, not as depth.
        img.paste(T.background(accent))
        if self.menu_confirm_off:
            self._render_confirm_off(draw, img, accent)
            return
        for box, icon, label, _target in MENU_CARDS:
            T.card(img, draw, box, radius=20, fill=T.CARD)
            cx = (box[0] + box[2]) // 2
            self._icon_chip(draw, cx, 152, accent, icon, r=32)
            T.text_center(draw, cx, 202, label, T.F_LABEL, T.INK)

        # Power-off button under the two cards (muted; not a primary action).
        red = (255, 120, 96)
        T.card(img, draw, OFF_BTN_BOX, radius=22, fill=T.CARD)
        cy = (OFF_BTN_BOX[1] + OFF_BTN_BOX[3]) // 2
        self._icon_power(draw, OFF_BTN_BOX[0] + 36, cy, red, r=12)
        draw.text((OFF_BTN_BOX[0] + 60, cy), "Éteindre", font=T.F_LABEL,
                  fill=T.INK_DIM, anchor="lm")

    def _icon_chip(self, draw, cx, cy, accent, kind, r=36):
        """A tinted disc behind a glyph — gives every icon a consistent home.

        One idiom for all three: outline glyphs, 3 px stroke, ~44 px optical
        box. Mixing an outline radio with a hairline timer and a chunky filled
        Bluetooth rune stopped the row reading as a set.
        """
        draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                     fill=T.mix(T.CARD_HI, accent, 0.22))
        glyph = T.lighten(accent, 0.55)   # bright glyph reads on the tinted disc
        if kind == "radio":
            self._icon_radio(draw, cx, cy + 1, glyph)
        elif kind == "bluetooth":
            self._icon_bt(draw, cx, cy, glyph, a=22, width=3)
        else:
            self._icon_timer(draw, cx, cy + 2, glyph)

    def _render_confirm_off(self, draw, img, accent):
        red = (255, 110, 90)
        T.card(img, draw, OFF_CARD_BOX, radius=22, fill=T.CARD)
        self._icon_power(draw, T.CX, 124, red, r=18)
        T.text_center(draw, T.CX, 158, "Éteindre le satellite ?", T.F_TITLE, T.INK)
        T.card(img, draw, OFF_CANCEL_BOX, radius=16, fill=T.CARD_HI, elevate=False)
        T.text_center(draw, (OFF_CANCEL_BOX[0] + OFF_CANCEL_BOX[2]) // 2,
                      (OFF_CANCEL_BOX[1] + OFF_CANCEL_BOX[3]) // 2,
                      "Annuler", T.F_LABEL, T.INK, anchor="mm")
        T.card(img, draw, OFF_CONFIRM_BOX, radius=16,
               fill=T.mix(T.CARD, red, 0.22), elevate=False)
        T.text_center(draw, (OFF_CONFIRM_BOX[0] + OFF_CONFIRM_BOX[2]) // 2,
                      (OFF_CONFIRM_BOX[1] + OFF_CONFIRM_BOX[3]) // 2,
                      "Éteindre", T.F_LABEL, T.lighten(red, 0.25), anchor="mm")

    # ── RADIO ─────────────────────────────────────────────────────────────────
    def _render_radio(self, draw, img, now, ctx, accent):
        self._header(draw, "Radio", now)
        # Highlight strictly the station we last started (no substring matching —
        # "rtl" is a substring of "rtl2"). Cleared when playback stops.
        playing = (ctx or {}).get("sat_playing")

        for i, st in enumerate(STATIONS):
            box = self._station_box(i)
            active = playing and self.active_station == st["id"]
            # Tile idiom: big centred logo over its name, like a wall of album
            # art. The playing tile gets the accent edge (an active-state
            # marker, not decoration) + CARD_HI + a small EQ in the corner.
            T.card(img, draw, box, radius=16,
                   fill=T.CARD_HI if active else T.CARD, elevate=False,
                   edge=accent if active else T.HAIRLINE)
            x0, y0, x1, y1 = box
            cx = (x0 + x1) // 2
            icon = T.station_icon(st["id"], 40)
            if icon is not None:
                img.paste(icon, (cx - 20, y0 + 12), icon)
            else:                                        # fallback: brand dot
                draw.ellipse([cx - 14, y0 + 18, cx + 14, y0 + 46], fill=st["color"])
            # Every label stays at full ink: dimming the inactive tiles made
            # the whole grid read as disabled.
            T.text_center(draw, cx, y0 + 60, st["label"], T.F_SMALL, T.INK)
            if active:
                self._icon_eq(draw, x1 - 18, y0 + 16, accent)

        # volume row: speaker glyph · slider · % — one inline row under the grid
        vx0, vx1, vy = 64, 322, 283
        pct = self._volume(ctx)
        sx = 32
        draw.polygon([(sx - 6, vy - 5), (sx, vy - 5), (sx + 7, vy - 11),
                      (sx + 7, vy + 11), (sx, vy + 5), (sx - 6, vy + 5)],
                     fill=T.INK_DIM)
        self._slider(draw, vx0, vx1, vy, pct, accent)
        draw.text((vx1 + 16, vy), f"{pct}%", font=T.F_SMALL,
                  fill=T.INK_DIM, anchor="lm")

        # Stop — the second most important control here, so it gets a red-tinted
        # surface and a labelled glyph rather than a grey square that reads as
        # disabled. Muted (but never invisible) when nothing is playing.
        red = (255, 95, 72)
        box = STOP_BTN_BOX
        T.card(img, draw, box, radius=18,
               fill=T.mix(T.CARD, red, 0.20 if playing else 0.07), elevate=False)
        scx = (box[0] + box[2]) // 2
        sq = red if playing else T.mix(T.INK_FAINT, red, 0.35)
        draw.rounded_rectangle([scx - 10, 261, scx + 10, 281], 3, fill=sq)
        T.text_center(draw, scx, 288, "Stop", T.F_SMALL,
                      T.INK if playing else T.INK_DIM)

    # ── TIMER ───────────────────────────────────────────────────────────────
    def _render_timer(self, draw, img, now, ctx, accent):
        self._header(draw, "Minuteur", now)
        if self.timer_custom:
            self._render_custom(draw, img, accent)
            return

        timers = (ctx or {}).get("timers", [])
        if timers:
            t0 = timers[0]
            key = t0.get("id") or t0.get("name", "timer")
            rem = max(0, t0.get("remaining_s", 0))
            self._timer_init[key] = max(self._timer_init.get(key, 0), rem)
            frac = rem / self._timer_init[key] if self._timer_init[key] else 0
            # Ring centred with Annuler stacked under it: the old left-ring /
            # floating-right-pill split left the screen visibly unbalanced.
            self._ring(draw, T.CX, 122, 58, frac, rem, t0.get("ringing"), accent)
            for j, tm in enumerate(timers[1:3]):
                r = max(0, tm.get("remaining_s", 0))
                m, s = divmod(r, 60)
                draw.text((W - 26, 84 + j * 30), f"• {m}:{s:02d}",
                          font=T.F_BODY, fill=T.INK_DIM, anchor="ra")
            self._cancel_btn(draw, img)
        else:
            T.text_center(draw, T.CX, 122, "Aucun minuteur", T.F_BODY, T.INK_DIM,
                          anchor="mm")

        # 4 quick presets + "Perso" (custom)
        for i in range(5):
            box = self._preset_box(i)
            cx = (box[0] + box[2]) // 2
            T.card(img, draw, box, radius=14, fill=T.CARD, elevate=False)
            if i < 4:
                draw.text((cx, box[1] + 11), str(TIMER_PRESETS[i]),
                          font=T.F_TITLE, fill=T.INK, anchor="ma")
                draw.text((cx, box[1] + 37), "min", font=T.F_SMALL,
                          fill=T.INK_DIM, anchor="ma")
            else:
                draw.text((cx, (box[1] + box[3]) // 2), "Perso",
                          font=T.F_LABEL, fill=T.lighten(accent, 0.4), anchor="mm")

    def _cancel_btn(self, draw, img):
        red = (255, 95, 72)
        box = CANCEL_BTN_BOX
        T.card(img, draw, box, radius=22, fill=T.mix(T.CARD, red, 0.16), elevate=False)
        cy = (box[1] + box[3]) // 2
        tw = draw.textlength("Annuler", font=T.F_LABEL)
        cx = int((box[0] + box[2]) / 2 - (22 + tw) / 2)   # cross + label as one group
        draw.line([cx - 8, cy - 8, cx + 8, cy + 8], fill=red, width=3)
        draw.line([cx - 8, cy + 8, cx + 8, cy - 8], fill=red, width=3)
        draw.text((cx + 22, cy), "Annuler", font=T.F_LABEL,
                  fill=T.INK, anchor="lm")

    def _render_custom(self, draw, img, accent):
        # big value
        T.text_center(draw, T.CX - 20, 120, str(self.custom_min), T.F_RING, T.INK, anchor="mm")
        draw.text((T.CX + 64, 120), "min", font=T.F_BODY, fill=T.INK_DIM, anchor="lm")
        # −1 / +1 round buttons (filled discs, bright glyphs)
        for cx2, plus in ((90, False), (390, True)):
            T.card(img, draw, (cx2 - 30, 90, cx2 + 30, 150), radius=30,
                   fill=T.CARD_HI, elevate=False)
            draw.line([cx2 - 12, 120, cx2 + 12, 120], fill=T.INK, width=3)
            if plus:
                draw.line([cx2, 108, cx2, 132], fill=T.INK, width=3)
        # −5 / +5 pills — sized for a resistive panel (they were 38 px tall next
        # to the 60 px ± discs directly above them, and easy to miss).
        for bx, label in ((STEP5_BOXES[0], "-5"), (STEP5_BOXES[1], "+5")):
            T.card(img, draw, bx, radius=15, fill=T.CARD, elevate=False)
            draw.text(((bx[0] + bx[2]) // 2, (bx[1] + bx[3]) // 2), label,
                      font=T.F_LABEL, fill=T.INK, anchor="mm")
        # Démarrer — the primary action gets a full accent fill, not a tint.
        self._primary_btn(img, draw, (110, 250, 370, 302), accent,
                          f"Démarrer · {self.custom_min} min")

    def _primary_btn(self, img, draw, box, accent, label):
        """Accent-filled pill — reserved for the single primary action of a
        screen. A faint top bevel keeps it from looking like a flat sticker."""
        x0, y0, x1, y1 = box
        r = (y1 - y0) // 2
        T.card(img, draw, box, radius=r, fill=accent, elevate=True,
               edge=T.lighten(accent, 0.18))
        T.text_center(draw, (x0 + x1) // 2, (y0 + y1) // 2, label,
                      T.F_LABEL, (255, 255, 255), anchor="mm")

    def _ring(self, draw, cx, cy, r, frac, rem, ringing, accent):
        col = (255, 70, 50) if ringing else accent
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=T.CARD_HI, width=10)
        frac = 1.0 if ringing else max(0.0, min(1.0, frac))
        end = -90 + 360 * frac
        draw.arc([cx - r, cy - r, cx + r, cy + r], -90, end, fill=col, width=10)
        # Rounded caps: a dot at 12 o'clock and one at the arc's live end.
        if 0.0 < frac < 1.0:
            for ang in (-90.0, end):
                a = math.radians(ang)
                ex, ey = cx + r * math.cos(a), cy + r * math.sin(a)
                draw.ellipse([ex - 5, ey - 5, ex + 5, ey + 5], fill=col)
        m, s = divmod(rem, 60)
        txt = f"{m}:{s:02d}" if m < 60 else f"{m//60}:{m%60:02d}:{s:02d}"
        # Fit the digits inside the ring's inner diameter (stroke is 10 px).
        fnt = T.F_RING
        while draw.textlength(txt, font=fnt) > 2 * r - 34 and fnt.size > 26:
            fnt = T.font("light", fnt.size - 4)
        T.text_center(draw, cx, cy, txt, fnt, T.INK, anchor="mm")

    # ── BLUETOOTH ─────────────────────────────────────────────────────────────
    def _render_bluetooth(self, draw, img, now, accent):
        discoverable = bool(self._bt.get("discoverable"))
        connected = self._bt.get("connected")
        self._header(draw, "Bluetooth", now)

        # Connection status card
        box = (24, 70, 456, 120)
        T.card(img, draw, box, radius=16, fill=T.CARD, elevate=False)
        cy = (box[1] + box[3]) // 2
        dot = (40, 220, 120) if connected else T.INK_FAINT
        draw.ellipse([box[0] + 20, cy - 6, box[0] + 32, cy + 6], fill=dot)
        self._icon_bt(draw, box[0] + 56, cy, T.INK_DIM, a=11, width=3)
        if connected:
            draw.text((box[0] + 78, cy), connected, font=T.F_LABEL,
                      fill=T.INK, anchor="lm")
            draw.text((box[2] - 18, cy), "Connecté", font=T.F_SMALL,
                      fill=T.mix(T.INK_DIM, (40, 220, 120), 0.5), anchor="rm")
        else:
            draw.text((box[0] + 78, cy), "Aucun appareil connecté",
                      font=T.F_LABEL, fill=T.INK_DIM, anchor="lm")

        # Primary action: make discoverable / stop (toggles the pairing window)
        if discoverable:
            rem = max(0, int(self._bt.get("pairing_remaining", 0)))
            m, s = divmod(rem, 60)
            T.card(img, draw, BT_PAIR_BTN_BOX, radius=18,
                   fill=T.mix(T.CARD_HI, accent, 0.30), elevate=False)
            bcx = (BT_PAIR_BTN_BOX[0] + BT_PAIR_BTN_BOX[2]) // 2
            T.text_center(draw, bcx, BT_PAIR_BTN_BOX[1] + 12,
                          f"Détectable · {m}:{s:02d}", T.F_LABEL, T.INK)
            T.text_center(draw, bcx, BT_PAIR_BTN_BOX[1] + 40,
                          "touchez pour arrêter", T.F_SMALL, T.INK_DIM)
            T.text_center(draw, T.CX, 240,
                          "Cherchez « pi-satellite » sur le téléphone",
                          T.F_SMALL, T.INK_DIM)
        else:
            self._primary_btn(img, draw, BT_PAIR_BTN_BOX, accent, "")
            bcx = (BT_PAIR_BTN_BOX[0] + BT_PAIR_BTN_BOX[2]) // 2
            bcy = (BT_PAIR_BTN_BOX[1] + BT_PAIR_BTN_BOX[3]) // 2
            self._icon_bt(draw, bcx - 78, bcy, (255, 255, 255), a=14, width=4)
            draw.text((bcx - 52, bcy), "Appairer un appareil", font=T.F_LABEL,
                      fill=(255, 255, 255), anchor="lm")
            T.text_center(draw, T.CX, 240,
                          "Rend le satellite détectable pendant 2 min",
                          T.F_SMALL, T.INK_DIM)

        # Now playing — fills the otherwise dead bottom third with the one thing
        # worth knowing here: what the connected phone is actually streaming.
        if self._bt.get("playing"):
            nb = (24, 264, 456, 312)
            T.card(img, draw, nb, radius=16, fill=T.CARD, elevate=False)
            ncy = (nb[1] + nb[3]) // 2
            self._icon_eq(draw, nb[0] + 28, ncy, accent)
            artist = _short(self._bt.get("artist") or "", 18)
            aw = draw.textlength(artist, font=T.F_SMALL) if artist else 0
            if artist:
                draw.text((nb[2] - 18, ncy), artist, font=T.F_SMALL,
                          fill=T.INK_DIM, anchor="rm")
            # Truncate the title to whatever the artist left free, never into it.
            title = self._bt.get("title") or "Lecture"
            avail = (nb[2] - 18 - aw - 14) - (nb[0] + 52)
            while len(title) > 1 and draw.textlength(title, font=T.F_LABEL) > avail:
                title = title[:-2] + "…"
            draw.text((nb[0] + 52, ncy), title, font=T.F_LABEL, fill=T.INK, anchor="lm")

    def _icon_bt(self, draw, cx, cy, color, a=15, width=3):
        """The Bluetooth rune as a single stroke (two right knees + left crossbars)."""
        d = a * 0.62
        q = a * 0.5
        pts = [(cx - d, cy - q), (cx + d, cy + q), (cx, cy + a),
               (cx, cy - a), (cx + d, cy - q), (cx - d, cy + q)]
        draw.line(pts, fill=color, width=width, joint="curve")

    # ── shared chrome ─────────────────────────────────────────────────────────
    def _header(self, draw, title, now):
        # Crisp drawn chevron (the font's "‹" renders soft and sits oddly).
        cx, cy = 32, 29
        draw.line([(cx + 7, cy - 11), (cx - 5, cy), (cx + 7, cy + 11)],
                  fill=T.INK, width=3, joint="curve")
        T.text_center(draw, T.CX, 14, title, T.F_TITLE, T.INK)
        draw.text((W - 18, 28), now.strftime("%H:%M"), font=T.F_CLOCK2,
                  fill=T.INK_DIM, anchor="rm")

    def _render_toast(self, draw):
        if time.monotonic() >= self._toast_until or not self._toast:
            return
        w, _ = T.text_size(draw, self._toast, T.F_LABEL)
        ICON = 24
        box = (T.CX - (w + ICON) // 2 - 20, H - 46,
               T.CX + (w + ICON) // 2 + 20, H - 12)
        fill = T.mix(T.CARD_HI, (255, 70, 55), 0.5) if self._toast_error else T.CARD_HI
        T.rounded(draw, box, 17, fill=fill)
        icx, icy = box[0] + 22, (box[1] + box[3]) // 2
        if self._toast_error:
            draw.line([icx, icy - 7, icx, icy + 2], fill=T.INK, width=3)
            draw.ellipse([icx - 1, icy + 5, icx + 2, icy + 8], fill=T.INK)
        else:
            draw.line([(icx - 7, icy), (icx - 2, icy + 5), (icx + 7, icy - 5)],
                      fill=(90, 220, 140), width=3, joint="curve")
        draw.text((icx + 14, icy), self._toast, font=T.F_LABEL,
                  fill=T.INK, anchor="lm")

    # ── menu icons ─────────────────────────────────────────────────────────────
    # All three menu glyphs share a stroke weight (3 px) and a ~44 px optical
    # box, and are drawn about their own centre so `_icon_chip` can place them.
    def _icon_radio(self, draw, cx, cy, accent):
        draw.rounded_rectangle([cx - 24, cy - 6, cx + 24, cy + 20], 5,
                               outline=accent, width=3)
        draw.line([cx - 14, cy - 6, cx + 5, cy - 22], fill=accent, width=3)
        draw.ellipse([cx + 5, cy + 1, cx + 19, cy + 15], outline=accent, width=3)

    def _icon_timer(self, draw, cx, cy, accent):
        draw.arc([cx - 21, cy - 19, cx + 21, cy + 23], 0, 360, fill=accent, width=3)
        draw.line([cx - 8, cy - 27, cx + 8, cy - 27], fill=accent, width=3)
        draw.line([cx, cy + 2, cx, cy - 10], fill=accent, width=3)

    def _slider(self, draw, x0, x1, y, pct, accent):
        """Rounded-cap track, accent fill, white knob with an accent ring."""
        pct = max(0, min(100, pct))
        fillx = x0 + int((x1 - x0) * pct / 100)
        draw.rounded_rectangle([x0, y - 3, x1, y + 3], 3, fill=T.CARD_HI)
        if fillx > x0 + 6:
            draw.rounded_rectangle([x0, y - 3, fillx, y + 3], 3, fill=accent)
        draw.ellipse([fillx - 10, y - 10, fillx + 10, y + 10], fill=accent)
        draw.ellipse([fillx - 7, y - 7, fillx + 7, y + 7], fill=T.INK)

    def _icon_eq(self, draw, cx, cy, color):
        """Three little bars — a 'now playing' mark."""
        for i, h in enumerate((7, 12, 9)):
            x = cx - 7 + i * 7
            draw.rounded_rectangle([x, cy - h, x + 3, cy + h], 1, fill=color)

    def _wifi_icon(self, draw, cx, cy, quality, connected):
        """Classic upward signal fan anchored at the apex dot (cx, cy). Lit arcs
        scale with link quality; offline shows faint arcs + a red dot."""
        bars = (1 + (quality >= 40) + (quality >= 70)) if connected else 0
        for i, r in enumerate((7, 14, 21)):
            lit = connected and bars > i
            draw.arc([cx - r, cy - r, cx + r, cy + r], 225, 315,
                     fill=T.INK_DIM if lit else T.INK_FAINT, width=3)
        draw.ellipse([cx - 2, cy - 2, cx + 2, cy + 2],
                     fill=T.INK_DIM if connected else (255, 90, 70))

    def _icon_power(self, draw, cx, cy, color, r=14):
        # Standard power symbol: ring open at the top + vertical stem.
        w = max(2, r // 5)
        draw.arc([cx - r, cy - r, cx + r, cy + r], -60, 240, fill=color, width=w)
        draw.line([cx, cy - r - w, cx, cy + 1], fill=color, width=w)
