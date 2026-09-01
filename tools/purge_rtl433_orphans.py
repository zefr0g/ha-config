#!/usr/bin/env python3
"""Purge orphaned rtl_433 MQTT-discovery devices from Home Assistant.

Why this is needed
------------------
Cheap 433 MHz sensors (LaCrosse TX141THBv2, Vevor 7-in-1, ...) redraw a random
device id on every battery change. The rtl_433 addon publishes a *retained* MQTT
discovery config per id, so each battery swap leaves behind a full set of dead
entities plus their retained discovery topics. Deleting the entities in the UI is
not enough: the retained config republishes them on the next HA restart.

The fix is to clear the retained discovery payload (publish an empty string to the
config topic with retain=true), which makes HA drop the entity for good, then tidy
any device-registry rows that survive.

Usage
-----
    python3 tools/purge_rtl433_orphans.py --dry-run          # show what would go
    python3 tools/purge_rtl433_orphans.py                    # do it

A device is only purged when it matches PURGE_PATTERNS, is not in KEEP, *and* every
one of its entities currently reads unknown/unavailable. That last check is what
keeps the sensor that is actually transmitting right now safe without having to
hard-code its id — which is the whole point, since the id keeps changing.
"""

import argparse
import asyncio
import json
import re
import sys

import websockets

URL = "ws://dd-ha:8123/api/websocket"
TOKEN_FILE = "/home/dd/ha-dashboards/.ha_token"

# Device-name prefixes whose retained discovery must be cleared.
PURGE_PATTERNS = [
    r"^Vevor-7in1-",            # 433 path abandoned; the station now feeds via weather_station/*
    r"^LaCrosse-TX141THBv2-",   # superseded by the wildcard sensors in mqtt.yaml
]

# Never touch these, even if they match above.
KEEP = [
    r"^vevor_ws_",              # hand-rolled "Station Météo" device (weather_station/* topics)
]

DISCOVERY_PREFIX = "homeassistant"
COLLECT_SECONDS = 20


def matches(name: str) -> bool:
    if any(re.search(p, name) for p in KEEP):
        return False
    return any(re.search(p, name) for p in PURGE_PATTERNS)


_next_id = 0


def new_id():
    """HA requires strictly increasing message ids on a connection."""
    global _next_id
    _next_id += 1
    return _next_id


async def call(ws, cmd):
    mid = cmd["id"] = new_id()
    await ws.send(json.dumps(cmd))
    while True:
        msg = json.loads(await ws.recv())
        if msg.get("id") == mid and msg.get("type") == "result":
            if not msg.get("success"):
                raise RuntimeError(f"{cmd.get('type')} failed: {msg.get('error')}")
            return msg.get("result")


async def collect_discovery_topics(ws):
    """Listen on the discovery tree and return {topic: payload} for retained configs.

    Retained messages all arrive right after subscribing; the window just has to be
    long enough for the broker to flush them.
    """
    mid = new_id()
    await ws.send(json.dumps({"id": mid, "type": "mqtt/subscribe",
                              "topic": f"{DISCOVERY_PREFIX}/#"}))
    found = {}
    try:
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=COLLECT_SECONDS))
            if msg.get("type") == "event" and msg.get("id") == mid:
                ev = msg["event"]
                if ev["topic"].endswith("/config") and ev["payload"].strip():
                    found[ev["topic"]] = ev["payload"]
    except asyncio.TimeoutError:
        pass
    await call(ws, {"type": "unsubscribe_events", "subscription": mid})
    return found


def device_name_of(topic: str, payload: str) -> str:
    """Best-effort device identity for a discovery config topic."""
    try:
        cfg = json.loads(payload)
        dev = cfg.get("device") or {}
        ids = dev.get("identifiers") or []
        if ids:
            return ids[0] if isinstance(ids[0], str) else str(ids[0])
        if dev.get("name"):
            return dev["name"]
    except (ValueError, TypeError):
        pass
    # Fall back to the topic's object_id segment, e.g. .../Vevor-7in1-0-2569-rssi/config
    # — note this still carries the measurement suffix; resolve_device() strips it.
    return topic.split("/")[-2]


def resolve_device(raw: str, dead: set) -> str | None:
    """Map a discovery config's raw identity onto a known dead device name.

    The older rtl_433 discovery layout encodes device *and* measurement in one
    object_id ("Vevor-7in1-0-2569-rssi"), so an exact lookup misses it; fall back to
    the longest dead device name it starts with.
    """
    if raw in dead:
        return raw
    candidates = [d for d in dead if raw.startswith(d)]
    return max(candidates, key=len) if candidates else None


async def dead_device_names(ws):
    """Names of registry devices whose every enabled entity is unknown/unavailable.

    A device still transmitting has at least one entity carrying a real value, so
    this cleanly separates "orphaned by a battery change" from "in use right now".
    """
    entities = await call(ws, {"type": "config/entity_registry/list"})
    devices = await call(ws, {"type": "config/device_registry/list"})
    states = {s["entity_id"]: s["state"] for s in await call(ws, {"type": "get_states"})}

    by_device = {}
    for ent in entities:
        if ent.get("disabled_by"):
            continue
        by_device.setdefault(ent.get("device_id"), []).append(ent["entity_id"])

    dead = set()
    for dev in devices:
        ents = by_device.get(dev["id"], [])
        if not ents:
            continue
        if all(states.get(e, "unavailable") in ("unknown", "unavailable") for e in ents):
            for ident in dev.get("identifiers", []):
                if len(ident) > 1:
                    dead.add(ident[1])
            if dev.get("name"):
                dead.add(dev["name"])
    return dead


async def main(dry_run: bool):
    token = open(TOKEN_FILE).read().strip()
    async with websockets.connect(URL, max_size=None) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type": "auth", "access_token": token}))
        if json.loads(await ws.recv())["type"] != "auth_ok":
            sys.exit("auth failed")

        dead = await dead_device_names(ws)
        print(f"devices with no live entity: {', '.join(sorted(dead)) or '(none)'}\n")

        topics = await collect_discovery_topics(ws)
        doomed = {}
        for t, p in topics.items():
            dev = resolve_device(device_name_of(t, p), dead)
            if dev and matches(dev):
                doomed[t] = p

        print(f"{len(topics)} retained discovery configs seen, "
              f"{len(doomed)} belong to dead devices on the purge list")
        for t in sorted(doomed):
            print(("  [dry-run] " if dry_run else "  clearing  ") + t)

        if not dry_run:
            for t in sorted(doomed):
                await call(ws, {
                    "type": "call_service", "domain": "mqtt", "service": "publish",
                    "service_data": {"topic": t, "payload": "", "retain": True, "qos": 0},
                })
            # Give HA a moment to process the removals before reading the registry.
            await asyncio.sleep(5)

        # Sweep device-registry rows that no discovery config backs any more.
        devices = await call(ws, {"type": "config/device_registry/list"})
        stale = []
        for dev in devices:
            names = [i[1] for i in dev.get("identifiers", []) if len(i) > 1]
            if any(matches(n) and n in dead for n in names):
                stale.append(dev)
        print(f"\n{len(stale)} device-registry rows left to remove")
        for i, dev in enumerate(stale):
            print(("  [dry-run] " if dry_run else "  removing  ")
                  + f"{dev.get('name')} ({dev['id']})")
            if not dry_run:
                for entry in dev.get("config_entries", []):
                    try:
                        await call(ws, {
                            "type": "config/device_registry/remove_config_entry",
                            "device_id": dev["id"], "config_entry_id": entry,
                        })
                    except RuntimeError as err:
                        print(f"      skipped: {err}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    asyncio.run(main(ap.parse_args().dry_run))
