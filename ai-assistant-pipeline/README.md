# AI Assistant Pipeline — maintenance docs

Everything for the **local, cloud-free voice assistant**: wake word → speech-to-text →
LLM → text-to-speech, running across three machines on the home LAN.

> Language: French. Nothing leaves the LAN. HA host: `dd-ha:8123`.

## The 30-second mental model

```
  ┌─────────────────┐        stream audio        ┌──────────────────────────┐
  │  pi-satellite    │ ─────────────────────────► │  dd-ha  (HAOS VM 103)    │
  │  RPi4            │                            │  Assist orchestrator     │
  │  • "Hey Jarvis"  │ ◄───────────────────────── │  • pipelines             │
  │    (on-device)   │        TTS audio back      │  • wyoming + ollama      │
  │  • mic + speaker │                            │    integrations          │
  │  • touchscreen   │                            │  • Music Assistant       │
  └─────────────────┘                            └───────────┬──────────────┘
                                                             │ wyoming / http
                                                             ▼
                                              ┌────────────────────────────────┐
                                              │  dd-ai  (CT 107, RTX 3060 12GB) │
                                              │  • Whisper  STT  :10300  (GPU)  │
                                              │  • Ollama   LLM  :11434  (GPU)  │
                                              │  • Piper    TTS  :10200  (CPU)  │
                                              └────────────────────────────────┘
```

The **preferred pipeline** ("Home Assistant") is the production path:
`stt.faster_whisper` → `conversation.ollama_3060_12g` (gemma4:12b) → `tts.piper`.
All three heavy services live on **dd-ai** (Proxmox container 107, the RTX 3060 box).

## Documents

| File | What's in it |
|------|--------------|
| [01-architecture.md](01-architecture.md) | Full component/host/port/entity inventory + data flow |
| [02-pipelines-and-satellite.md](02-pipelines-and-satellite.md) | The 3 Assist pipelines, wake word, timers, radio quirks |
| [03-runbook.md](03-runbook.md) | **Troubleshooting** — every known failure mode + its fix |
| [04-dd-ai-gpu.md](04-dd-ai-gpu.md) | dd-ai GPU/CUDA maintenance, container recreate commands |
| [05-access-and-deploy.md](05-access-and-deploy.md) | How to reach each host, deploy HA config, rotate tokens |

## Fastest triage

| Symptom | Most likely cause | Go to |
|---------|-------------------|-------|
| `No speech-to-text provider for: stt.faster_whisper` | dd-ai GPU cgroup major drift → whisper crash-loop | [03 §1](03-runbook.md#1-stt-dead--stt-provider-missing) |
| Voice is slow / LLM answers wrong | ollama fell back to CPU (same GPU drift) | [03 §2](03-runbook.md#2-everything-slow-ollama-on-cpu) |
| Satellite unresponsive, mic "dead" | LVA container crash after Pi power loss | [03 §3](03-runbook.md#3-satellite-mic-dead--lva-crash-loop) |
| Timers stopped ringing | LVA ring flag stuck | [03 §4](03-runbook.md#4-timers-stopped-ringing) |
| Touch controls do nothing (radio/volume) | stale Pi HA token (401) | [03 §5](03-runbook.md#5-touch-controls-dead-radiovolume-no-op) |
| "Mets RTL" runs but audio doesn't change | Music Assistant owns the speaker | [03 §6](03-runbook.md#6-radio-wont-change-or-plays-wrong-station) |

_Sourced from the running system + accumulated operational notes, 2026-07-09._
