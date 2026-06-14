"""
Home Assistant actions triggered by touch.

The device reads state via ha_context; this module is the write path — calling
HA services so the on-screen buttons actually do something. Same local HA URL
and token as ha_context. All calls are fire-and-forget with a short timeout so
the render loop never blocks for long.
"""

import json
import urllib.request

from ha_context import _HA_URL, _headers, _SATELLITE_ENTITY, _SATELLITE_DEVICE_ID

# ── Radio stations (id, label, stream URL, brand colour) ─────────────────────
# Streams mirror scripts.yaml; calling play_media directly avoids a script hop.
STATIONS = [
    {"id": "france_inter", "label": "France Inter",
     "url": "http://icecast.radiofrance.fr/franceinter-hifi.aac", "color": (227, 35, 26)},
    {"id": "france_info", "label": "France Info",
     "url": "http://icecast.radiofrance.fr/franceinfo-hifi.aac", "color": (236, 0, 140)},
    {"id": "rtl", "label": "RTL",
     # icecast origin — avoids the streaming.radio.rtl.fr → streamer-04 redirect
     # that served lagging/cutting audio. HLS fallback if ever needed:
     # https://live.m6radio.quortex.io/.../grouprtl/national/long/audio-64000/index.m3u8
     "url": "https://icecast.rtl.fr/rtl-1-44-128", "color": (237, 28, 36)},
    {"id": "rtl2", "label": "RTL2",
     # icecast origin — avoids the lagging/cutting streamer-02 redirect edge
     "url": "https://icecast.rtl2.fr/rtl2-1-44-128", "color": (0, 160, 227)},
    {"id": "europe2", "label": "Europe 2",
     "url": "http://europe2.lmn.fm/europe2.mp3", "color": (255, 90, 0)},
    {"id": "nova", "label": "Radio Nova",
     # main Nova channel; the old nova-128 mount 404s — mount renamed to radionova
     "url": "http://radionova.ice.infomaniak.ch/radionova-256.aac", "color": (149, 95, 233)},
]


def _post(path: str, payload: dict) -> bool:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(f"{_HA_URL}{path}", data=body,
                                 headers=_headers(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=4) as r:
            return r.status < 300
    except Exception:
        return False


def _service(domain: str, service: str, data: dict) -> bool:
    return _post(f"/api/services/{domain}/{service}", data)


# ── Radio ─────────────────────────────────────────────────────────────────
def play_radio(url: str) -> bool:
    return _service("media_player", "play_media", {
        "entity_id": _SATELLITE_ENTITY,
        "media_content_id": url,
        "media_content_type": "music",
    })


def stop_radio() -> bool:
    return _service("media_player", "media_stop", {"entity_id": _SATELLITE_ENTITY})


# ── Volume ──────────────────────────────────────────────────────────────────
def set_volume(pct: int) -> bool:
    pct = max(0, min(100, int(pct)))
    return _service("media_player", "volume_set", {
        "entity_id": _SATELLITE_ENTITY,
        "volume_level": round(pct / 100.0, 2),
    })


# ── Timers (reuse HA's voice-timer infrastructure via the conversation agent) ─
# English phrasing: HA's French timer intents return no_intent_match for this
# device, but the English HassStartTimer/Cancel/Status intents work. The user
# never sees this — the UI is French.
def _converse(text: str) -> bool:
    return _post("/api/conversation/process", {
        "text": text,
        "language": "en",
        "agent_id": "conversation.home_assistant",
        "device_id": _SATELLITE_DEVICE_ID,
    })


def start_timer(minutes: int) -> bool:
    return _converse(f"set a timer for {minutes} minutes")


def cancel_timers() -> bool:
    return _converse("cancel all timers")
