#!/usr/bin/env python3
"""
Display daemon — single-threaded loop driving the ST7796S 480×320 panel.

Each iteration: poll touch, refresh HA context (slow), render a full frame with
the UI controller, then diff it against what's on the panel and push only the
changed rectangle over SPI. Idle costs almost nothing (the diff is empty most
ticks); interactions and the voice waveform animate smoothly.

State (idle/listening/…) is read from /tmp/va_state written by voice-leds.service.
No threads, no subprocesses — SPI transfers never race anything.
"""

import json
import os
import shutil
import signal
import sys
import time
from datetime import datetime

import numpy as np

sys.path.insert(0, "/home/dd/dev/voice-assistant/src")

from config import STATE_INT, STATE_IDLE, DISPLAY_CONFIG_FILE
from display import theme as T
from display.driver import ST7796S
from display.touch import Touch
from display.app import App
from display.boot import BootScreen
from ha_context import fetch_ha_context

PANEL_READY = "/run/voice-display-panel-ready"   # written by the boot splash

STATE_FILE = "/tmp/va_state"
RING_FILE  = "/tmp/va_timer_ring"   # written by the LED daemon while a timer rings

_DISPLAY_DEFAULTS = {"brightness": 100, "contrast": 42, "gamma": "natural", "power": True}

POLL_HZ        = 20          # touch poll / animation cap
IDLE_RENDER_DT = 0.50        # idle re-render cadence (colon blinks at 1 Hz)

# ── Night dimming ───────────────────────────────────────────────────────────
# An ambient clock has no business glowing at day brightness in a dark room,
# and brightness was HA-only until now (you had to open a dashboard to fix it).
# The HA/MQTT brightness stays the *reference* level — this only scales it — so
# a manual change from HA still takes effect immediately, day or night.
NIGHT_START, NIGHT_END = 22, 7    # local hours [start, end) — dim overnight
NIGHT_FACTOR   = 0.35             # fraction of the configured brightness
NIGHT_FADE_MIN = 30               # minutes to ramp in/out at each boundary
WAKE_SECONDS   = 25               # full brightness after a touch, then fade back


def night_scale(now: datetime) -> float:
    """1.0 by day, NIGHT_FACTOR deep at night, linearly ramped at the edges."""
    mins = now.hour * 60 + now.minute + now.second / 60.0
    start, end, fade = NIGHT_START * 60, NIGHT_END * 60, NIGHT_FADE_MIN
    if start <= end:                       # (not our case, but keep it general)
        depth = 1.0 if start <= mins < end else 0.0
    else:                                  # window wraps midnight
        depth = 1.0 if (mins >= start or mins < end) else 0.0
    # Ramp across the boundaries instead of stepping.
    if depth:
        into = (mins - start) % 1440
        out_of = (end - mins) % 1440
        depth = min(1.0, into / fade, out_of / fade)
    return 1.0 - depth * (1.0 - NIGHT_FACTOR)


def read_state() -> int:
    try:
        with open(STATE_FILE) as f:
            return STATE_INT.get(f.read().strip(), STATE_IDLE)
    except Exception:
        return STATE_IDLE


def read_ring() -> bool:
    try:
        with open(RING_FILE) as f:
            return f.read().strip() == "1"
    except Exception:
        return False


def read_display_config() -> dict:
    try:
        with open(DISPLAY_CONFIG_FILE) as f:
            return {**_DISPLAY_DEFAULTS, **json.load(f)}
    except Exception:
        return dict(_DISPLAY_DEFAULTS)


def apply_display_config(driver, prev, curr):
    # Brightness is not applied here — it goes through the night-dim scaler in
    # the main loop, which owns the backlight and folds this value in.
    if curr["contrast"] != prev.get("contrast"):
        driver.contrast(curr["contrast"])
    if curr["gamma"] != prev.get("gamma"):
        driver.set_gamma(curr["gamma"])
    if curr["power"] != prev.get("power"):
        driver.display_power(curr["power"])


def blit_diff(driver, prev_arr, img):
    """Push only the bounding box of pixels that changed since the last frame."""
    new_arr = np.asarray(img)
    if prev_arr is None:
        driver.blit_frame(T.to_rgb565(img))
        return new_arr.copy()
    diff = np.any(new_arr != prev_arr, axis=2)
    if not diff.any():
        return prev_arr
    rows = np.where(diff.any(axis=1))[0]
    cols = np.where(diff.any(axis=0))[0]
    y0, y1, x0, x1 = int(rows[0]), int(rows[-1]), int(cols[0]), int(cols[-1])
    crop = img.crop((x0, y0, x1 + 1, y1 + 1))
    driver.blit_rect(T.to_rgb565(crop, (x0, y0)), x0, y0, x1, y1)
    return new_arr.copy()


def perform_poweroff(driver, touch):
    """Graceful system poweroff requested from the touch UI.

    Close the SPI/touch devices first so no transfer is in flight, then *replace*
    this process with `systemctl poweroff` via os.execv — execv does not fork, so
    it can't race SPI DMA (unlike subprocess.Popen, which is forbidden here).
    """
    print("[DISPLAY] UI requested poweroff — closing SPI, powering off", flush=True)
    try:
        touch.close()
    finally:
        driver.close()
    systemctl = shutil.which("systemctl") or "/usr/bin/systemctl"
    os.execv(systemctl, [systemctl, "poweroff"])


def interpolate_timers(ctx, since):
    """Tick timer countdowns locally between 5 s HA polls."""
    if not ctx or not ctx.get("timers"):
        return ctx
    dt = int(time.monotonic() - since)
    return {**ctx, "timers": [
        {**t, "remaining_s": max(0, t.get("remaining_s", 0) - dt)}
        for t in ctx["timers"]
    ]}


def run_boot_screen(driver, touch):
    """Live startup checklist, shown before anything that can block.

    This daemon starts several seconds ahead of the network, Docker and the
    voice assistant, so the first useful thing the panel can show is what boot
    is still waiting for. It also keeps the very first frame off the critical
    path of fetch_ha_context(), whose 3 s timeouts would otherwise stall the
    panel while the network is still coming up. A tap skips it.
    """
    boot = BootScreen()
    prev_arr = None
    sig = last_render = None
    while True:
        # Render on a change or once a second (the elapsed readout) — never
        # faster: every frame here competes with the boot it is reporting on.
        if sig != boot.signature() or last_render is None or \
                time.monotonic() - last_render >= 1.0:
            prev_arr = blit_diff(driver, prev_arr, boot.render())
            if last_render is None:
                with open("/proc/uptime") as f:
                    print(f"[BOOT] first frame at {float(f.read().split()[0]):.1f}s "
                          "uptime", flush=True)
            sig, last_render = boot.signature(), time.monotonic()
        if boot.finished() or touch.poll_tap():
            break
        time.sleep(0.25)
        boot.probe()
    return prev_arr


def main():
    # If the boot splash already brought the panel up, attach to it rather than
    # resetting — a reset here would blank the splash mid-boot.
    driver = ST7796S(init_panel=not os.path.exists(PANEL_READY))
    touch = Touch()

    # Honour the configured (night-scaled) brightness on the boot screen too —
    # a cold boot at 3am should not blast the room at full backlight.
    boot_cfg = read_display_config()
    driver.brightness(max(4, int(round(boot_cfg["brightness"] * night_scale(datetime.now())))))

    # First frame before App()/HA context: on screen in well under a second.
    boot_arr = run_boot_screen(driver, touch)

    app = App()

    def cleanup(sig=None, frame=None):
        print("\n[DISPLAY] Shutting down...")
        try:
            touch.close()
        finally:
            driver.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print("[DISPLAY] ST7796S UI loop starting", flush=True)
    ctx = fetch_ha_context()
    ctx_mono = time.monotonic()
    disp_cfg = read_display_config()
    apply_display_config(driver, {}, disp_cfg)

    prev_arr = boot_arr
    last_render = 0.0
    period = 1.0 / POLL_HZ
    last_tap_mono = 0.0          # for the touch-to-full-brightness window
    applied_bl = None            # backlight % currently on the panel

    while True:
        t0 = time.monotonic()

        tap = touch.poll_tap()
        if tap:
            last_tap_mono = t0
            app.handle_tap(tap[0], tap[1], ctx)

        if app.shutdown_requested:
            # Show the "Arrêt en cours…" splash, hold it briefly, then power off.
            img = app.render(read_state(), datetime.now(), ctx)
            blit_diff(driver, prev_arr, img)
            time.sleep(1.2)
            perform_poweroff(driver, touch)   # never returns

        if t0 - ctx_mono >= 5.0:
            ctx = fetch_ha_context()
            ctx_mono = t0

        new_cfg = read_display_config()
        if new_cfg != disp_cfg:
            apply_display_config(driver, disp_cfg, new_cfg)
            disp_cfg = new_cfg

        # Backlight = HA's level × night scale, briefly overridden to full by a
        # touch (with a short fade back so it doesn't snap).
        scale = night_scale(datetime.now())
        since_tap = t0 - last_tap_mono
        if since_tap < WAKE_SECONDS:
            scale = 1.0
        elif since_tap < WAKE_SECONDS + 4.0:
            k = (since_tap - WAKE_SECONDS) / 4.0
            scale = 1.0 + (scale - 1.0) * k
        target_bl = max(4, int(round(disp_cfg["brightness"] * scale)))
        if disp_cfg["brightness"] == 0:      # explicit "off" from HA stays off
            target_bl = 0
        if target_bl != applied_bl:
            driver.brightness(target_bl)
            applied_bl = target_bl

        state = read_state()
        animating = app.is_animating(state)
        ringing = read_ring()

        # Render when something moves, on a tap, while ringing, or on idle cadence.
        if tap or animating or ringing or (t0 - last_render) >= IDLE_RENDER_DT:
            render_ctx = {**interpolate_timers(ctx, ctx_mono), "timer_ringing": ringing}
            img = app.render(state, datetime.now(), render_ctx)
            prev_arr = blit_diff(driver, prev_arr, img)
            last_render = t0

        time.sleep(max(0, period - (time.monotonic() - t0)))


if __name__ == "__main__":
    main()
