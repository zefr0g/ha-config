"""
Bluetooth status reader + pairing trigger for the touch UI.

The display process must never fork, so it cannot run bluetoothctl directly.
It reads the status JSON written by bt_bridge.py (voice-bt.service) and requests
pairing by writing a one-line command file the bridge consumes. Both are plain
file ops — safe inside the single-threaded render loop.
"""

import json
import os

from config import BT_STATUS_FILE, BT_CMD_FILE

_DEFAULT = {"discoverable": False, "pairing_remaining": 0, "connected": None,
            "playing": False, "title": None, "artist": None}


def read_bt_status() -> dict:
    try:
        with open(BT_STATUS_FILE) as f:
            return {**_DEFAULT, **json.load(f)}
    except Exception:
        return dict(_DEFAULT)


def _write_cmd(cmd: str) -> bool:
    tmp = BT_CMD_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            f.write(cmd)
        os.replace(tmp, BT_CMD_FILE)
        return True
    except Exception:
        return False


def request_pairing() -> bool:
    return _write_cmd("pair")


def stop_pairing() -> bool:
    return _write_cmd("stop")
