# 02 — Pipelines, wake word, timers & radio

## The three Assist pipelines

Listed via WebSocket (`assist_pipeline/pipeline/list`). **Preferred = "Home Assistant"** (id `01gzv84zrz4nw3vtjx28mh6h98`) — this is what the satellite uses.

| Pipeline | Conversation | STT | TTS | Wake word |
|----------|-------------|-----|-----|-----------|
| **Home Assistant** ⭐ | `conversation.ollama_3060_12g` (gemma4:12b) | `stt.faster_whisper` (GPU) | `tts.piper` (GPU) | `wake_word.openwakeword` / `okay_nabu` |
| Ollama local | `conversation.ollama_conversation_2` | `stt.faster_whisper` | `tts.wyoming_xtts` ⚠️ phantom | — |
| Assistant local complet | `conversation.home_assistant` (built-in, no LLM) | `stt.faster_whisper_addon` (add-on) | `tts.wyoming_xtts` ⚠️ phantom | — |

All French (`fr`), voice `fr_FR-siwis-medium`.

- The **satellite runs its own wake word** ("Hey Jarvis", on-device microWakeWord in LVA). The pipeline's `wake_word.openwakeword` entry is for HA-side detection on other assist devices.
- **Piper needs language `fr_FR`** (not `fr`) or synthesis fails.
- Editing a single pipeline: sed can't scope one pipeline inside the compact JSON — use the fetch→python-edit→push pattern (`scratchpad/edit_pipeline.py`) with `ha core stop`/`start`, or the WS `assist_pipeline/pipeline/update` command.

## Intent handling: prefer-local + LLM fallback

The preferred pipeline uses `conversation.ollama_3060_12g` with `llm_hass_api: ["assist"]` and **"Prefer handling commands locally" is ON**:

1. HA's deterministic intent engine tries first (device commands, exposed script aliases). Fast, no LLM, works even if Ollama is down.
2. Anything unmatched falls through to **gemma4:12b** for free-form questions.

Because the agent is an LLM, `custom_sentences/*` intent files are **not** the control path — the LLM calls exposed entities as tools. Known LLM failure modes:
- gemma **hallucinates tool calls** — says "Terminé" / "j'ai annulé le minuteur" but `success:[]` / never invoked the function.
- rare instant (~46 ms) `intent-failed` "Unexpected error during intent recognition" = an httpx `ConnectionError` reaching Ollama (intermittent).

Prefer-local shields the common device commands from both.

## Timers

Native HA timer intents work end-to-end on the satellite (start / status / cancel, French, both built-in and via Ollama).

- **Say "lance un minuteur de N minutes"** / "démarre un minuteur de N minutes" / "minuteur N minutes".
- **"mets un minuteur de N minutes" does NOT work** — the built-in French matcher returns a hollow "Terminé" with no timer and (under prefer-local) never escalates to the LLM. This is a default-HA limitation, not an Ollama bug. Overriding it via `custom_sentences` was tried and reverted.
- The Ollama system prompt steers delayed *device* actions ("éteins X dans 30 min") to `script.schedule_entity_action` and reserves `HassStartTimer` for plain reminders. See the scheduled-actions system (`input_text.scheduled_actions`, dashboards, recovery automation) — separate from the pipeline.
- **Stopping a timer ring** is voice-only — say **"stop"**. There is no HA/network path (see [03 §4](03-runbook.md#4-timers-stopped-ringing)).

## Radio (the Music Assistant ownership trap)

**Radio/music must play through the MASS player `media_player.enceinte_entree`, NOT the raw LVA player `media_player.rpi_satellite_media_player`.**

- Music Assistant **owns** the satellite speaker: `enceinte_entree.active_queue == rpi_satellite_media_player`. A `play_media` on the raw LVA player gets overridden by MASS's queue → stream never changes.
- Authoritative "what's playing" = `enceinte_entree`'s `media_content_id` (e.g. `builtin://radio/https://icecast.rtl.fr/rtl-1-44-128`).
- The 6 `script.radio_*` + `script.arreter_radio` all target `enceinte_entree` and carry French aliases ("mets France Inter", "arrête la radio"…) exposed to Assist.

**Voice radio TTS collision:** spoken "mets RTL" starts the stream *during* the pipeline, then the assistant's TTS reply (same single audio output) clobbers it. Fix already in place: voice scripts fire-and-forget `script.radio_play(url)` (mode `restart`) which waits `until assist_satellite.rpi_satellite_satellite_assist == 'idle'` (timeout 8 s) before playing. Dashboard/touch chips call `play_media` directly (no TTS, no wait). To add a station: mirror an existing `script.radio_*` (canonical URL + aliases + expose to conversation).

## Satellite services (pi-satellite)

| Service | User | Role |
|---------|------|------|
| `lva.service` | dd | LVA Docker container — wake word, mic stream, ESPHome API → `dd-ha:6053` |
| `voice-leds.service` | root | WS2812B LED daemon (Docker log stream → `/tmp/va_state`) |
| `voice-display.service` | root | Touchscreen render loop (480×320, reads `/tmp/va_state`) |
| `voice-display-control.service` | dd | MQTT bridge: display brightness/power in HA |

**Deploy satellite code changes:**
```bash
rsync -av satellite/src/ dd@pi-satellite:/home/dd/dev/voice-assistant/src/
ssh dd@pi-satellite "sudo systemctl restart voice-display.service"
```

Wake word select: `select.rpi_satellite_mot_d_activation` → **"Hey Jarvis"**. The custom "petit pois" model exists on the Pi but under-performs and is **not used**. **Recreating the LVA container resets the wake word** — re-select "Hey Jarvis" afterward.

Bluetooth A2DP speaker mode exists (menu ▸ Bluetooth tile). Full detail in `satellite/CLAUDE.md`.
