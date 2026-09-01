"""
Boot screen — live startup status on the panel while the rest of the box comes up.

The display daemon is deliberately the first service to start (see
docs/boot-tuning.md), so it is on screen several seconds before the network,
Docker or the voice assistant exist. Rather than showing a dead clock with no
data behind it, it shows what boot is actually waiting for, then hands over to
the normal UI once the voice stack answers.

Every probe here must be cheap and fork-free: no subprocess in this process
(fork races SPI DMA), and no call that can block the render loop for long.
Unit state is read from systemd's /run/systemd/units/invocation:<unit> marker
files, the local address straight off the interface via ioctl.
"""

import fcntl
import os
import socket
import struct
import time

from PIL import ImageDraw

from config import STATE_IDLE
from display import theme as T
from display.theme import W, H

HA_HOST, HA_PORT = "dd-ha", 8123
_WIFI_IF = "wlan0"
_SIOCGIFADDR = 0x8915

OK, PENDING = "ok", "pending"


def _unit_active(unit: str) -> bool:
    """True while systemd holds an invocation for the unit — no fork needed.

    lexists, not exists: the marker is a symlink whose target is the bare
    invocation ID, not a path, so it is always dangling by design.
    """
    return os.path.lexists(f"/run/systemd/units/invocation:{unit}")


def _iface_ip(name: str = _WIFI_IF):
    """Address of the interface itself — no traffic, no hard-coded peer."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        packed = fcntl.ioctl(s.fileno(), _SIOCGIFADDR,
                             struct.pack("256s", name.encode()[:15]))
        return socket.inet_ntoa(packed[20:24])
    except OSError:
        return None
    finally:
        s.close()


def _ha_reachable() -> bool:
    """Cheap TCP probe. Only called once we have an address, so DNS is up."""
    try:
        socket.create_connection((HA_HOST, HA_PORT), timeout=0.4).close()
        return True
    except OSError:
        return False


def _kernel() -> str:
    return os.uname().release


class BootScreen:
    """Startup checklist, held until the voice stack is up (or we stop waiting)."""

    # Ordered as boot actually resolves them.
    CHECKS = (
        ("sys",    "Système"),
        ("net",    "Réseau"),
        ("docker", "Docker"),
        ("lva",    "Assistant vocal"),
        ("ha",     "Home Assistant"),
    )

    def __init__(self, max_wait: float = 25.0):
        self.t0 = time.monotonic()
        self.max_wait = max_wait
        self.state = {k: PENDING for k, _ in self.CHECKS}
        self.detail = {k: "" for k, _ in self.CHECKS}
        # When each step flipped to OK — the panel doubles as a boot profiler.
        self.done_at = {}
        self._mark("sys", _kernel())
        self._ready_at = None
        self._last_probe = -1.0

    def _mark(self, key: str, detail: str = ""):
        if self.state[key] != OK:
            self.state[key] = OK
            self.done_at[key] = self.elapsed
        if detail:
            self.detail[key] = detail

    # ── status ───────────────────────────────────────────────────────────
    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.t0

    def probe(self):
        """Refresh the checklist. Rate-limited — the probes touch the network."""
        now = time.monotonic()
        if now - self._last_probe < 0.5:
            return
        self._last_probe = now

        ip = _iface_ip()
        if ip:
            self._mark("net", ip)

        for key, unit in (("docker", "docker.service"), ("lva", "lva.service")):
            if _unit_active(unit):
                self._mark(key)

        # Only probe HA once the interface has an address, so a DNS lookup
        # cannot stall the loop while the network is still coming up.
        if ip and self.state["ha"] != OK and _ha_reachable():
            self._mark("ha", HA_HOST)

        if all(v == OK for v in self.state.values()) and self._ready_at is None:
            self._ready_at = now

    def signature(self) -> tuple:
        """What is actually on screen, ignoring the elapsed-seconds readout."""
        return tuple(self.state[k] for k, _ in self.CHECKS)

    def finished(self) -> bool:
        """Everything up (held briefly so 'Prêt' is read), or we stop waiting.

        The timeout matters: if HA itself is down, the checklist must not hold
        the normal UI hostage — the satellite is still usable without it.
        """
        if self._ready_at is not None:
            return time.monotonic() - self._ready_at > 1.2
        return self.elapsed > self.max_wait

    # ── render ───────────────────────────────────────────────────────────
    def render(self):
        accent = T.ACCENT[STATE_IDLE]
        done = sum(1 for v in self.state.values() if v == OK)
        total = len(self.CHECKS)
        ready = done == total

        img = T.background(accent)
        draw = ImageDraw.Draw(img)

        draw.text((28, 24), socket.gethostname(), font=T.F_TITLE, fill=T.INK)
        draw.text((28, 56), "Démarrage" if not ready else "Prêt",
                  font=T.F_SMALL, fill=accent if ready else T.INK_DIM)
        draw.text((W - 28, 30), f"{self.elapsed:4.1f} s", font=T.F_BODY,
                  fill=T.INK_DIM, anchor="ra")

        box = (24, 86, W - 24, 258)
        T.card(img, draw, box)

        x0, y0 = box[0] + 22, box[1] + 18
        row_h = 30
        for i, (key, label) in enumerate(self.CHECKS):
            y = y0 + i * row_h
            ok = self.state[key] == OK
            colour = accent if ok else T.INK_FAINT
            cy = y + 11
            if ok:
                draw.ellipse([x0, cy - 6, x0 + 12, cy + 6], fill=colour)
                draw.line([(x0 + 3, cy), (x0 + 5, cy + 3), (x0 + 9, cy - 3)],
                          fill=T.BG_BOTTOM, width=2)
            else:
                # Static hollow dot, deliberately not animated: this runs while
                # the rest of the box is still booting, and an animated frame
                # re-blits a large bounding box every tick — enough SD/CPU
                # contention to measurably delay the boot it is reporting on.
                draw.ellipse([x0, cy - 6, x0 + 12, cy + 6],
                             outline=T.INK_FAINT, width=2)
            draw.text((x0 + 26, y), label, font=T.F_BODY,
                      fill=T.INK if ok else T.INK_DIM)
            # Right of each row: what it resolved to, then how long it took.
            if key in self.done_at:
                draw.text((box[2] - 22, y + 2), f"{self.done_at[key]:.1f} s",
                          font=T.F_SMALL, fill=T.INK_FAINT, anchor="ra")
            if self.detail[key]:
                draw.text((box[2] - 84, y + 2), self.detail[key], font=T.F_SMALL,
                          fill=T.INK_FAINT, anchor="ra")

        # Progress bar — fraction of checks answered.
        bx0, bx1, by = 24, W - 24, 282
        draw.rounded_rectangle([bx0, by, bx1, by + 8], radius=4, fill=T.CARD)
        width = int((bx1 - bx0) * done / total)
        if width > 8:
            draw.rounded_rectangle([bx0, by, bx0 + width, by + 8], radius=4,
                                   fill=accent if ready else T.mix(accent, T.CARD_HI, 0.35))
        draw.text((bx0, by + 16), f"{done}/{total}", font=T.F_SMALL, fill=T.INK_FAINT)
        return img
