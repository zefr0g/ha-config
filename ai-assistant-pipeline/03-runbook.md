# 03 — Runbook (failure modes & fixes)

Every known way the pipeline breaks, ordered by how often it bites. Each section:
**symptom → diagnose → fix → verify.**

---

## 1. STT dead — "stt-provider-missing"

**Symptom:** Assist error `No speech-to-text provider for: stt.faster_whisper (stt-provider-missing)`; voice does nothing. `stt.faster_whisper` is `unavailable`. (Before the 2026-07-09 rename this entity was `stt.faster_whisper_3`.)

**Root cause (the #1 recurring issue):** the RTX 3060's `nvidia-uvm` device-node **major number drifts** on every nvidia driver/module reload, but CT 107's cgroup allow-list in `/etc/pve/lxc/107.conf` hardcodes the old major. The container is then denied GPU access → whisper crashes with `RuntimeError: CUDA failed with error unknown error` and crash-loops (`Restarting (1)`). Ollama/piper may still be up (piper is CPU). Seen: 507→508 (2026-07-09), 506→507 (2026-07-05).

**Diagnose:**
```bash
# Is whisper crash-looping?
ssh root@prox "pct exec 107 -- docker ps -a --format '{{.Names}} {{.Status}}' | grep whisper"
ssh root@prox "pct exec 107 -- docker logs --tail 20 whisper 2>&1 | grep -i cuda"
# Compare the REAL uvm major vs what the container allows:
ssh root@prox "ls -l /dev/nvidia-uvm; grep cgroup2.devices.allow /etc/pve/lxc/107.conf"
```
If `/dev/nvidia-uvm` shows e.g. `508,` but the conf has `c 507:* rwm` → drift confirmed.

**Fix** (edit the major to match the host, reboot the container):
```bash
ssh root@prox "cp /etc/pve/lxc/107.conf /etc/pve/lxc/107.conf.bak-\$(date +%Y%m%d) && \
  sed -i 's/^lxc.cgroup2.devices.allow: c 507:\* rwm/lxc.cgroup2.devices.allow: c 508:* rwm/' /etc/pve/lxc/107.conf"
#          ^^^ replace 507 with the OLD major, 508 with the CURRENT host major
ssh root@prox "pct reboot 107"          # graceful reboot re-applies the cgroup; NOT 'pct restart'
```
Then **reload the HA Wyoming entry** so the STT entity reconnects (it won't on its own quickly):
```bash
TOKEN=$(cat /home/dd/ha-dashboards/.ha_token)
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  http://dd-ha:8123/api/config/config_entries/entry/01KWQ49XNTZ5ZKN3J1906GVZXW/reload
```

**Verify:**
```bash
# whisper up + on GPU (~1.16 GB), "Ready" in logs:
ssh root@prox "pct exec 107 -- docker ps --format '{{.Names}} {{.Status}}' | grep whisper; \
  pct exec 107 -- nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader"
# HA entity healthy (state 'unknown' == OK for STT):
curl -s -H "Authorization: Bearer $TOKEN" http://dd-ha:8123/api/states/stt.faster_whisper \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['state'])"
```
`unknown` (not `unavailable`) = fixed. Then say "Hey Jarvis" to the satellite.

> **NOT a hardware fault.** Do not reseat the GPU, roll back the driver, or chase
> `LnkSta 2.5GT/s` (that's idle power-saving). The uvm major is the whole story.
> Durability idea (still a TODO): a Proxmox hookscript that reads `/proc/devices`
> and rewrites the allow line before CT start, so this stops recurring.

---

## 2. Everything slow / Ollama on CPU

**Symptom:** voice works but is sluggish; LLM answers are slow or degraded. Same root cause as §1 (GPU cgroup drift) but seen from Ollama's side.

**Diagnose:**
```bash
ssh root@prox "pct exec 107 -- docker exec ollama ollama ps"      # look for '100% CPU' instead of GPU
ssh root@prox "pct exec 107 -- nvidia-smi --query-compute-apps=process_name,used_memory --format=csv"
# Deep proof of cuInit failure:
ssh root@prox "pct exec 107 -- docker exec -e OLLAMA_DEBUG=2 -e OLLAMA_HOST=0.0.0.0:11998 ollama \
  sh -lc 'timeout 8 ollama serve 2>&1 | grep -iE \"cuInit|CUDA devices|inference compute\"'"
# 'cuInit failed: 999' == same GPU cgroup drift
```

**Fix:** same as [§1](#1-stt-dead--stt-provider-missing) (fix uvm major + `pct reboot 107`). After reboot ollama reloads on GPU automatically.

**Verify:** `ollama ps` → `100% GPU`; `nvidia-smi` shows the gemma process (~8 GB) + whisper (~1.16 GB) ≈ 9.3 / 12 GB.

---

## 3. Satellite "mic dead" / LVA crash-loop

**Symptom:** satellite totally unresponsive to voice after an **unclean Pi shutdown / power loss** (e.g. opening the case). Looks like the mic died.

**Diagnose — separate hardware from software:**
```bash
# 1) Is the mic actually fine? Raw ALSA capture (signal is on LEFT channel; INMP441 L/R→GND):
ssh dd@pi-satellite "arecord -D hw:0,0 -f S32_LE -r 48000 -c 2 -d 3 /tmp/t.wav && ls -l /tmp/t.wav"
# 2) LVA crash-looping?
ssh dd@pi-satellite "systemctl status lva.service --no-pager | tail; docker logs --tail 15 lva 2>&1"
```
Log shows `RWLayer of container <id> is unexpectedly nil` + `Exited (137)` → corrupted overlay2 layer.

**Fix** (all volumes are host-mounted in `/home/dd/lva/docker-compose.yml`, so removing the container loses nothing):
```bash
ssh dd@pi-satellite "sudo systemctl stop lva.service && docker rm -f lva && sudo systemctl start lva.service"
# if it persists:
ssh dd@pi-satellite "sudo systemctl restart docker && sudo systemctl restart lva.service"
```

**Verify:** `docker ps` shows `lva` Up; say "Hey Jarvis". **Re-select wake word** "Hey Jarvis" in `select.rpi_satellite_mot_d_activation` — container recreate resets it.

> `audioop` is gone in Python 3.13 on the Pi — compute a capture's peak via `wave`+`struct`, not `audioop`.

---

## 4. Timers stopped ringing

**Symptom:** timers used to ring on the satellite; now they finish silently.

**Root cause:** the ring (`/app/sounds/timer_finished.flac`) is played/looped by LVA itself and can be stopped **only by the voice stop word "stop"**. If a ring was silenced by anything else (`media_player.media_stop`, mute), the internal `_timer_finished` flag stays `True` — every later timer's FINISHED event is then skipped.

**Fix:**
```bash
ssh dd@pi-satellite "sudo systemctl restart lva.service"   # fresh process resets the flag
```

**Verify:** set a 15 s timer, then:
```bash
ssh dd@pi-satellite "docker logs --tail 20 lva 2>&1 | grep -i timer_finished; pactl list sink-inputs short"
```
Should show `Playing 1 URL(s): …/timer_finished.flac`.

> There is **no HA/network way to stop an active ring** — `assist_satellite` only
> exposes announce/ask_question, and `media_stop` hits the music player (mpv), not
> the ring (tts_player). Tell the user to say "stop", never script `media_stop`.

---

## 5. Touch controls dead (radio/volume no-op)

**Symptom:** on the satellite touchscreen, tapping a radio station plays nothing; the volume slider moves on screen but real volume doesn't change. **Phone/web HA UI still works** (that uses HA's own session, so it does *not* rule this out).

**Root cause:** stale HA token on the Pi. The Pi keeps its **own** token at `/home/dd/dev/voice-assistant/.ha_token` (separate from the repo's `.ha_token`, not auto-synced). `ha_actions.py` calls are fire-and-forget with a bare `except: return False`, so a 401 fails silently.

**Diagnose (from the Pi):**
```bash
ssh dd@pi-satellite "curl -s -o /dev/null -w '%{http_code}\n' \
  -H \"Authorization: Bearer \$(cat /home/dd/dev/voice-assistant/.ha_token)\" \
  http://dd-ha:8123/api/states/media_player.enceinte_entree"
# 401 == stale token
```

**Fix:**
```bash
scp /home/dd/ha-dashboards/.ha_token dd@pi-satellite:/home/dd/dev/voice-assistant/.ha_token
ssh dd@pi-satellite "sudo systemctl restart voice-display.service"
```

> **When rotating the HA token, update ALL copies** or something else breaks:
> Pi `…/voice-assistant/.ha_token`; workstation `/home/dd/.ha_token` (push_dashboards.py);
> repo `.ha_token` (ha_ws.py); dd-ha `/config/.ha_token` (ha_history_service);
> and dd-ha `/config/secrets.yaml` `ha_token:` (needs a **full HA core restart** —
> `secrets.yaml` is cached, `rest.reload` won't re-read it). A stale secret shows as
> recurring `Login attempt failed from localhost (::1)` in the HA log.

---

## 6. Radio won't change (or plays wrong station)

**Symptom:** "mets RTL" runs the script (you hear "Terminé") but audio stays on the previous station.

**Root cause:** Music Assistant owns the satellite speaker; a `play_media` on the raw LVA player is overridden by MASS's queue. **Everything must target `media_player.enceinte_entree`.** For *spoken* commands there's also a TTS collision (the reply clobbers the just-started stream).

**Fix / correct design** (already in place — check it wasn't regressed):
- `script.radio_*` and the display `play_radio` path target `enceinte_entree`, not `rpi_satellite_media_player`.
- Voice path uses `script.radio_play(url)` (mode `restart`) that waits until `assist_satellite.rpi_satellite_satellite_assist == 'idle'` before playing.

**Verify:** `media_player.enceinte_entree` `media_content_id` contains the station's stream URL. Full explanation → [02 — Radio](02-pipelines-and-satellite.md#radio-the-music-assistant-ownership-trap).

---

## 7. Wake word wrong / reset

**Symptom:** wrong or no wake word after recreating the LVA container.

**Fix:** set `select.rpi_satellite_mot_d_activation` → **"Hey Jarvis"** (built-in). The custom "petit pois" model exists on the Pi but under-performs — do not use it.

---

## 8. Whisper Ready but STT still shows unavailable in HA

After the backend is confirmed healthy (port 10300 open, `Ready` in logs, GPU in use) the HA entity can lag `unavailable`. **Reload the Wyoming config entry** — see the reload command in [§1](#1-stt-dead--stt-provider-missing). It flips the entity `unavailable → unknown`.

---

## 9. Deploy caveat — reloading `script` cancels in-flight waits

Reloading the `script` component (`POST /api/services/script/reload`) **cancels any running script**, including pending `script.delayed_entity_action` waits (the scheduled-actions deferred mechanism) and the `script.radio_play` idle-wait. After deploying script changes, re-arm anything mid-wait. An HA restart orphans scheduled-action entries too — handled by the `scheduled_actions_recovery` automation. See [05-access-and-deploy.md](05-access-and-deploy.md).

---

## Quick reference — restart order

If unsure, restart bottom-up (backend first):
1. Fix GPU + `pct reboot 107` (dd-ai) — recovers whisper + ollama.
2. Reload HA Wyoming entry (`config_entries/entry/…/reload`) — reconnects STT/TTS.
3. `systemctl restart lva.service` (pi-satellite) — recovers wake word / timers / mic.
4. `systemctl restart voice-display.service` (pi-satellite) — recovers touch UI after a token fix.
