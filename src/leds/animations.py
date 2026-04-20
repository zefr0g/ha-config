"""Non-blocking per-state LED strip animations (3-LED K2000 style)."""

import math
import threading
import time
from config import LED_COUNT, LED_COLORS


def _scale(color, factor):
    return tuple(max(0, min(255, int(c * factor))) for c in color)


def _run(stop_event, fn, *args):
    while not stop_event.is_set():
        fn(stop_event, *args)


def _idle(stop, ring):
    ring.clear()
    stop.wait()


def _wake(stop, ring):
    ring.set_all(*LED_COLORS["wake"])
    time.sleep(0.3)
    ring.set_all(*LED_COLORS["idle"])
    stop.set()


def _kitt(stop, ring, color, step_ms=0.08):
    """K2000 bouncing scanner: bright center pixel, dim neighbours."""
    # positions: 0→1→2→1→0→...
    sequence = list(range(LED_COUNT)) + list(range(LED_COUNT - 2, 0, -1))
    for pos in sequence:
        if stop.is_set():
            return
        colors = [(0, 0, 0)] * LED_COUNT
        colors[pos] = color
        if pos > 0:
            colors[pos - 1] = _scale(color, 0.2)
        if pos < LED_COUNT - 1:
            colors[pos + 1] = _scale(color, 0.2)
        ring.set_pixels(colors)
        time.sleep(step_ms)


def _listening(stop, ring):
    _kitt(stop, ring, LED_COLORS["listening"], step_ms=0.20)


def _processing(stop, ring):
    _kitt(stop, ring, LED_COLORS["processing"], step_ms=0.13)


def _speaking(stop, ring):
    color = LED_COLORS["speaking"]
    period = 1.2
    steps = 30
    for i in range(steps):
        if stop.is_set():
            return
        t = i / steps
        factor = 0.3 + 0.7 * (math.sin(t * 2 * math.pi - math.pi / 2) + 1) / 2
        ring.set_all(*_scale(color, factor))
        time.sleep(period / steps)


def _error(stop, ring):
    color = LED_COLORS["error"]
    for _ in range(3):
        ring.set_all(*color)
        time.sleep(0.2)
        ring.clear()
        time.sleep(0.2)
    stop.set()


_ANIMATION_FN = {
    "idle":       _idle,
    "wake":       _wake,
    "listening":  _listening,
    "processing": _processing,
    "speaking":   _speaking,
    "error":      _error,
}


class AnimationController:
    def __init__(self, ring):
        self._ring = ring
        self._stop  = threading.Event()
        self._thread = None

    def set_state(self, state):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

        fn = _ANIMATION_FN.get(state, _ANIMATION_FN["idle"])
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=_run, args=(self._stop, fn, self._ring), daemon=True
        )
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        self._ring.clear()
