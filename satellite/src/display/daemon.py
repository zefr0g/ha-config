#!/usr/bin/env python3
"""
Display daemon — single-threaded 10 FPS render loop.

State is read from /tmp/va_state written by voice-leds.service.
No threads, no subprocesses — SPI transfers are never racing anything.
"""

import signal
import sys
import time
from datetime import datetime

sys.path.insert(0, "/home/dd/dev/voice-assistant/src")

from config import STATE_INT, STATE_IDLE
from display.driver import GC9A01
from display.display_ui import render_frame, _read_wifi_dbm, media_scroll_text
from ha_context import fetch_ha_context

STATE_FILE = "/tmp/va_state"


def read_state() -> int:
    try:
        with open(STATE_FILE) as f:
            state_str = f.read().strip()
        return STATE_INT.get(state_str, STATE_IDLE)
    except Exception:
        return STATE_IDLE


def main():
    driver = GC9A01()

    def cleanup(sig=None, frame=None):
        print("\n[DISPLAY] Shutting down...")
        driver.close()
        sys.exit(0)

    signal.signal(signal.SIGINT,  cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print("[DISPLAY] Render loop starting at 10 FPS (no threads)")
    step          = 0
    wifi_dbm      = _read_wifi_dbm()
    ha_ctx        = fetch_ha_context()
    ha_fetch_mono = time.monotonic()
    slow_tick     = 0
    radio_offset  = 0
    _last_radio   = ""
    _scroll_frame = 0

    while True:
        t0 = time.monotonic()

        slow_tick += 1
        if slow_tick >= 50:       # refresh slow sensors every ~5s
            wifi_dbm      = _read_wifi_dbm()
            ha_ctx        = fetch_ha_context()
            ha_fetch_mono = time.monotonic()
            slow_tick     = 0
            wf = (ha_ctx or {}).get("watchface", "")
            if wf:
                try:
                    with open("/tmp/va_watchface", "w") as f:
                        f.write(wf)
                except OSError:
                    pass

        # Advance radio scroll offset every 8 frames (~0.8s per char)
        media = ha_ctx.get("media") if ha_ctx else None
        if media:
            radio_txt = media_scroll_text(media["title"], media["artist"])
            if radio_txt != _last_radio:
                radio_offset = 0
                _scroll_frame = 0
                _last_radio = radio_txt
            _scroll_frame += 1
            if _scroll_frame >= 8:
                radio_offset += 1
                _scroll_frame = 0
        else:
            radio_offset = 0
            _last_radio  = ""

        # Interpolate timer countdown locally between HA polls
        elapsed = time.monotonic() - ha_fetch_mono
        if ha_ctx and ha_ctx.get("timers"):
            render_ctx = {**ha_ctx, "timers": [
                {**t, "remaining_s": max(0, t["remaining_s"] - int(elapsed))}
                for t in ha_ctx["timers"]
            ]}
        else:
            render_ctx = ha_ctx

        current_state = read_state()
        vol_pct = (ha_ctx or {}).get("volume_pct", 50)
        frame = render_frame(step, current_state, datetime.now(), vol_pct, wifi_dbm, render_ctx, radio_offset)
        driver.blit_frame(frame)
        step += 1

        elapsed = time.monotonic() - t0
        time.sleep(max(0, 0.1 - elapsed))


if __name__ == "__main__":
    main()
