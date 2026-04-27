#!/usr/bin/env python3
"""
Query HA entity history and write a concise voice-friendly summary
to input_text.historique_resultat via the HA REST API.

Usage: python3 ha_history_service.py <entity_id> [hours]
Deploy to: /config/scripts/ha_history_service.py on HA server
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

HA_URL = "http://localhost:8123"
TOKEN_FILE = Path("/config/.ha_token")


def token() -> str:
    return TOKEN_FILE.read_text().strip()


def headers() -> dict:
    return {"Authorization": f"Bearer {token()}", "Content-Type": "application/json"}


def get_history(entity_id: str, hours: int) -> list[dict]:
    start = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    r = requests.get(
        f"{HA_URL}/api/history/period/{start}",
        headers=headers(),
        params={
            "filter_entity_id": entity_id,
            "minimal_response": "true",
            "significant_changes_only": "true",
        },
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    return data[0] if data else []


def friendly_name(entity_id: str) -> str:
    r = requests.get(f"{HA_URL}/api/states/{entity_id}", headers=headers(), timeout=5)
    if r.ok:
        return r.json().get("attributes", {}).get("friendly_name") or entity_id
    return entity_id


def summarise(entity_id: str, events: list[dict], hours: int) -> str:
    name = friendly_name(entity_id)
    if not events:
        return f"{name}: aucun événement dans les dernières {hours}h."

    # Determine active states (on/open/true)
    active = {"on", "open", "true", "locked"}

    on_events = [(e["state"], e["last_changed"]) for e in events]

    # Compute cycles and durations
    now = datetime.now(timezone.utc)
    cycles = 0
    total_active_secs = 0
    last_on_time = None
    last_on_str = None

    prev_state, prev_ts = None, None
    for state, ts_str in on_events:
        ts = datetime.fromisoformat(ts_str)
        if state.lower() in active:
            cycles += 1
            last_on_time = ts
            last_on_str = ts.astimezone().strftime("%d/%m à %H:%M")
            prev_state, prev_ts = state, ts
        elif prev_state and prev_state.lower() in active and prev_ts:
            total_active_secs += (ts - prev_ts).total_seconds()
            prev_state, prev_ts = state, ts
        else:
            prev_state, prev_ts = state, ts

    # If still active at end, count up to now
    if prev_state and prev_state.lower() in active and prev_ts:
        total_active_secs += (now - prev_ts).total_seconds()

    current_state = on_events[-1][0] if on_events else "?"

    def fmt_duration(secs: float) -> str:
        secs = int(secs)
        h, m = divmod(secs // 60, 60)
        if h:
            return f"{h}h{m:02d}"
        return f"{m}min"

    parts = [f"{name}:"]
    parts.append(f"{cycles} activation{'s' if cycles > 1 else ''} en {hours}h.")
    if last_on_str:
        parts.append(f"Dernière: {last_on_str}.")
    if total_active_secs > 60:
        parts.append(f"Durée totale: {fmt_duration(total_active_secs)}.")
    parts.append(f"État actuel: {current_state}.")

    summary = " ".join(parts)
    # Truncate to 255 chars (HA input_text state limit)
    return summary[:255]


def write_result(summary: str):
    r = requests.post(
        f"{HA_URL}/api/states/input_text.historique_resultat",
        headers=headers(),
        json={"state": summary},
        timeout=5,
    )
    r.raise_for_status()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: ha_history_service.py <entity_id> [hours]")
        sys.exit(1)

    entity_id = sys.argv[1]
    hours = int(sys.argv[2]) if len(sys.argv) > 2 else 24

    events = get_history(entity_id, hours)
    summary = summarise(entity_id, events, hours)
    write_result(summary)
    print(summary)
