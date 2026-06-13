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
| Display | **ST7796S 4.0" TFT 480×320 (landscape)** | SPI0 | GPIO 8 (CS/CE0), 10 (MOSI), 11 (CLK), 23 (BLK), 24 (DC), 25 (RST) |
| Touch | **XPT2046 resistive (on display module)** | SPI0 | GPIO 7 (T_CS/CE1), 22 (T_IRQ) — **reserved, not yet driven** |

> **Display migration (2026):** replaced the original GC9A01 1.28" round 240×240 panel
> with a 4.0" ST7796S 480×320 landscape touchscreen. The touch controller (XPT2046,
> shares SPI0 on CE1) is wired and its pins are reserved in `config.py`, but **no touch
> driver exists yet** — see Goals.

Full wiring in [WIRING.md](WIRING.md).

---

## Key Technical Decisions

- **I2S for both mic and amp** — INMP441 and MAX98357A share BCLK (GPIO18) and LRCLK (GPIO19). No conflict because mic is input-only and amp is output-only.
- **`googlevoicehat-soundcard` overlay** — used for full-duplex I2S (not `hifiberry-dac`). Exposes capture (INMP441) and playback (MAX98357A) on a single ALSA card 0 at 48kHz/32-bit stereo. Analog audio (`dtparam=audio=off`) is disabled.
- **GPIO12 for WS2812B** — GPIO18 (PCM_CLK) is taken by I2S. GPIO12 (PWM0) is the correct pin for `rpi_ws281x`. Use **DMA channel 5** (channel 10 caused only 1 LED to light). VDD on 5V, data via 300Ω series resistor.
- **SPI0 for display** — ST7796S uses hardware SPI0. GPIO10/11 are MOSI/CLK, GPIO8 is CE0. The XPT2046 touch controller sits on the same bus at CE1 (GPIO7).
- **ST7796S requires manual CS control** — `spi.no_cs = True` must be set and CS (GPIO8) toggled manually. Toggling CS between pixel chunks resets the panel's write-address counter, so CS is held LOW for the *entire* pixel transfer in `blit_frame()`. The fd is set `FD_CLOEXEC` defensively.
- **SPI speed = 40 MHz** — the satellite now uses a **soldered proto-hat** (not a breadboard), which is reliable at 40 MHz. The original GC9A01 was limited to 20 MHz on breadboard with jumper wires. A full 480×320 RGB565 frame is **307 KB**; >25 MHz is needed to push 10 FPS.
- **SPI chunk size = 64 bytes** — BCM2835 SPI uses DMA for transfers ≥ ~96 bytes. BCM2835 I2S PCM also uses DMA. When the LVA audio container has the audio device open, SPI DMA causes `TimeoutError: [Errno 110]`. Sending data in 64-byte chunks (`writebytes2`) forces PIO mode and avoids the conflict. **Cost:** 307 KB ÷ 64 = ~4800 `writebytes2` calls per frame — this is the dominant CPU cost (see Known Issues).
- **MADCTL `0xE8` + INVOFF** — landscape orientation, BGR, rotated 180°. This particular panel renders correctly with inversion *off* (`0x20`).
- **Display tunables exposed to HA** — brightness (software PWM on GPIO23), contrast (VCMPCTL `0xC5`), gamma preset (natural/vivid/soft/warm), and power (DISPON/DISPOFF) are all controllable from Home Assistant via an MQTT-discovery bridge (`control.py`). See Services.
- **No PWM audio** — audio goes through I2S, which frees PWM0 (GPIO12) for WS2812B.
- **LVA uses ESPHome API** — connects to HA at port 6053 via Zeroconf/mDNS. Not Wyoming protocol.
- **State IPC via `/tmp/va_state`** — LED daemon follows docker logs (Docker Python SDK, no subprocess fork), writes current state string. Display daemon reads this file each frame. No threads in display process.
- **Display config IPC via `/tmp/display_config.json`** — `control.py` (MQTT) writes it; `daemon.py` reads it each frame and applies only the deltas (brightness/contrast/gamma/power).
- **Display daemon: zero threads, zero subprocesses** — single-threaded render loop. Subprocess forks during SPI transfers cause ioctl races. (`GPIO.PWM` for backlight manages its own internal thread but never touches SPI.)

---

## Hardware — Verified Working Config

| Component | Test result | Key settings |
|-----------|-------------|--------------|
| INMP441 mic | 81% full-scale signal at 48kHz | `hw:0,0`, S32_LE, stereo |
| MAX98357A amp | Clean playback | `hw:0,0`, S32_LE, 48kHz stereo |
| WS2812B strip | 3 LEDs, full RGB | DMA=5, GPIO12, 5V VDD |
| ST7796S display | Full-screen color fills, "Horizon Rising" UI | SPI 40MHz, `no_cs=True`, manual GPIO8 CS, 64-byte chunks |
| XPT2046 touch | **Untested — no driver** | reserved on CE1 (GPIO7), IRQ GPIO22 |

---

## Current Status

- Phase: **Display migrated to ST7796S, software deployed** — all daemons running as systemd services.
- `lva.service` — LVA Docker container, connects to HA on `dd-ha`
- `voice-leds.service` — running (LED ring, Docker SDK log streaming)
- `voice-display.service` — running ("Horizon Rising" 480×320 render loop)
- `voice-display-control.service` — running (MQTT bridge, display tunables in HA)

### Known Issues / Things to improve

- **Display daemon pegs ~98% of one CPU core.** The render loop never reaches its
  `time.sleep()` — per-frame work exceeds the 100 ms budget, so effective FPS is below
  the 10 FPS target. Two causes: (1) per-pixel numpy glow/waveform compute over the full
  307 KB array every frame, (2) ~4800 64-byte `writebytes2` syscalls per frame. Ideas:
  dirty-rectangle / partial-window updates (only the waveform + clock change), lower the
  target FPS, or precompute the static background once and composite the dynamic layer.
- **Touch is wired but unused** — XPT2046 on CE1, IRQ on GPIO22, pins reserved in
  `config.py`, but there is no touch driver and nothing reads it. This is the obvious next
  feature (tap to wake / dismiss / navigate watchfaces).
- **Stale `ui.py`** — the old GC9A01 240×240 renderer (`display/ui.py`) is still present in
  the repo and on the Pi but is **not imported**; `daemon.py` uses `display_ui.py`. Safe to
  delete. A leftover `display.zip` also sits in the deployed dir on the Pi.
- **Stale boot-config comment** — `/boot/firmware/config.txt` on the Pi still labels SPI as
  "# SPI (GC9A01 round display)". Cosmetic.

---

## Services

| Service | File | User | Purpose |
|---------|------|------|---------|
| `lva.service` | `systemd/lva.service` | dd | LVA Docker container (docker compose up in /home/dd/lva/) |
| `voice-leds.service` | `systemd/voice-leds.service` | root | LED ring daemon (DMA/PWM requires root) |
| `voice-display.service` | `systemd/voice-display.service` | root | Display render loop (SPI/GPIO requires root) |
| `voice-display-control.service` | `systemd/voice-display-control.service` | dd | MQTT discovery bridge → display tunables in HA |

---

## Display UI ("Ambient" — touch)

A calm full-bleed clock home screen (Roboto Thin). Tap anywhere → a two-button
menu (Radio / Minuteur). Each opens a focused, touch-driven control screen that
calls Home Assistant services. When the assistant is listening/speaking, a
glowing waveform rises from the bottom and the accent colour shifts per state.

- **Dirty-rectangle rendering** — the controller renders a full 480×320 image;
  the daemon diffs it against what's on the panel (numpy) and pushes only the
  changed bounding box over SPI. Idle pushes ~nothing → idle CPU dropped from
  **98% to ~10%**. Render cadence: 20 Hz while animating, 2 Hz at idle (colon
  blink); touch is polled at 20 Hz regardless.
- **Touch** — XPT2046 on SPI0/CE1 (`spidev0.1`, 1 MHz), pen IRQ on GPIO22. Taps
  are edge-triggered on release. Calibration is an affine raw→screen map per axis
  (`swap` + `mx,cx,my,cy`) least-squares-fit from 4 corner taps, stored in
  `.touch_calib.json`; (re)generate with `display/calibrate.py`.
- **HA actions** (`ha_actions.py`) — radio plays directly on the satellite
  (`media_player.play_media`, 5 stations + stop), volume via `volume_set`,
  timers via the conversation agent (same path as voice timers).

## Source Layout

```
src/
├── config.py          — shared constants (GPIO, LED, display, touch pins, states, colors)
├── ha_context.py      — HA read path (media, timers, volume, weather) — polled ~5 s
├── leds/              — LED ring daemon + animations
└── display/
    ├── driver.py      — ST7796S SPI driver: blit_frame + blit_rect (dirty-rect), gamma/contrast/brightness/power
    ├── theme.py       — palette, fonts (Roboto), per-state accent, background, RGB565
    ├── touch.py       — XPT2046 driver (edge-triggered taps, calibration)
    ├── ha_actions.py  — HA service calls (radio / volume / timers)
    ├── app.py         — UI controller + Home/Menu/Radio/Timer screens + voice overlay
    ├── daemon.py      — loop: poll touch → render → diff → blit changed rect
    ├── control.py     — MQTT-discovery bridge for display tunables
    ├── calibrate.py   — interactive touch calibration (run with daemon stopped)
    ├── shot.py        — headless PNG preview of every screen (design iteration)
    └── display_ui.py, ui.py — ⚠ STALE old renderers, unused (delete candidates)
```

---

## Goals (in order)

1. ~~Get audio pipeline working (INMP441 → ALSA → PipeWire, MAX98357A playback)~~ ✓
2. ~~LED ring state machine~~ ✓
3. ~~Display UI (clock face, animated feedback)~~ ✓ (now ST7796S 480×320)
4. ~~Systemd services for auto-start~~ ✓
5. ~~Display tunables (brightness/contrast/gamma/power) exposed in HA over MQTT~~ ✓
6. **Cut display-daemon CPU usage** — partial updates / static-background compositing
7. **Touch support** — XPT2046 read loop (tap-to-wake, dismiss, watchface switching)
8. Radio / media playback via HA media_player entity → LVA mpv → MAX98357A
9. Delete stale `ui.py` and the Pi's leftover `display.zip`

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
  then `ssh dd@pi-satellite "sudo systemctl restart voice-display.service"`

---

## Do Not

- Do not add cloud API calls — everything must be local
- Do not hard-code IP addresses — use hostnames
- Do not use subprocess.Popen in the display process — fork races with SPI DMA
- Do not use SPI chunks > 64 bytes — triggers BCM2835 DMA, conflicts with I2S PCM DMA
- Do not toggle CS between pixel chunks — resets the ST7796S write-address counter
