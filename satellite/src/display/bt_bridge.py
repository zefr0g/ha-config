#!/usr/bin/env python3
"""
Bluetooth control bridge for the satellite speaker (voice-bt.service, root).

Runs as a standalone service so it can shell out to `bluetoothctl` / `busctl` —
the display daemon must never fork (subprocess races SPI DMA), so all Bluetooth
control is isolated here. The display talks to this bridge purely through two
files (see bt_actions.py):

  BT_STATUS_FILE  ← we write {discoverable, pairing_remaining, connected,
                              playing, title, artist}
  BT_CMD_FILE     → we read  "pair" | "stop"  (one line, deleted after read)

Runs as root (like voice-display.service) so it can consume the root-owned
command file in sticky /tmp.

"pair" makes the adapter discoverable + pairable for BT_PAIR_WINDOW seconds;
BlueZ auto-reverts via its own DiscoverableTimeout. A trusted phone reconnects
on its own and never needs this. Pairing is auto-accepted by bt-agent.service.

Playback metadata comes from BlueZ AVRCP (org.bluez.MediaPlayer1) via busctl —
the phone/laptop pushes Title/Artist/Status, no PipeWire introspection needed.
"""

import json
import os
import re
import signal
import subprocess
import sys
import time

sys.path.insert(0, "/home/dd/dev/voice-assistant/src")

from config import BT_STATUS_FILE, BT_CMD_FILE, BT_PAIR_WINDOW

IDLE_DT = 4.0   # bluetoothctl/busctl poll cadence when no pairing window is open
_PLAYER_RE = re.compile(r"/org/bluez/hci\d+/dev_[0-9A-F_]+/player\d+")


def _run(*args, timeout=5) -> str:
    """Run a command, return stdout ('' on failure)."""
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.stdout
    except Exception as e:
        print(f"[BT] {args[0] if args else '?'} failed: {e}", flush=True)
        return ""


def _btctl(*args) -> str:
    return _run("bluetoothctl", *args)


def _connected_device() -> str | None:
    for ln in _btctl("devices", "Connected").splitlines():
        parts = ln.split(maxsplit=2)            # "Device <mac> <name>"
        if len(parts) == 3 and parts[0] == "Device":
            return parts[2]
    return None


def _is_discoverable() -> bool:
    for ln in _btctl("show").splitlines():
        if "Discoverable:" in ln:
            return ln.strip().endswith("yes")
    return False


def _start_pairing():
    _btctl("discoverable-timeout", str(BT_PAIR_WINDOW))
    _btctl("pairable", "on")
    _btctl("discoverable", "on")


# ── AVRCP playback metadata (BlueZ org.bluez.MediaPlayer1 over busctl) ────────
def _mp_prop(path: str, name: str):
    """Read a MediaPlayer1 property as parsed JSON 'data', or None."""
    out = _run("busctl", "--system", "--json=short", "get-property",
               "org.bluez", path, "org.bluez.MediaPlayer1", name)
    try:
        return json.loads(out)["data"]
    except Exception:
        return None


def _avrcp() -> dict:
    """Active player status + track. Prefers a player reporting 'playing'."""
    res = {"playing": False, "title": None, "artist": None}
    paths = _PLAYER_RE.findall(_run("busctl", "--system", "tree", "org.bluez"))
    if not paths:
        return res
    chosen, status = paths[0], None
    for p in paths:
        st = _mp_prop(p, "Status")
        if st == "playing":
            chosen, status = p, st
            break
        if status is None:
            status = st
    res["playing"] = (status == "playing")
    track = _mp_prop(chosen, "Track")
    if isinstance(track, dict):
        res["title"] = (track.get("Title") or {}).get("data") or None
        res["artist"] = (track.get("Artist") or {}).get("data") or None
    return res


def _read_cmd() -> str | None:
    try:
        with open(BT_CMD_FILE) as f:
            cmd = f.read().strip()
        os.remove(BT_CMD_FILE)
        return cmd
    except FileNotFoundError:
        return None
    except Exception:
        return None


def _write_status(status: dict):
    tmp = BT_STATUS_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(status, f)
        os.replace(tmp, BT_STATUS_FILE)
    except Exception:
        pass


def main():
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    print("[BT] bridge starting", flush=True)
    pairing_until = 0.0
    last_poll = 0.0

    while True:
        now = time.monotonic()
        cmd = _read_cmd()
        if cmd == "pair":
            _start_pairing()
            pairing_until = now + BT_PAIR_WINDOW
            print(f"[BT] discoverable for {BT_PAIR_WINDOW}s", flush=True)
        elif cmd == "stop":
            _btctl("discoverable", "off")
            pairing_until = 0.0
            print("[BT] discoverable off", flush=True)

        # Poll at 1 Hz while a pairing window is open (live countdown + catch a
        # new connection); otherwise every IDLE_DT to keep idle CPU low. The
        # command file is still checked every second, so the button stays snappy.
        window = bool(pairing_until) and now < pairing_until
        if cmd or window or (now - last_poll) >= IDLE_DT:
            discoverable = _is_discoverable()
            if not discoverable:
                pairing_until = 0.0
            remaining = max(0, int(pairing_until - now)) if pairing_until else 0
            media = _avrcp()
            _write_status({
                "discoverable": discoverable,
                "pairing_remaining": remaining,
                "connected": _connected_device(),
                "playing": media["playing"],
                "title": media["title"],
                "artist": media["artist"],
            })
            last_poll = now
        time.sleep(1.0)


if __name__ == "__main__":
    main()
