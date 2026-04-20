"""
Home Assistant context polling — media player and voice timers.
Polled every ~5s by the display daemon's slow_tick.
"""

import json
import os
import urllib.request
import urllib.error

_HA_URL = "http://dd-ha:8123"
_TOKEN_FILE = "/home/dd/dev/voice-assistant/.ha_token"
_MEDIA_ENTITY = "media_player.enceinte_entree"
# device_id of the RPi satellite in HA
_SATELLITE_DEVICE_ID = "9d38634ac0aa71eb9f30c64630957c90"


def _token() -> str:
    try:
        with open(_TOKEN_FILE) as f:
            return f.read().strip()
    except Exception:
        return os.environ.get("HA_TOKEN", "")


def _headers() -> dict:
    return {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}


def _get(path: str):
    req = urllib.request.Request(f"{_HA_URL}{path}", headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _post(path: str, payload: dict):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(f"{_HA_URL}{path}", data=body, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _fetch_timers() -> list:
    """
    Call the built-in HA conversation agent (no LLM) to get active voice timers
    for the satellite device. Returns [{"name": str, "remaining_s": int}, ...].
    """
    data = _post("/api/conversation/process", {
        "text": "timer status",
        "language": "en",
        "agent_id": "conversation.home_assistant",
        "device_id": _SATELLITE_DEVICE_ID,
    })
    if not data:
        return []
    timers = (data.get("response", {})
                  .get("speech_slots", {})
                  .get("timers", []))
    result = []
    for t in timers:
        remaining = t.get("total_seconds_left", -1)
        is_active = t.get("is_active", False)
        # Include active timers and ringing timers (done but not yet dismissed)
        if is_active or remaining == 0:
            result.append({
                "name": t["name"],
                "remaining_s": remaining,
                "ringing": not is_active and remaining == 0,
            })
    return result


def fetch_ha_context() -> dict:
    """
    Returns:
        {
          "media": None | {"title": str, "artist": str},
          "timers": [{"name": str, "remaining_s": int}, ...],
        }
    """
    result: dict = {"media": None, "timers": []}

    if not _token():
        return result

    # Media player — single entity fetch
    state = _get(f"/api/states/{_MEDIA_ENTITY}")
    if state and state.get("state") == "playing":
        attrs = state.get("attributes", {})
        title = attrs.get("media_title") or attrs.get("media_station") or "Radio"
        artist = attrs.get("media_artist") or ""
        result["media"] = {"title": title, "artist": artist}

    # Voice timers via built-in conversation agent
    result["timers"] = _fetch_timers()

    return result
