# 05 — Access, deploy & tokens

## How to reach each host

| Target | Command | Notes |
|--------|---------|-------|
| Proxmox host | `ssh root@prox` | Use short name `prox` (host key changed after rebuild — `prox.home` may fail strict check). |
| dd-ai (CT 107) | `ssh root@prox` then `pct exec 107 -- <cmd>` | Direct ssh to dd-ai **fails** (key not authorized). `.home`/`.local` resolves but no shell access. |
| dd-ha (HA OS) | `ssh root@dd-ha` | Key auth as **root** (`dd@dd-ha` is denied). |
| pi-satellite | `ssh dd@pi-satellite` | |

**Sandbox caveat:** the Bash sandbox blocks LAN egress. `ssh root@dd-ha` and `curl http://dd-ha:8123` calls may need `dangerouslyDisableSandbox: true`. `.local` mDNS is unreliable from dd-ha (HA needs `.home` / Pi-hole) — a failed `.local` ping is not proof a host is down.

## Driving the HA API

- **Token:** `/home/dd/ha-dashboards/.ha_token` (repo, gitignored). Also `/home/dd/.ha_token` (used by `push_dashboards.py`).
- **REST** from the workstation: `http://dd-ha:8123/api/...` with `Authorization: Bearer $(cat .ha_token)`.
- dd-ha's `core-ssh` addon has `/config` mounted but **cannot** reach core at `127.0.0.1:8123` — only via `dd-ha:8123`. Drive the API from the workstation, not from inside dd-ha.
- `/api/error_log` is gone in 2026.x — use WS `system_log/list` (via `ha_ws.py`) for logger errors.
- `ha_ws.py` (repo root) is a minimal WS client (auth from `.ha_token`) for things REST can't do: entity-registry renames, `homeassistant/expose_entity`, pipeline updates.

Common one-liners:
```bash
TOKEN=$(cat /home/dd/ha-dashboards/.ha_token)
# entity state
curl -s -H "Authorization: Bearer $TOKEN" http://dd-ha:8123/api/states/stt.faster_whisper
# reload a config entry (e.g. dd-ai whisper after a GPU fix)
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  http://dd-ha:8123/api/config/config_entries/entry/01KWQ49XNTZ5ZKN3J1906GVZXW/reload
# validate + reload scripts / automations
curl -s -X POST -H "Authorization: Bearer $TOKEN" http://dd-ha:8123/api/config/core/check_config
curl -s -X POST -H "Authorization: Bearer $TOKEN" http://dd-ha:8123/api/services/script/reload
```

## Deploying HA config (dd-ha)

Only **dashboards** auto-deploy (`python3 push_dashboards.py`). Everything else (scripts.yaml, automations, sensors) you copy yourself — repo and live **can drift, diff before overwriting**:
```bash
# live config dir on dd-ha is /config (also bind-mounted at /homeassistant)
cat scripts.yaml | ssh root@dd-ha 'cp /config/scripts.yaml /config/scripts.yaml.bak.$(date +%s) && cat > /config/scripts.yaml'
# then validate + reload via REST (above)
```
> `python3` is **not** on the HAOS host — do JSON parsing on the workstation, not on dd-ha.

**Deploy caveat:** reloading the `script` component **cancels in-flight script runs** — including pending `script.delayed_entity_action` waits (scheduled actions) and the `script.radio_play` idle-wait. Re-arm anything mid-wait after a reload. An HA **restart** orphans scheduled-action entries; the `scheduled_actions_recovery` automation (fires on HA start) re-executes past-due and relaunches future ones.

## Token rotation checklist

Rotating the HA long-lived token means updating **every** copy or something breaks silently:

| Location | Used by |
|----------|---------|
| `pi-satellite:/home/dd/dev/voice-assistant/.ha_token` | satellite touch controls (`ha_actions.py`) — **not auto-synced** |
| workstation `/home/dd/.ha_token` | `push_dashboards.py` |
| repo `/home/dd/ha-dashboards/.ha_token` | `ha_ws.py`, runbook curl commands |
| `dd-ha:/config/.ha_token` | `ha_history_service.py` |
| `dd-ha:/config/secrets.yaml` → `ha_token:` | `sensors_timers.yaml` REST self-poll (Bearer-prefixed) |

After updating `secrets.yaml` you need a **full HA core restart** (`ssh root@dd-ha "ha core restart"`) — `secrets.yaml` is cached and `rest.reload` won't re-read it. Symptom of a stale secret: recurring `Login attempt failed from localhost (::1)` in the HA log. Symptom of a stale Pi token: satellite touch controls silently no-op (401) — see [03 §5](03-runbook.md#5-touch-controls-dead-radiovolume-no-op).

## Deploying satellite code

```bash
rsync -av satellite/src/ dd@pi-satellite:/home/dd/dev/voice-assistant/src/
ssh dd@pi-satellite "sudo systemctl restart voice-display.service"   # or lva.service
```
Preview display changes headless first: `python3 satellite/src/display/shot.py /tmp/out` renders every screen state to PNG.
