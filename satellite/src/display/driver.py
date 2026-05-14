"""ST7796S 4" TFT display driver — SPI0 with manual CS control, 480×320."""

import fcntl
import time
import spidev
import RPi.GPIO as GPIO

from config import SPI_DC, SPI_CS, SPI_RST, SPI_BLK, DISPLAY_SPI_SPEED


class ST7796S:
    def __init__(self):
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(SPI_DC,  GPIO.OUT)
        GPIO.setup(SPI_CS,  GPIO.OUT, initial=GPIO.HIGH)
        GPIO.setup(SPI_RST, GPIO.OUT)
        GPIO.setup(SPI_BLK, GPIO.OUT)

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

        c(0x36); d(0x28)    # MADCTL: MV=1 (landscape 480×320) + BGR panel order
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

    def blit_frame(self, rgb565_bytes):
        """Send a full 480×320 RGB565 frame. CS held LOW for the entire pixel transfer."""
        self._cmd(0x2A)
        self._data([0x00, 0x00, 0x01, 0xDF])   # CASET: col 0..479
        self._cmd(0x2B)
        self._data([0x00, 0x00, 0x01, 0x3F])   # RASET: row 0..319
        self._cmd(0x2C)

        GPIO.output(SPI_CS, GPIO.LOW)
        GPIO.output(SPI_DC, GPIO.HIGH)
        # 64-byte chunks keep SPI in PIO mode — BCM2835 DMA kicks in above ~96 bytes
        # and conflicts with the I2S PCM DMA used by the audio subsystem.
        data = bytes(rgb565_bytes)
        for i in range(0, len(data), 64):
            self._spi.writebytes2(data[i:i + 64])
        GPIO.output(SPI_CS, GPIO.HIGH)

    def backlight(self, on: bool):
        GPIO.output(SPI_BLK, GPIO.HIGH if on else GPIO.LOW)

    def close(self):
        self.backlight(False)
        self._spi.close()
        GPIO.cleanup()
