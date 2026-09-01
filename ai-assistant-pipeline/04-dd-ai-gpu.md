# 04 — dd-ai GPU & container maintenance

The AI stack lives in **Proxmox CT 107 (`dd-ai`)** with the **RTX 3060 12 GB** passed through. Reach it via `ssh root@prox` → `pct exec 107 -- …`.

## GPU passthrough — the recurring gotcha

The container gets the GPU through:
- **cgroup device allows** in `/etc/pve/lxc/107.conf`:
  ```
  lxc.cgroup2.devices.allow: c 195:* rwm   # nvidia0 / nvidiactl
  lxc.cgroup2.devices.allow: c <N>:* rwm   # nvidia-uvm  ← DRIFTS, must match host
  lxc.cgroup2.devices.allow: c 235:* rwm   # nvidia-caps
  ```
- **bind mounts** of `/dev/nvidia0`, `/dev/nvidiactl`, `/dev/nvidia-uvm`, `/dev/nvidia-uvm-tools`, `/dev/nvidia-caps/nvidia-cap{1,2}`.

`nvidia-smi`/NVML only need `/dev/nvidia0`+`/dev/nvidiactl` (major **195**, stable). CUDA `cuInit` additionally needs `/dev/nvidia-uvm`, whose major is **dynamically allocated and changes on every driver/module reload**. When it drifts past the hardcoded allow, CUDA dies (`cuInit failed: 999` / "CUDA unknown error") while `nvidia-smi` still works. This is the single most common outage — full fix procedure in [03 §1](03-runbook.md#1-stt-dead--stt-provider-missing).

Check anytime:
```bash
ssh root@prox "ls -l /dev/nvidia-uvm; grep cgroup2.devices.allow /etc/pve/lxc/107.conf"
# the number after 'crw-rw-rw- 1 root root 508,' must appear as 'c 508:* rwm'
```
Host driver: RTX 3060, driver **610.43.02** (`nvidia-smi` on prox).

## Containers — recreate reference

All three are plain `docker run` (no compose), `restart=unless-stopped`. Normally you never recreate them — a `pct reboot 107` restarts everything cleanly. Recreate only if a container's config itself is wrong.

### whisper (STT, GPU) — `whisper-gpu:latest`

Custom image because the stock `rhasspy/wyoming-whisper` is CPU-only. Built from `/opt/whisper-gpu/Dockerfile` (`python:3.11-slim` + `wyoming-faster-whisper nvidia-cublas-cu12 nvidia-cudnn-cu12`, `LD_LIBRARY_PATH` → the pip nvidia libs).

```bash
docker run -d --name whisper --runtime=nvidia --restart unless-stopped \
  -e NVIDIA_VISIBLE_DEVICES=all -e NVIDIA_DRIVER_CAPABILITIES=all \
  -e LD_LIBRARY_PATH=/usr/local/lib/python3.11/site-packages/nvidia/cublas/lib:/usr/local/lib/python3.11/site-packages/nvidia/cudnn/lib \
  -p 10300:10300 -v /opt/whisper-data:/data \
  whisper-gpu:latest \
  --model large-v3-turbo --language fr --device cuda --compute-type int8_float16 --beam-size 1
```
- `int8_float16` is the chosen precision — `float16` added ~1 GB VRAM for imperceptible accuracy gain (reverted). ~1.16 GB VRAM, ~0.7 s inference.
- The image ENTRYPOINT supplies `--uri tcp://0.0.0.0:10300` and `--data-dir/--download-dir /data`.
- large-v3-turbo is the best French+HA STT tradeoff (non-turbo large-v3 = 6× compute, not worth it).

### ollama (LLM, GPU) — `ollama/ollama`

```bash
docker run -d --name ollama --runtime=nvidia --restart unless-stopped \
  -e NVIDIA_VISIBLE_DEVICES=all -e NVIDIA_DRIVER_CAPABILITIES=all \
  -e OLLAMA_FLASH_ATTENTION=1 -e OLLAMA_KV_CACHE_TYPE=q8_0 \
  -e OLLAMA_NUM_PARALLEL=1 -e OLLAMA_KEEP_ALIVE=-1 \
  -p 11434:11434 -v /opt/ollama:/root/.ollama \
  ollama/ollama
```
- **Flash-attn ~2×'d prompt eval** (162→330 tok/s = lower voice latency); **q8 KV cache** shrank the footprint.
- `KEEP_ALIVE=-1` keeps `gemma4:12b` resident (~8 GB) so there's no cold-load per command.
- Models: `gemma4:12b` (production, ~8 GB, 100% GPU at ctx 8096, tool-calling works) and `gemma4:e4b` (lighter fallback). Pull with `docker exec ollama ollama pull <model>`.

### piper (TTS, CPU) — `rhasspy/wyoming-piper`

```bash
docker run -d --name piper --restart unless-stopped \
  -p 10200:10200 -v /opt/piper-data:/data \
  rhasspy/wyoming-piper --voice fr_FR-siwis-medium
```
CPU-only. TTS stays Piper by user decision. **Kokoro was tried and rejected** — the `nordwestt/kokoro-wyoming` image has no `misaki`/`espeak-ng` phonemizer, so its French voice reads French with English g2p (gibberish). A better-than-piper French TTS later would be **XTTS v2** (~2 GB VRAM, rebalance whisper to CPU) or a properly-phonemized Kokoro (Kokoro-FastAPI + wyoming bridge). **Lesson: verify any new TTS via a TTS→STT round-trip before trusting it.**

## Changing the Ollama model in HA

The conversation entity is `conversation.ollama_3060_12g`. To point HA at a different model, edit the Ollama config-entry **subentry** in `/config/.storage/core.config_entries` on dd-ha (the rich system prompt — TV channels, `schedule_entity_action`, satellite volumes — lives there and must be preserved):
```bash
ssh root@dd-ha "ha core stop"      # safe .storage edit; back up first
# ...edit the subentry model + prompt...
ssh root@dd-ha "ha core start"
```
> HA's built-in *OpenAI Conversation* integration rejects a custom `base_url` (only `api.openai.com`) — that's why this stack uses **Ollama's native HA integration**, not an OpenAI-compatible endpoint.

## Health snapshot commands

```bash
# containers
ssh root@prox "pct exec 107 -- docker ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'"
# GPU + compute apps
ssh root@prox "pct exec 107 -- nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader; \
  pct exec 107 -- nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv"
# ollama on GPU?
ssh root@prox "pct exec 107 -- docker exec ollama ollama ps"
# ollama models
curl -s http://dd-ai.home:11434/api/tags | python3 -m json.tool
# wyoming ports reachable from the LAN
for p in 10300 10200 11434; do timeout 2 bash -c "cat </dev/null >/dev/tcp/dd-ai.home/$p" && echo "$p OPEN" || echo "$p DOWN"; done
```

Healthy budget: gemma4:12b ~8 GB + whisper ~1.16 GB ≈ **9.3 / 12 GB**. CT 107 sized 8c / 8–16 GB RAM (GPU does the heavy lifting).
