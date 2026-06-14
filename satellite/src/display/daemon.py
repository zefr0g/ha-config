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
from ha_context import fetch_ha_context

STATE_FILE = "/tmp/va_state"
RING_FILE  = "/tmp/va_timer_ring"   # written by the LED daemon while a timer rings

_DISPLAY_DEFAULTS = {"brightness": 100, "contrast": 42, "gamma": "natural", "power": True}

POLL_HZ        = 20          # touch poll / animation cap
IDLE_RENDER_DT = 0.50        # idle re-render cadence (colon blinks at 1 Hz)


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
    if curr["brightness"] != prev.get("brightness"):
        driver.brightness(curr["brightness"])
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
    driver.blit_rect(T.to_rgb565(crop), x0, y0, x1, y1)
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


def main():
    driver = ST7796S()
    touch = Touch()
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

    print("[DISPLAY] ST7796S UI loop starting")
    ctx = fetch_ha_context()
    ctx_mono = time.monotonic()
    disp_cfg = read_display_config()
    apply_display_config(driver, {}, disp_cfg)

    prev_arr = None
    last_render = 0.0
    period = 1.0 / POLL_HZ

    while True:
        t0 = time.monotonic()

        tap = touch.poll_tap()
        if tap:
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
