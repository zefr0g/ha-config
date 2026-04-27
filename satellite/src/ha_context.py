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
_SATELLITE_ENTITY = "media_player.rpi_satellite_media_player"
_WATCHFACE_ENTITY = "input_select.rpi_watchface"
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


def _fetch_active_radio_station() -> str | None:
    """
    Return the friendly_name of the most recently triggered radio script,
    or None if no radio script has run more recently than arreter_radio.
    """
    from datetime import timezone

    states = _get("/api/states") or []
    radio: list[dict] = []
    stop_ts = None

    for s in states:
        eid = s.get("entity_id", "")
        if eid == "script.arreter_radio":
            ts = s.get("attributes", {}).get("last_triggered")
            if ts:
                stop_ts = ts
        elif eid.startswith("script.radio_"):
            ts = s.get("attributes", {}).get("last_triggered")
            if ts:
                name = s.get("attributes", {}).get("friendly_name", eid)
                radio.append({"name": name, "ts": ts})

    if not radio:
        return None

    radio.sort(key=lambda x: x["ts"], reverse=True)
    latest = radio[0]
    if stop_ts and stop_ts >= latest["ts"]:
        return None  # radio was stopped after the last play
    return latest["name"]


def fetch_ha_context() -> dict:
    """
    Returns:
        {
          "media":      None | {"title": str, "artist": str},
          "timers":     [{"name": str, "remaining_s": int}, ...],
          "volume_pct": int (0-100),
        }
    """
    result: dict = {"media": None, "timers": [], "volume_pct": 50}

    if not _token():
        return result

    # Satellite state + volume (single fetch reused below)
    sat = _get(f"/api/states/{_SATELLITE_ENTITY}")
    if sat:
        vol = sat.get("attributes", {}).get("volume_level")
        if vol is not None:
            result["volume_pct"] = round(float(vol) * 100)

        if sat.get("state") == "playing":
            # Try MASS media entity first for richer metadata
            mass_state = _get(f"/api/states/{_MEDIA_ENTITY}")
            title, artist = None, ""
            if mass_state and mass_state.get("state") == "playing":
                attrs = mass_state.get("attributes", {})
                title = attrs.get("media_title") or attrs.get("media_station")
                artist = attrs.get("media_artist") or ""

            # Fall back to last-triggered radio script name
            if not title:
                title = _fetch_active_radio_station()

            if title:
                result["media"] = {"title": title, "artist": artist}

    # Voice timers via built-in conversation agent
    result["timers"] = _fetch_timers()

    # Watchface selection
    wf = _get(f"/api/states/{_WATCHFACE_ENTITY}")
    if wf:
        result["watchface"] = wf.get("state", "").lower()

    return result
