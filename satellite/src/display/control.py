#!/usr/bin/env python3
"""
Display settings MQTT bridge.

Subscribes to HA MQTT discovery command topics and writes
DISPLAY_CONFIG_FILE. The display daemon reads that file each frame
and applies changes via the ST7796S driver.

Requires: paho-mqtt  (pip install paho-mqtt)

MQTT credentials: MQTT_CREDS_FILE  — one line "username:password"  (chmod 600)
If the file is absent or empty, connects without authentication.
"""

import json
import os
import sys
import time

sys.path.insert(0, "/home/dd/dev/voice-assistant/src")

from config import (
    DISPLAY_CONFIG_FILE,
    MQTT_BROKER,
    MQTT_CREDS_FILE,
    MQTT_PORT,
    MQTT_TOPIC_PREFIX,
)
from display.driver import GAMMA_OPTIONS

try:
    import paho.mqtt.client as mqtt
except ImportError:
    sys.exit("paho-mqtt not installed — run: pip install paho-mqtt")

# ── HA device descriptor ──────────────────────────────────────────────────────
_DEVICE_ID = "pi_satellite_display"
_DEVICE_INFO = {
    "identifiers": [_DEVICE_ID],
    "name": "Pi Satellite Display",
    "model": "ST7796S 4\" TFT 480×320",
    "manufacturer": "RPi Voice Satellite",
}

# ── MQTT discovery + state/command topics ─────────────────────────────────────
_T = MQTT_TOPIC_PREFIX   # shorthand

_ENTITIES = [
    {
        "component": "number",
        "key": "brightness",
        "discovery": {
            "name": "Luminosité",
            "unique_id": f"{_DEVICE_ID}_brightness",
            "command_topic": f"{_T}/brightness/set",
            "state_topic":   f"{_T}/brightness/state",
            "min": 0, "max": 100, "step": 1,
            "unit_of_measurement": "%",
            "icon": "mdi:brightness-6",
            "device": _DEVICE_INFO,
        },
    },
    {
        "component": "number",
        "key": "contrast",
        "discovery": {
            "name": "Contraste",
            "unique_id": f"{_DEVICE_ID}_contrast",
            "command_topic": f"{_T}/contrast/set",
            "state_topic":   f"{_T}/contrast/state",
            "min": 0, "max": 127, "step": 1,
            "icon": "mdi:contrast-circle",
            "device": _DEVICE_INFO,
        },
    },
    {
        "component": "select",
        "key": "gamma",
        "discovery": {
            "name": "Gamma",
            "unique_id": f"{_DEVICE_ID}_gamma",
            "command_topic": f"{_T}/gamma/set",
            "state_topic":   f"{_T}/gamma/state",
            "options": GAMMA_OPTIONS,
            "icon": "mdi:sine-wave",
            "device": _DEVICE_INFO,
        },
    },
    {
        "component": "switch",
        "key": "power",
        "discovery": {
            "name": "Écran",
            "unique_id": f"{_DEVICE_ID}_power",
            "command_topic": f"{_T}/power/set",
            "state_topic":   f"{_T}/power/state",
            "payload_on": "ON",
            "payload_off": "OFF",
            "icon": "mdi:monitor",
            "device": _DEVICE_INFO,
        },
    },
]

_DEFAULTS: dict = {
    "brightness": 100,
    "contrast": 42,      # 0x2A — matches the _init() hard-coded value
    "gamma": "natural",
    "power": True,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_creds() -> tuple[str, str] | None:
    try:
        with open(MQTT_CREDS_FILE) as f:
            line = f.read().strip()
        if ":" in line:
            user, _, pw = line.partition(":")
            return user, pw
    except FileNotFoundError:
        pass
    return None


def _read_config() -> dict:
    try:
        with open(DISPLAY_CONFIG_FILE) as f:
            return {**_DEFAULTS, **json.load(f)}
    except Exception:
        return dict(_DEFAULTS)


def _write_config(cfg: dict):
    tmp = DISPLAY_CONFIG_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f)
    os.replace(tmp, DISPLAY_CONFIG_FILE)


def _state_value(key: str, value) -> str:
    if key == "power":
        return "ON" if value else "OFF"
    return str(value)


# ── MQTT callbacks ────────────────────────────────────────────────────────────

def _on_connect(client, userdata, flags, rc, props=None):
    if rc != 0:
        print(f"[CTRL] MQTT connect failed: rc={rc}", flush=True)
        return
    print("[CTRL] MQTT connected", flush=True)

    # Publish discovery payloads
    for ent in _ENTITIES:
        topic = f"homeassistant/{ent['component']}/{_DEVICE_ID}_{ent['key']}/config"
        client.publish(topic, json.dumps(ent["discovery"]), retain=True)

    # Subscribe to all command topics
    for ent in _ENTITIES:
        client.subscribe(ent["discovery"]["command_topic"])

    # Publish current state
    cfg = userdata["config"]
    for ent in _ENTITIES:
        key = ent["key"]
        client.publish(
            ent["discovery"]["state_topic"],
            _state_value(key, cfg[key]),
            retain=True,
        )
    print("[CTRL] Discovery published, subscribed to command topics", flush=True)


def _on_message(client, userdata, msg):
    payload = msg.payload.decode().strip()
    topic   = msg.topic
    cfg     = userdata["config"]

    for ent in _ENTITIES:
        if topic != ent["discovery"]["command_topic"]:
            continue
        key = ent["key"]
        try:
            if key == "brightness":
                cfg[key] = max(0, min(100, int(float(payload))))
            elif key == "contrast":
                cfg[key] = max(0, min(127, int(float(payload))))
            elif key == "gamma":
                if payload in GAMMA_OPTIONS:
                    cfg[key] = payload
            elif key == "power":
                cfg[key] = payload.upper() == "ON"
        except (ValueError, TypeError):
            print(f"[CTRL] Bad payload for {key}: {payload!r}", flush=True)
            return

        _write_config(cfg)
        client.publish(
            ent["discovery"]["state_topic"],
            _state_value(key, cfg[key]),
            retain=True,
        )
        print(f"[CTRL] {key} → {cfg[key]}", flush=True)
        break


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    cfg  = _read_config()
    _write_config(cfg)   # ensure file exists with defaults on first run

    userdata = {"config": cfg}
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id=f"{_DEVICE_ID}_ctrl")
    client.user_data_set(userdata)
    client.on_connect = _on_connect
    client.on_message = _on_message

    creds = _read_creds()
    if creds:
        client.username_pw_set(*creds)

    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            client.loop_forever()
        except (OSError, ConnectionRefusedError) as e:
            print(f"[CTRL] MQTT error: {e} — retrying in 10s", flush=True)
            time.sleep(10)


if __name__ == "__main__":
    main()
