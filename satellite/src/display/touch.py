"""
XPT2046 resistive touch controller (on the ST7796S module).

Wiring: shares SPI0 with the display but on chip-select CE1 (GPIO7); pen
interrupt on GPIO22 (active low). The display owns CE0 with manual CS, so the
two never transfer at the same time — the render loop is single-threaded and
polls touch only between frames.

The chip returns 12-bit raw ADC values; a one-time calibration maps them to
screen pixels. Calibration lives in CALIB_FILE (written by calibrate.py).
"""

import json
import time

import spidev
import RPi.GPIO as GPIO

from config import TOUCH_IRQ, DISPLAY_WIDTH, DISPLAY_HEIGHT

CALIB_FILE = "/home/dd/dev/voice-assistant/.touch_calib.json"

# XPT2046 control bytes (differential, 12-bit, PD=00 so PENIRQ stays enabled)
_CMD_X = 0xD0
_CMD_Y = 0x90
_CMD_Z1 = 0xB0
_CMD_Z2 = 0xC0

# Calibration is an affine map raw→screen per axis (least-squares fit through
# the 4 corner taps by calibrate.py). `swap` picks which raw axis feeds screen X.
#   screen_x = mx * (rawY if swap else rawX) + cx
#   screen_y = my * (rawX if swap else rawY) + cy
# Rough default for an uncalibrated landscape panel (raw ~200..3900):
_DEFAULT_CALIB = {
    "swap": True,
    "mx": (DISPLAY_WIDTH - 1) / 3700.0,  "cx": -200 * (DISPLAY_WIDTH - 1) / 3700.0,
    "my": (DISPLAY_HEIGHT - 1) / 3700.0, "cy": -200 * (DISPLAY_HEIGHT - 1) / 3700.0,
}


def load_calib() -> dict:
    try:
        with open(CALIB_FILE) as f:
            return {**_DEFAULT_CALIB, **json.load(f)}
    except Exception:
        return dict(_DEFAULT_CALIB)


class Touch:
    def __init__(self, calib: dict | None = None):
        self.calib = calib or load_calib()
        self._spi = spidev.SpiDev()
        self._spi.open(0, 1)               # bus 0, CE1
        self._spi.max_speed_hz = 1_000_000  # XPT2046 wants ≤ ~2 MHz
        self._spi.mode = 0

        GPIO.setup(TOUCH_IRQ, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        self._down = False          # debounced pen-down state
        self._down_since = 0.0
        self._last_xy = (0, 0)
        self._press_count = 0       # consecutive stable reads (debounce)

    # ── Raw reads ────────────────────────────────────────────────────────────
    def _read(self, cmd: int) -> int:
        r = self._spi.xfer2([cmd, 0x00, 0x00])
        return ((r[1] << 8) | r[2]) >> 3      # 12-bit

    def pressed(self) -> bool:
        return GPIO.input(TOUCH_IRQ) == 0

    def _read_raw(self) -> tuple[int, int] | None:
        """Median-filtered raw (x, y), or None if the read looks like noise.
        A real finger gives tightly-clustered samples; electrical noise (e.g.
        from the audio amp while radio plays) is erratic — reject wide spread."""
        xs, ys = [], []
        for _ in range(7):
            ys.append(self._read(_CMD_Y))
            xs.append(self._read(_CMD_X))
        xs.sort(); ys.sort()
        x, y = xs[len(xs) // 2], ys[len(ys) // 2]
        if x < 80 or x > 4000 or y < 80 or y > 4000:
            return None
        if (xs[-1] - xs[0]) > 350 or (ys[-1] - ys[0]) > 350:   # erratic = noise
            return None
        return x, y

    def _to_screen(self, x: int, y: int) -> tuple[int, int]:
        c = self.calib
        rsx = y if c["swap"] else x
        rsy = x if c["swap"] else y
        px = c["mx"] * rsx + c["cx"]
        py = c["my"] * rsy + c["cy"]
        return (int(max(0, min(DISPLAY_WIDTH - 1, px))),
                int(max(0, min(DISPLAY_HEIGHT - 1, py))))

    # ── Public: edge-triggered tap ─────────────────────────────────────────────
    def poll_tap(self) -> tuple[int, int] | None:
        """Call every loop. Returns (x, y) once, on the frame the finger lifts
        (release = tap). Returns None otherwise. Edge-triggered so a held finger
        fires exactly one tap."""
        now = time.monotonic()
        if self.pressed():
            raw = self._read_raw()
            if raw:
                self._last_xy = self._to_screen(*raw)
                self._press_count += 1
                if not self._down and self._press_count >= 2:   # debounce
                    self._down = True
                    self._down_since = now
            else:
                self._press_count = max(0, self._press_count - 1)
            return None

        # Pen up
        was_down = self._down
        self._down = False
        self._press_count = 0
        if was_down:
            held = now - self._down_since
            if 0.03 <= held <= 2.0:        # ignore spurious blips and long holds
                return self._last_xy
        return None

    def close(self):
        try:
            self._spi.close()
        except Exception:
            pass
