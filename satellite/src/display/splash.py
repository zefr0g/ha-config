#!/usr/bin/env python3
"""
Earliest-possible boot splash — raw RGB565 straight to the panel.

This runs as the first thing systemd starts (voice-splash.service, before
basic.target). It imports nothing but the SPI/GPIO driver: no numpy, no Pillow,
no theme, no fonts — those cost ~2s from a cold page cache and are the reason
the display daemon cannot paint before ~8s. The frame was rendered ahead of
time by make_splash.py, so all that happens here is a panel init and one
307200-byte push.

It leaves a marker so the daemon knows the panel is already initialised and can
skip its own reset — otherwise the daemon's SWRESET would blank the splash and
the screen would flash black halfway through boot.
"""

import os
import sys
import time

sys.path.insert(0, "/home/dd/dev/voice-assistant/src")

from display.driver import ST7796S

SPLASH = "/home/dd/dev/voice-assistant/assets/boot_splash.rgb565"
MARKER = "/run/voice-display-panel-ready"
SPIDEV = "/dev/spidev0.0"
FRAME_BYTES = 480 * 320 * 2
DEV_WAIT_S = 15.0


def wait_for_spidev(timeout: float = DEV_WAIT_S) -> bool:
    """Block until the SPI device node exists.

    This unit starts before sysinit, so spidev may not be bound yet — it is a
    module, not a devtmpfs node. Polling here (rather than ordering after some
    later target) means the splash paints the instant the bus is usable, and
    keeps working whenever the module happens to load.
    """
    deadline = time.monotonic() + timeout
    while not os.path.exists(SPIDEV):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.05)
    return True


def main():
    if not wait_for_spidev():
        print(f"[SPLASH] {SPIDEV} never appeared — giving up", flush=True)
        return 1

    try:
        with open(SPLASH, "rb") as f:
            frame = f.read()
    except OSError as e:
        print(f"[SPLASH] no splash frame ({e}) — run make_splash.py", flush=True)
        return 1
    if len(frame) != FRAME_BYTES:
        print(f"[SPLASH] bad frame size {len(frame)} != {FRAME_BYTES}", flush=True)
        return 1

    driver = ST7796S()
    driver.blit_frame(frame)
    # Backlight is a plain GPIO here, not PWM: a PWM duty cycle lives in a
    # thread that dies with this process. The daemon applies the real
    # (night-scaled) brightness when it takes over a few seconds later.
    driver.backlight(True)

    # Do NOT call GPIO.cleanup() — it would drive the backlight and reset pins
    # low on exit and blank the panel we just painted.
    with open(MARKER, "w") as f:
        f.write(str(os.getpid()))

    with open("/proc/uptime") as f:
        print(f"[SPLASH] on screen at {float(f.read().split()[0]):.2f}s uptime",
              flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
