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
    color = LED_COLORS["wake"]
    steps = 20
    for i in range(steps):
        if stop.is_set():
            return
        ring.set_all(*_scale(color, i / steps))
        time.sleep(0.4 / steps)
    ring.set_all(*color)
    stop.set()


def _breathe(stop, ring, color, period=2.5):
    steps = 40
    for i in range(steps):
        if stop.is_set():
            return
        t = i / steps
        factor = 0.15 + 0.85 * (math.sin(t * 2 * math.pi - math.pi / 2) + 1) / 2
        ring.set_all(*_scale(color, factor))
        time.sleep(period / steps)


def _rotate(stop, ring, color, step_s=0.25):
    """Single bright dot cycling 0→1→2→0, dim trail on previous LED."""
    for pos in range(LED_COUNT):
        if stop.is_set():
            return
        colors = [(0, 0, 0)] * LED_COUNT
        colors[pos] = color
        colors[(pos - 1) % LED_COUNT] = _scale(color, 0.15)
        ring.set_pixels(colors)
        time.sleep(step_s)


def _listening(stop, ring):
    _breathe(stop, ring, LED_COLORS["listening"], period=2.5)


def _processing(stop, ring):
    _rotate(stop, ring, LED_COLORS["processing"], step_s=0.22)


def _speaking(stop, ring):
    _breathe(stop, ring, LED_COLORS["speaking"], period=2.0)


def _error(stop, ring):
    color = LED_COLORS["error"]
    for _ in range(3):
        ring.set_all(*color)
        time.sleep(0.35)
        ring.clear()
        time.sleep(0.35)
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
