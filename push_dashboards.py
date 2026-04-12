#!/usr/bin/env python3
"""Push YAML dashboards to Home Assistant via WebSocket API."""
import asyncio, json, sys, yaml
import websockets

HA_WS = "ws://dd-ha:8123/api/websocket"
TOKEN_FILE = "/home/dd/.ha_token"

# yaml filename → lovelace url_path (None = default dashboard)
DASHBOARDS = {
    "dashboard_home.yaml":       "dashboard-playground",
    "dashboard_piscine.yaml":    "dashboard-piscine",
    "dashboard_video.yaml":      "lovelace-video",
    "dashboard_proxmox.yaml":    "playground-ai",
    "dashboard_temp.yaml":       "lovelace-temperatures",
    "dashboard_alarm.yaml":      "dashboard-alarme",
    "dashboard_interphone.yaml": "lovelace-interphone",
    "dashboard_3dprint.yaml":    "3d-print",
}


async def push(token: str, files: list[str]):
    import os
    base = os.path.dirname(os.path.abspath(__file__))

    async with websockets.connect(HA_WS) as ws:
        msg = json.loads(await ws.recv())
        assert msg["type"] == "auth_required"
        await ws.send(json.dumps({"type": "auth", "access_token": token}))
        msg = json.loads(await ws.recv())
        assert msg["type"] == "auth_ok", f"Auth failed: {msg}"

        for i, fname in enumerate(files, start=1):
            url_path = DASHBOARDS[fname]
            with open(os.path.join(base, fname)) as f:
                config = yaml.safe_load(f)
            cmd = {"id": i, "type": "lovelace/config/save", "config": config}
            if url_path:
                cmd["url_path"] = url_path
            await ws.send(json.dumps(cmd))
            resp = json.loads(await ws.recv())
            label = url_path or "default"
            if resp.get("success"):
                print(f"  OK  {fname} → {label}")
            else:
                print(f"  ERR {fname} → {label}: {resp.get('error')}")


def main():
    try:
        with open(TOKEN_FILE) as f:
            token = f.read().strip()
    except FileNotFoundError:
        print(f"Token file not found: {TOKEN_FILE}")
        print("Create it with: echo 'YOUR_TOKEN' > ~/.ha_token && chmod 600 ~/.ha_token")
        sys.exit(1)

    files = sys.argv[1:] if sys.argv[1:] else list(DASHBOARDS.keys())
    unknown = [f for f in files if f not in DASHBOARDS]
    if unknown:
        print(f"Unknown dashboard(s): {unknown}")
        print(f"Known: {list(DASHBOARDS.keys())}")
        sys.exit(1)

    asyncio.run(push(token, files))


if __name__ == "__main__":
    main()
