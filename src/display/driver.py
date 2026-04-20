"""GC9A01 round TFT display driver — SPI with manual CS control."""

import fcntl
import time
import spidev
import RPi.GPIO as GPIO

from config import SPI_DC, SPI_CS, SPI_RST, SPI_BLK, DISPLAY_SPI_SPEED


class GC9A01:
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
        # Mark fd as close-on-exec so subprocess.Popen forks never inherit it,
        # which would cause SPI ioctl timeouts when the fork races with a transfer
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
        c(0xEF)
        c(0xEB); d(0x14)
        c(0xFE); c(0xEF)
        c(0xEB); d(0x14)
        c(0x84); d(0x40)
        c(0x85); d(0xFF)
        c(0x86); d(0xFF)
        c(0x87); d(0xFF)
        c(0x88); d(0x0A)
        c(0x89); d(0x21)
        c(0x8A); d(0x00)
        c(0x8B); d(0x80)
        c(0x8C); d(0x01)
        c(0x8D); d(0x01)
        c(0x8E); d(0xFF)
        c(0x8F); d(0xFF)
        c(0xB6); d([0x00, 0x20])
        c(0x36); d(0x08)
        c(0x3A); d(0x05)
        c(0x90); d([0x08, 0x08, 0x08, 0x08])
        c(0xBD); d(0x06)
        c(0xBC); d(0x00)
        c(0xFF); d([0x60, 0x01, 0x04])
        c(0xC3); d(0x13)
        c(0xC4); d(0x13)
        c(0xC9); d(0x22)
        c(0xBE); d(0x11)
        c(0xE1); d([0x10, 0x0E])
        c(0xDF); d([0x21, 0x0C, 0x02])
        c(0xF0); d([0x45, 0x09, 0x08, 0x08, 0x26, 0x2A])
        c(0xF1); d([0x43, 0x70, 0x72, 0x36, 0x37, 0x6F])
        c(0xF2); d([0x45, 0x09, 0x08, 0x08, 0x26, 0x2A])
        c(0xF3); d([0x43, 0x70, 0x72, 0x36, 0x37, 0x6F])
        c(0xED); d([0x1B, 0x0B])
        c(0xAE); d(0x77)
        c(0xCD); d(0x63)
        c(0x70); d([0x07, 0x07, 0x04, 0x0E, 0x0F, 0x09, 0x07, 0x08, 0x03])
        c(0xE8); d(0x34)
        c(0x62); d([0x18, 0x0D, 0x71, 0xED, 0x70, 0x70,
                    0x18, 0x0F, 0x71, 0xEF, 0x70, 0x70])
        c(0x63); d([0x18, 0x11, 0x71, 0xF1, 0x70, 0x70,
                    0x18, 0x13, 0x71, 0xF3, 0x70, 0x70])
        c(0x64); d([0x28, 0x29, 0xF1, 0x01, 0xF1, 0x00, 0x07])
        c(0x66); d([0x3C, 0x00, 0xCD, 0x67, 0x45, 0x45, 0x10, 0x00, 0x00, 0x00])
        c(0x67); d([0x00, 0x3C, 0x00, 0x00, 0x00, 0x01, 0x54, 0x10, 0x32, 0x98])
        c(0x74); d([0x10, 0x85, 0x80, 0x00, 0x00, 0x4E, 0x00])
        c(0x98); d([0x3E, 0x07])
        c(0x35)
        c(0x21)
        c(0x11); time.sleep(0.12)
        c(0x29); time.sleep(0.02)

    def blit_frame(self, rgb565_bytes):
        """Send a full 240×240 RGB565 frame. CS held LOW for the entire transfer."""
        self._cmd(0x2A)
        self._data([0x00, 0x00, 0x00, 0xEF])
        self._cmd(0x2B)
        self._data([0x00, 0x00, 0x00, 0xEF])
        self._cmd(0x2C)

        GPIO.output(SPI_CS, GPIO.LOW)
        GPIO.output(SPI_DC, GPIO.HIGH)
        # Use 64-byte chunks to stay in PIO mode (below BCM2835 DMA threshold).
        # Larger chunks trigger SPI DMA which conflicts with I2S PCM DMA when
        # the audio device is open (e.g. LVA container running).
        chunk = 64
        data = bytes(rgb565_bytes)
        for i in range(0, len(data), chunk):
            self._spi.writebytes2(data[i:i + chunk])
        GPIO.output(SPI_CS, GPIO.HIGH)

    def backlight(self, on: bool):
        GPIO.output(SPI_BLK, GPIO.HIGH if on else GPIO.LOW)

    def close(self):
        self.backlight(False)
        self._spi.close()
        GPIO.cleanup()
