#!/usr/bin/env python3
"""
Touch calibration for the XPT2046.

Run with the display daemon stopped (it owns the SPI bus + GPIO):

    sudo systemctl stop voice-display.service
    sudo python3 /home/dd/dev/voice-assistant/src/display/calibrate.py
    sudo systemctl start voice-display.service

Touch the white target each time it appears (4 corners). The script reads the
raw ADC values, brute-forces the axis swap/flip and min/max that best map the
corners onto the screen, and writes them to touch.CALIB_FILE.
"""

import json
import sys
import time

sys.path.insert(0, "/home/dd/dev/voice-assistant/src")

import numpy as np
from PIL import Image, ImageDraw

from config import DISPLAY_WIDTH as W, DISPLAY_HEIGHT as H
from display import theme as T
from display.driver import ST7796S
from display.touch import Touch, CALIB_FILE

TARGETS = [(40, 40), (W - 40, 40), (W - 40, H - 40), (40, H - 40)]


def draw_target(driver, pt, idx, total):
    img = Image.new("RGB", (W, H), (6, 8, 14))
    d = ImageDraw.Draw(img)
    x, y = pt
    d.line([x - 18, y, x + 18, y], fill=(255, 255, 255), width=2)
    d.line([x, y - 18, x, y + 18], fill=(255, 255, 255), width=2)
    d.ellipse([x - 12, y - 12, x + 12, y + 12], outline=(0, 200, 255), width=2)
    T.text_center(d, W // 2, H // 2 - 20,
                  f"Touchez la cible  ({idx}/{total})", T.F_LABEL, (220, 226, 240))
    driver.blit_frame(T.to_rgb565(img))


def read_point(touch) -> tuple[int, int]:
    # wait for a stable press
    while not touch.pressed():
        time.sleep(0.01)
    time.sleep(0.08)
    xs, ys = [], []
    while touch.pressed() and len(xs) < 40:
        raw = touch._read_raw()
        if raw:
            xs.append(raw[0]); ys.append(raw[1])
        time.sleep(0.01)
    while touch.pressed():            # wait for release
        time.sleep(0.01)
    xs.sort(); ys.sort()
    return xs[len(xs) // 2], ys[len(ys) // 2]


def _fit(raw_vals, screen_vals):
    """Least-squares screen = m*raw + c; returns (m, c, sum_sq_residual)."""
    m, c = np.polyfit(raw_vals, screen_vals, 1)
    resid = float(np.sum((np.array(raw_vals) * m + c - np.array(screen_vals)) ** 2))
    return float(m), float(c), resid


def solve(raws):
    """Pick the axis assignment (swap) and fit an affine map for each screen axis
    directly through the known target coordinates — accurate even though the
    targets are inset from the screen edges."""
    rx = [r[0] for r in raws]
    ry = [r[1] for r in raws]
    sx = [t[0] for t in TARGETS]
    sy = [t[1] for t in TARGETS]
    best, best_err = None, 1e18
    for swap in (False, True):
        rsx = ry if swap else rx       # raw axis that drives screen X
        rsy = rx if swap else ry       # raw axis that drives screen Y
        mx, cx, e1 = _fit(rsx, sx)
        my, cy, e2 = _fit(rsy, sy)
        if e1 + e2 < best_err:
            best_err = e1 + e2
            best = {"swap": swap, "mx": mx, "cx": cx, "my": my, "cy": cy}
    rms = (best_err / (2 * len(raws))) ** 0.5
    return best, rms


def main():
    driver = ST7796S()
    touch = Touch()
    print("[CAL] Touch each target as it appears...")
    raws = []
    for i, pt in enumerate(TARGETS):
        draw_target(driver, pt, i + 1, len(TARGETS))
        time.sleep(0.4)
        r = read_point(touch)
        print(f"[CAL] target {pt} -> raw {r}")
        raws.append(r)

    cal, rms = solve(raws)
    with open(CALIB_FILE, "w") as f:
        json.dump(cal, f, indent=2)
    print(f"[CAL] wrote {CALIB_FILE}: {cal}")
    print(f"[CAL] corner RMS error ≈ {rms:.0f}px (lower is better)")

    # quick confirmation screen
    img = Image.new("RGB", (W, H), (6, 8, 14))
    d = ImageDraw.Draw(img)
    T.text_center(d, W // 2, H // 2 - 10, "Calibration enregistrée", T.F_TITLE, (220, 226, 240))
    driver.blit_frame(T.to_rgb565(img))
    time.sleep(1.5)
    driver.close()
    touch.close()


if __name__ == "__main__":
    main()
