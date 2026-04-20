"""Thread-safe WS2812B LED ring wrapper."""

import threading
from rpi_ws281x import PixelStrip, Color
from config import LED_PIN, LED_COUNT, LED_DMA, LED_FREQ_HZ, LED_INVERT, LED_CHANNEL, LED_BRIGHTNESS


class LEDRing:
    def __init__(self, brightness=LED_BRIGHTNESS):
        self._strip = PixelStrip(
            LED_COUNT, LED_PIN, LED_FREQ_HZ,
            LED_DMA, LED_INVERT, brightness, LED_CHANNEL,
        )
        self._strip.begin()
        self._lock = threading.Lock()

    def set_all(self, r, g, b):
        with self._lock:
            for i in range(LED_COUNT):
                self._strip.setPixelColor(i, Color(r, g, b))
            self._strip.show()

    def set_pixel(self, i, r, g, b):
        with self._lock:
            self._strip.setPixelColor(i, Color(r, g, b))
            self._strip.show()

    def set_pixels(self, colors):
        """Set all pixels at once. colors: list of (r,g,b) tuples, length LED_COUNT."""
        with self._lock:
            for i, (r, g, b) in enumerate(colors):
                self._strip.setPixelColor(i, Color(r, g, b))
            self._strip.show()

    def clear(self):
        self.set_all(0, 0, 0)
