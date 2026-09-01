# 01 — Architecture

## Hosts

| Host | What it is | Address | Reach it via |
|------|-----------|---------|--------------|
| **prox** | Proxmox VE hypervisor (B550M + Ryzen 5700G, 30 GB RAM, **RTX 3060 12 GB**) | `192.168.x.x` | `ssh root@prox` |
| **dd-ai** | LXC **CT 107** — the AI stack (STT/LLM/TTS) | `192.168.x.x` / `dd-ai.home` | `ssh root@prox` → `pct exec 107 -- …` |
| **dd-ha** | Home Assistant OS — **VM 103** `dd-haos` on prox | `dd-ha:8123` | `ssh root@dd-ha` (config); REST from workstation |
| **pi-satellite** | RPi4 voice satellite (mic, speaker, touchscreen) | `pi-satellite` | `ssh dd@pi-satellite` |

> Direct `ssh dd@dd-ai` / `ssh root@dd-ai` fail (key not authorized) — **always go through `ssh root@prox` then `pct exec 107`**.

Other guests on the same prox host: CT 105 pihole, CT 106 frigate (uses the **iGPU** `renderD128`, *not* the 3060 — no VRAM contention), VM 102 dd-nas. HA itself is VM 103.

## The AI stack on dd-ai (CT 107)

Three plain `docker run` containers (no compose), all `restart=unless-stopped`:

| Container | Image | Port | Device | HA entity | Model / voice |
|-----------|-------|------|--------|-----------|---------------|
| `whisper` | `whisper-gpu:latest` (custom build) | 10300 | **GPU** | `stt.faster_whisper` | `large-v3-turbo`, fr, `int8_float16` |
| `ollama`  | `ollama/ollama` | 11434 | **GPU** | `conversation.ollama_3060_12g` | `gemma4:12b` (fallback `gemma4:e4b`) |
| `piper`   | `rhasspy/wyoming-piper` | 10200 | CPU | `tts.piper` | `fr_FR-siwis-medium` |

**VRAM budget (12 GB):** ollama gemma4:12b ~8 GB (resident, `keep_alive=-1`) + whisper ~1.16 GB ≈ **9.3 / 12 GB**, ~2.7 GB free. Piper is CPU-only.

Data dirs on dd-ai: `/opt/ollama`, `/opt/whisper-data`, `/opt/piper-data`, `/opt/whisper-gpu` (Dockerfile). llama.cpp is **parked** (`/opt/hf-cache`, `/opt/llama-cache`) — not in use.

Details of the container run commands, the custom whisper image, and Ollama perf env → [04-dd-ai-gpu.md](04-dd-ai-gpu.md).

## Data flow (a single voice command)

```
 "Hey Jarvis" ── on-device microWakeWord in LVA (pi-satellite)
      │  (opens the stream)
      ▼
 mic audio ──► dd-ha Assist pipeline "Home Assistant"
      │
      ├─ STT  : stt.faster_whisper ──wyoming──► dd-ai.home:10300  (Whisper, GPU) ──► French text
      │
      ├─ Intent: HA tries built-in intents FIRST (prefer-local ON)
      │          └─ falls through to conversation.ollama_3060_12g ──http──► dd-ai.home:11434 (gemma4:12b)
      │
      └─ TTS  : tts.piper ──wyoming──► dd-ai.home:10200 (Piper, CPU) ──► French audio
                     │
                     ▼
              played on the satellite speaker (LVA mpv / tts_player)
```

Warm round-trip ≈ 1.5–2 s (GPU STT ~0.4 s + warm LLM ~0.85 s + piper ~0.3 s). First command after idle ≈ 3 s (full system-prompt processing).

## Home Assistant integrations (on dd-ha)

Wyoming config entries (`/config/.storage/core.config_entries`, `domain: wyoming`):

| Title | Host:Port | Provides | Role |
|-------|-----------|----------|------|
| **faster-whisper** | `dd-ai.home:10300` | `stt.faster_whisper` | **STT (production, GPU)** |
| **piper** | `dd-ai.home:10200` | `tts.piper` | **TTS (production)** |
| Whisper (add-on) | `core-whisper:10300` | `stt.faster_whisper_addon` | STT fallback (HAOS add-on) |
| Piper (add-on) | `core-piper:10200` | `tts.piper_addon` | TTS fallback (HAOS add-on) |
| openWakeWord | `core-openwakeword:10400` | `wake_word.openwakeword` | wake-word engine |

Config-entry IDs worth knowing:
- **dd-ai whisper** entry `01KWQ49XNTZ5ZKN3J1906GVZXW` — reload this after fixing the GPU (see [03 §1](03-runbook.md#1-stt-dead--stt-provider-missing)).

### Cleaned up 2026-07-09

Three dead Wyoming entries (destroyed/removed machines) were deleted, so the STT/TTS
list is now exactly the four entries above — no `unavailable` junk:

| Removed entity | Was | Config entry (deleted) |
|--------|-----|--------------|
| `stt.faster_whisper_2` | `dd-tts.home:10300` (destroyed "Whisper TTS Prox") | `01KQ38737CB4X0M0HD46GEV4HM` |
| `stt.faster_whisper_dd_room` | `dd-room.local:10300` | `01KNWHWSX1RA1YSTJ9F8JG58FR` |
| `tts.kokoro` | `dd-ai:10210` (Kokoro tried & rejected — English g2p on French) | `01KWQAGEXXCETTN24SSNVC6JKC` |

One loose end remains: `tts.wyoming_xtts` is a **phantom** engine (no entity behind it)
still referenced by the non-preferred pipelines "Ollama local" and "Assistant local
complet" — their TTS is dead until repointed to `tts.piper` / `tts.piper_addon`.

> **Naming (cleaned up 2026-07-09):** the **production GPU** services own the clean
> names `stt.faster_whisper` / `tts.piper`; the HAOS add-on fallbacks were demoted to
> `stt.faster_whisper_addon` / `tts.piper_addon`. Previously the GPU services carried
> `_3` / `_2` suffixes (HA registration order) because dead entries held the base names.

## pi-satellite hardware (summary)

Full detail in `satellite/CLAUDE.md`. Key parts: INMP441 mic (I2S), MAX98357A amp + speaker (I2S), WS2812B 3-LED strip, ST7796S 4.0" 480×320 touchscreen. Wake word **"Hey Jarvis"** (built-in microWakeWord, on-device). The LVA (Linux Voice Assistant) Docker container connects to HA over the ESPHome API (`dd-ha:6053`).
