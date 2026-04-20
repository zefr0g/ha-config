# CLAUDE.md — AI Assistant Context

This file gives Claude context about the project so it can assist effectively across sessions.

---

## Project

**Linux Voice Assistant** running on a Raspberry Pi 4.
Fully local, no cloud. Integrated with Home Assistant on `dd-ha` (same LAN).

Backend services already running on `dd-ha`:
- **Whisper** — speech-to-text
- **Ollama** — local LLM
- **Piper** — text-to-speech
- **Home Assistant** — orchestration / Assist platform

Upstream framework: https://github.com/OHF-Voice/linux-voice-assistant

---

## Hardware (Raspberry Pi 4)

| Component | Module | Interface | GPIO / Pins |
|-----------|--------|-----------|-------------|
| Microphone | INMP441 (I2S) | I2S | GPIO 18 (BCLK), 19 (LRCLK), 20 (RX) |
| Amplifier | MAX98357A (I2S) | I2S | GPIO 18 (BCLK), 19 (LRCLK), 21 (TX) |
| Speaker | 3W 4Ω full range | — | via MAX98357A SPK+/− |
| LED strip | WS2812B 3 LEDs | PWM | GPIO 12 (PWM0), via 300Ω resistor |
| Display | GC9A01 1.28" round 240×240 | SPI0 | GPIO 8 (CS), 10 (MOSI), 11 (CLK), 23 (BLK), 24 (DC), 25 (RST) |

Full wiring in [WIRING.md](WIRING.md).

---

## Key Technical Decisions

- **I2S for both mic and amp** — INMP441 and MAX98357A share BCLK (GPIO18) and LRCLK (GPIO19). No conflict because mic is input-only and amp is output-only.
- **`googlevoicehat-soundcard` overlay** — used for full-duplex I2S (not `hifiberry-dac`). Exposes capture (INMP441) and playback (MAX98357A) on a single ALSA card 0 at 48kHz/32-bit stereo. Analog audio (`dtparam=audio=off`) is disabled.
- **GPIO12 for WS2812B** — GPIO18 (PCM_CLK) is taken by I2S. GPIO12 (PWM0) is the correct pin for `rpi_ws281x`. Use **DMA channel 5** (channel 10 caused only 1 LED to light). VDD on 5V, data via 300Ω series resistor.
- **SPI0 for display** — GC9A01 uses hardware SPI0. GPIO10/11 are MOSI/CLK, GPIO8 is CE0.
- **GC9A01 requires manual CS control** — `spi.no_cs = True` must be set and CS (GPIO8) toggled manually. `spi.xfer2()` toggling CS between chunks resets the display's write-address counter, causing only the first row to render. SPI speed: 20MHz (40MHz unreliable on breadboard with jumper wires).
- **No PWM audio** — audio goes through I2S, which frees PWM0 (GPIO12) for WS2812B.
- **SPI chunk size = 64 bytes** — BCM2835 SPI uses DMA for transfers ≥ ~96 bytes. BCM2835 I2S PCM also uses DMA. When the LVA audio container has the audio device open, SPI DMA causes `TimeoutError: [Errno 110]`. Sending data in 64-byte chunks forces PIO mode and avoids the conflict.
- **LVA uses ESPHome API** — connects to HA at port 6053 via Zeroconf/mDNS. Not Wyoming protocol.
- **State IPC via `/tmp/va_state`** — LED daemon follows docker logs (Docker Python SDK, no subprocess fork), writes current state string. Display daemon reads this file each frame. No threads in display process.
- **Display daemon: zero threads, zero subprocesses** — single-threaded 10 FPS render loop. Subprocess forks during SPI transfers cause ioctl races.

---

## Hardware — Verified Working Config

All four peripherals bench-tested and confirmed:

| Component | Test result | Key settings |
|-----------|-------------|--------------|
| INMP441 mic | 81% full-scale signal at 48kHz | `hw:0,0`, S32_LE, stereo |
| MAX98357A amp | Clean playback | `hw:0,0`, S32_LE, 48kHz stereo |
| WS2812B strip | 3 LEDs, full RGB | DMA=5, GPIO12, 5V VDD |
| GC9A01 display | Full-screen color fills | SPI 20MHz, `no_cs=True`, manual GPIO8 CS |

---

## Current Status

- Phase: **Software deployed** — all daemons running as systemd services.
- `voice-leds.service` — running (LED ring, Docker SDK log streaming)
- `voice-display.service` — running (10 FPS render loop, no crashes)
- `lva.service` — LVA Docker container, connects to HA on `dd-ha`

---

## Services

| Service | File | User | Purpose |
|---------|------|------|---------|
| `lva.service` | `systemd/lva.service` | dd | LVA Docker container (docker compose up in /home/dd/lva/) |
| `voice-leds.service` | `systemd/voice-leds.service` | root | LED ring daemon (DMA/PWM requires root) |
| `voice-display.service` | `systemd/voice-display.service` | root | Display daemon (SPI/GPIO requires root) |

---

## Source Layout

```
src/
├── config.py          — shared constants (GPIO, LED, states, colors)
├── leds/
│   ├── ring.py        — thread-safe PixelStrip wrapper
│   ├── animations.py  — per-state animation threads
│   └── daemon.py      — Docker log streaming → state → ring
└── display/
    ├── driver.py      — GC9A01 SPI driver (manual CS, 64-byte chunks)
    ├── ui.py          — Pillow frame renderer (port of ESPHome C++ lambda)
    └── daemon.py      — 10 FPS single-threaded render loop
```

---

## Goals (in order)

1. ~~Get audio pipeline working (INMP441 → ALSA → PipeWire, MAX98357A playback)~~ ✓
2. ~~LED ring state machine~~ ✓
3. ~~GC9A01 display UI (clock face, animated feedback)~~ ✓
4. ~~Systemd services for auto-start~~ ✓
5. End-to-end test: wake word → LED state changes → display state text
6. Radio / media playback via HA media_player entity → LVA mpv → MAX98357A

---

## Coding Conventions

- Language: **Python 3.11+**
- Style: Black + isort
- No unnecessary abstractions — keep modules small and focused
- Each hardware peripheral gets its own module under `src/`

---

## Environment

- Pi hostname: `pi-satellite`
- Pi user: `dd` (root for hardware daemons)
- HA host: `dd-ha`
- Dev machine syncs via rsync: `rsync -av src/ dd@pi-satellite:/home/dd/dev/voice-assistant/src/`

---

## Do Not

- Do not add cloud API calls — everything must be local
- Do not hard-code IP addresses — use hostnames
- Do not use subprocess.Popen in the display process — fork races with SPI DMA
- Do not use SPI chunks > 64 bytes — triggers BCM2835 DMA, conflicts with I2S PCM DMA
