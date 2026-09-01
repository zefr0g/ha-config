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

from config import (BT_STATUS_FILE, BT_CMD_FILE, BT_PAIR_WINDOW, BT_DUCK_LEVEL,
                    BT_DUCK_STATES, BT_DUCK_MAX_SECONDS, BT_TICK, VA_STATE_FILE)

IDLE_DT = 4.0   # bluetoothctl/busctl poll cadence when no pairing window is open
_PLAYER_RE = re.compile(r"/org/bluez/hci\d+/dev_[0-9A-F_]+/player\d+")
_VOL_RE = re.compile(r"Volume:\s*([\d.]+)")

# This service runs as root but PipeWire belongs to user dd, so pw-dump/wpctl
# need to be pointed at dd's runtime dir to find the socket (same trick the LVA
# container uses via PULSE_SERVER).
PW_ENV = {**os.environ, "XDG_RUNTIME_DIR": "/run/user/1000"}


def _run(*args, timeout=5, env=None) -> str:
    """Run a command, return stdout ('' on failure)."""
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                           env=env)
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


# ── Ducking: drop the phone's stream while the assistant is active ───────────
def _bt_node_id() -> str | None:
    """PipeWire node id of the phone's A2DP stream.

    Resolved fresh on every duck: the node only exists while audio is actually
    playing, so a cached id goes stale the moment the phone pauses.
    """
    try:
        for o in json.loads(_run("pw-dump", timeout=8, env=PW_ENV)):
            if o.get("type") != "PipeWire:Interface:Node":
                continue
            props = (o.get("info") or {}).get("props") or {}
            if str(props.get("node.name", "")).startswith("bluez_input"):
                return str(o["id"])
    except Exception:
        pass
    return None


def _get_volume(node_id: str) -> float | None:
    m = _VOL_RE.search(_run("wpctl", "get-volume", node_id, env=PW_ENV))
    return float(m.group(1)) if m else None


def _set_volume(node_id: str, vol: float) -> None:
    _run("wpctl", "set-volume", node_id, f"{vol:.2f}", env=PW_ENV)


def _read_va_state() -> str:
    try:
        with open(VA_STATE_FILE) as f:
            return f.read().strip()
    except Exception:
        return ""


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
    # Restore the music on the way out, or stopping the service mid-run would
    # leave the phone stuck at duck level with nothing left to undo it.
    ducked: tuple[str, float] | None = None

    def _bail(*_):
        if ducked:
            _set_volume(ducked[0], ducked[1])
        sys.exit(0)

    signal.signal(signal.SIGTERM, _bail)
    print("[BT] bridge starting", flush=True)
    pairing_until = 0.0
    last_poll = 0.0
    ducked_at = 0.0
    duck_inhibit = False

    while True:
        now = time.monotonic()

        # ── Duck / restore on assistant state ────────────────────────────────
        va_state = _read_va_state()
        active = va_state in BT_DUCK_STATES
        if not active:
            duck_inhibit = False        # fresh run may duck again
        if active and ducked is None and not duck_inhibit:
            nid = _bt_node_id()
            vol = _get_volume(nid) if nid else None
            # Only duck if it would actually lower something — and remember the
            # pre-duck level so a phone-side volume change is restored faithfully.
            if nid and vol is not None and vol > BT_DUCK_LEVEL:
                _set_volume(nid, BT_DUCK_LEVEL)
                ducked, ducked_at = (nid, vol), now
                print(f"[BT] duck {vol:.2f} → {BT_DUCK_LEVEL:.2f} ({va_state})",
                      flush=True)
        elif ducked is not None and (
                not active or (now - ducked_at) > BT_DUCK_MAX_SECONDS):
            timed_out = active          # still "active" → the state file is stuck
            _set_volume(ducked[0], ducked[1])
            print(f"[BT] restore {ducked[1]:.2f}"
                  f"{' (timeout)' if timed_out else ''}", flush=True)
            ducked = None
            # Latch after a timeout, or we would re-duck on the very next tick
            # and cycle every BT_DUCK_MAX_SECONDS until the state file moves.
            duck_inhibit = timed_out

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
        # command file and the VA state are read every tick (BT_TICK), so the
        # button stays snappy and ducking is effectively instant — both are
        # small local file reads, unlike the bluetoothctl/busctl calls below.
        window = bool(pairing_until) and now < pairing_until
        if cmd or (now - last_poll) >= (1.0 if window else IDLE_DT):
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
        time.sleep(BT_TICK)


if __name__ == "__main__":
    main()
