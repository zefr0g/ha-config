"""ST7796S 4" TFT display driver — SPI0 with manual CS control, 480×320."""

import fcntl
import time
import spidev
import RPi.GPIO as GPIO

from config import SPI_DC, SPI_CS, SPI_RST, SPI_BLK, DISPLAY_SPI_SPEED

# Gamma presets — (positive_14_bytes, negative_14_bytes)
# These curves vary midtone slope and highlight rolloff; verify on hardware.
_GAMMA_PRESETS: dict[str, tuple[list, list]] = {
    "natural": (
        [0xF0, 0x04, 0x08, 0x04, 0x04, 0x18, 0x2E, 0x44, 0x42, 0x38, 0x14, 0x12, 0x18, 0x1C],
        [0xE0, 0x04, 0x08, 0x04, 0x04, 0x08, 0x28, 0x44, 0x41, 0x38, 0x14, 0x12, 0x18, 0x1C],
    ),
    "vivid": (
        # Steeper midtone, brighter highlights
        [0xF0, 0x06, 0x0C, 0x04, 0x04, 0x20, 0x35, 0x44, 0x48, 0x36, 0x10, 0x0E, 0x14, 0x18],
        [0xE0, 0x06, 0x0C, 0x04, 0x04, 0x10, 0x30, 0x44, 0x47, 0x36, 0x10, 0x0E, 0x14, 0x18],
    ),
    "soft": (
        # Gentle S-curve, lifted shadows, compressed highlights
        [0xF0, 0x02, 0x06, 0x06, 0x06, 0x14, 0x28, 0x44, 0x3E, 0x3A, 0x18, 0x16, 0x1C, 0x22],
        [0xE0, 0x02, 0x06, 0x06, 0x06, 0x06, 0x24, 0x44, 0x3D, 0x3A, 0x18, 0x16, 0x1C, 0x22],
    ),
    "warm": (
        # Slightly compressed toe for warmer shadow rendering
        [0xF0, 0x04, 0x08, 0x04, 0x04, 0x18, 0x2E, 0x3A, 0x42, 0x38, 0x14, 0x12, 0x18, 0x1C],
        [0xE0, 0x04, 0x08, 0x04, 0x04, 0x08, 0x28, 0x3A, 0x41, 0x38, 0x14, 0x12, 0x18, 0x1C],
    ),
}
GAMMA_OPTIONS = list(_GAMMA_PRESETS)


class ST7796S:
    def __init__(self):
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(SPI_DC,  GPIO.OUT)
        GPIO.setup(SPI_CS,  GPIO.OUT, initial=GPIO.HIGH)
        GPIO.setup(SPI_RST, GPIO.OUT)
        GPIO.setup(SPI_BLK, GPIO.OUT)

        self._pwm: GPIO.PWM | None = None

        self._spi = spidev.SpiDev()
        self._spi.open(0, 0)
        self._spi.max_speed_hz = DISPLAY_SPI_SPEED
        self._spi.mode = 0
        self._spi.no_cs = True  # CS controlled manually
        # Prevent fork-inherited fd from racing with SPI transfers (no subprocess
        # in this process, but defensive in case of future changes)
        fd = self._spi.fileno()
        fcntl.fcntl(fd, fcntl.F_SETFD, fcntl.fcntl(fd, fcntl.F_GETFD) | fcntl.FD_CLOEXEC)

        self._reset()
        self._init()
        self.backlight(True)

    def _reset(self):
        GPIO.output(SPI_RST, GPIO.LOW)
        time.sleep(0.1)
        GPIO.output(SPI_RST, GPIO.HIGH)
        time.sleep(0.12)

    def _cmd(self, c):
        GPIO.output(SPI_CS, GPIO.LOW)
        GPIO.output(SPI_DC, GPIO.LOW)
        self._spi.xfer2([c])
        GPIO.output(SPI_CS, GPIO.HIGH)

    def _data(self, d):
        GPIO.output(SPI_CS, GPIO.LOW)
        GPIO.output(SPI_DC, GPIO.HIGH)
        self._spi.xfer2(d if isinstance(d, list) else [d])
        GPIO.output(SPI_CS, GPIO.HIGH)

    def _init(self):
        c, d = self._cmd, self._data

        c(0x01)             # SWRESET
        time.sleep(0.12)
        c(0x11)             # SLPOUT
        time.sleep(0.12)

        c(0xF0); d(0xC3)    # Enable extension commands (page 1)
        c(0xF0); d(0x96)    # Enable extension commands (page 2)

        c(0x36); d(0xE8)    # MADCTL: MY+MX+MV+BGR — landscape 480×320, rotated 180°
        c(0x3A); d(0x55)    # COLMOD: 16-bit RGB565

        c(0xB4); d(0x01)    # DIC: 1-dot inversion
        c(0xB7); d(0xC6)    # Entry mode

        c(0xE8); d([0x40, 0x8A, 0x00, 0x00, 0x29, 0x19, 0xA5, 0x33])  # DOCA
        c(0xC1); d(0x06)    # PWR2
        c(0xC2); d(0xA7)    # PWR3
        c(0xC5); d(0x2A)    # VCMPCTL — raised from 0x18: deeper blacks, brighter whites
        time.sleep(0.02)

        # Positive gamma — steeper toe for deeper blacks, lifted shoulder for vivid highlights
        c(0xE0); d([0xF0, 0x04, 0x08, 0x04, 0x04, 0x18, 0x2E,
                    0x44, 0x42, 0x38, 0x14, 0x12, 0x18, 0x1C])
        # Negative gamma
        c(0xE1); d([0xE0, 0x04, 0x08, 0x04, 0x04, 0x08, 0x28,
                    0x44, 0x41, 0x38, 0x14, 0x12, 0x18, 0x1C])
        time.sleep(0.02)

        c(0xF0); d(0x3C)    # Disable extension commands (page 1)
        c(0xF0); d(0x69)    # Disable extension commands (page 2)

        c(0x20)             # INVOFF — this panel renders correctly without inversion
        c(0x13)             # NORON
        c(0x29)             # DISPON
        time.sleep(0.02)

    def _set_window(self, x0, y0, x1, y1):
        self._cmd(0x2A)
        self._data([x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF])   # CASET (cols)
        self._cmd(0x2B)
        self._data([y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF])   # RASET (rows)
        self._cmd(0x2C)                                        # RAMWR

    def _push(self, data: bytes):
        GPIO.output(SPI_CS, GPIO.LOW)
        GPIO.output(SPI_DC, GPIO.HIGH)
        # 64-byte chunks keep SPI in PIO mode — BCM2835 DMA kicks in above ~96 bytes
        # and conflicts with the I2S PCM DMA used by the audio subsystem.
        for i in range(0, len(data), 64):
            self._spi.writebytes2(data[i:i + 64])
        GPIO.output(SPI_CS, GPIO.HIGH)

    def blit_frame(self, rgb565_bytes):
        """Send a full 480×320 RGB565 frame. CS held LOW for the entire pixel transfer."""
        self._set_window(0, 0, 479, 319)
        self._push(bytes(rgb565_bytes))

    def blit_rect(self, rgb565_bytes, x0, y0, x1, y1):
        """Push a sub-window (x0,y0)-(x1,y1) inclusive. Only the changed region is
        sent over SPI — this is what keeps the render loop cheap at idle and the UI
        responsive. Caller guarantees len == (x1-x0+1)*(y1-y0+1)*2."""
        self._set_window(x0, y0, x1, y1)
        self._push(bytes(rgb565_bytes))

    def backlight(self, on: bool):
        GPIO.output(SPI_BLK, GPIO.HIGH if on else GPIO.LOW)

    def brightness(self, pct: int):
        """Set backlight brightness 0–100% via software PWM on GPIO23 (1 kHz).
        GPIO.PWM manages its own internal thread; it does not touch SPI."""
        pct = max(0, min(100, pct))
        if pct == 0:
            if self._pwm:
                self._pwm.stop()
                self._pwm = None
            GPIO.output(SPI_BLK, GPIO.LOW)
        elif self._pwm is None:
            self._pwm = GPIO.PWM(SPI_BLK, 1000)
            self._pwm.start(pct)
        else:
            self._pwm.ChangeDutyCycle(pct)

    def contrast(self, val: int):
        """Set VCMPCTL (0x00–0x7F). Higher = deeper blacks / brighter whites.
        Default from init: 0x2A (dec 42)."""
        val = max(0, min(0x7F, val))
        c, d = self._cmd, self._data
        c(0xF0); d(0xC3)
        c(0xF0); d(0x96)
        c(0xC5); d(val)
        c(0xF0); d(0x3C)
        c(0xF0); d(0x69)

    def set_gamma(self, preset: str):
        """Apply a named gamma preset. Unknown names fall back to 'natural'."""
        pos, neg = _GAMMA_PRESETS.get(preset, _GAMMA_PRESETS["natural"])
        c, d = self._cmd, self._data
        c(0xF0); d(0xC3)
        c(0xF0); d(0x96)
        c(0xE0); d(list(pos))
        c(0xE1); d(list(neg))
        c(0xF0); d(0x3C)
        c(0xF0); d(0x69)

    def display_power(self, on: bool):
        """DISPON (0x29) / DISPOFF (0x28) — panel soft on/off, daemon keeps running."""
        self._cmd(0x29 if on else 0x28)

    def close(self):
        self.display_power(False)
        if self._pwm:
            self._pwm.stop()
            self._pwm = None
        self._spi.close()
        GPIO.cleanup()
