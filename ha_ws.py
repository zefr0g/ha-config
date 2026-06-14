#!/usr/bin/env python3
"""Minimal HA WebSocket client: authenticate, run a sequence of commands, print results.
Usage: pass JSON command objects as argv (without the 'id' field, which is auto-added)."""
import asyncio, json, sys
import websockets

URL = "ws://dd-ha:8123/api/websocket"

async def main(cmds):
    with open("/home/dd/ha-dashboards/.ha_token") as f:
        token = f.read().strip()
    async with websockets.connect(URL, max_size=None) as ws:
        assert json.loads(await ws.recv())["type"] == "auth_required"
        await ws.send(json.dumps({"type": "auth", "access_token": token}))
        auth = json.loads(await ws.recv())
        if auth["type"] != "auth_ok":
            print("AUTH FAILED:", auth); return
        mid = 0
        for cmd in cmds:
            mid += 1
            cmd["id"] = mid
            await ws.send(json.dumps(cmd))
            # read until we get the matching result id
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == mid and msg.get("type") == "result":
                    print(json.dumps({"cmd": cmd.get("type"), "success": msg.get("success"),
                                      "result": msg.get("result"), "error": msg.get("error")},
                                     ensure_ascii=False, indent=2))
                    break

if __name__ == "__main__":
    cmds = [json.loads(a) for a in sys.argv[1:]]
    asyncio.run(main(cmds))
