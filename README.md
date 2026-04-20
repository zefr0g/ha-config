# Linux Voice Assistant — Raspberry Pi 4

A fully local, self-hosted voice assistant running on a Raspberry Pi 4, integrated with [Home Assistant](https://www.home-assistant.io/) via the [linux-voice-assistant](https://github.com/OHF-Voice/linux-voice-assistant) project.

No cloud. No subscriptions. Whisper for speech recognition, Ollama for the LLM, Piper for text-to-speech — all running on a dedicated home server (`dd-ha`).

---

## Hardware

| Component | Module | Interface |
|-----------|--------|-----------|
| Microphone | INMP441 (I2S MEMS) | I2S |
| Amplifier | MAX98357A + 3W 4Ω speaker | I2S |
| LED feedback ring | WS2812B 12 LEDs RGB | PWM (GPIO12) |
| Display | GC9A01 1.28" Round TFT 240×240 | SPI |
| Main board | Raspberry Pi 4 | — |

See [WIRING.md](WIRING.md) for the full breadboard wiring diagram and GPIO pinout.

---

## Software Stack

### On the Raspberry Pi (`pi-satellite`)

| Layer | Tool |
|-------|------|
| OS | Raspberry Pi OS Lite (64-bit) |
| Voice assistant runtime | [linux-voice-assistant](https://github.com/OHF-Voice/linux-voice-assistant) (Docker) |
| Wake word detection | OpenWakeWord / MicroWakeWord |
| Audio I/O | PipeWire-pulse / ALSA (`googlevoicehat-soundcard`) |
| LED control | [rpi_ws281x](https://github.com/rpi-ws281x/rpi-ws281x-python) |
| Display | Custom GC9A01 SPI driver + Pillow renderer |
| Media playback | mpv (via LVA built-in) |

### On the Home Server (`dd-ha`)

| Layer | Tool |
|-------|------|
| Integration platform | Home Assistant |
| Speech-to-text | Whisper (local add-on) |
| LLM | Ollama |
| Text-to-speech | Piper |

---

## Architecture

```
[HA on dd-ha]  ←─ESPHome API:6053──►  [LVA Docker container]
                                              │ docker logs (Python SDK)
                             ┌────────────────┘
                             ▼
                   [LED daemon]      log line → state → WS2812B ring animation
                   [Display daemon]  reads /tmp/va_state + local clock/wifi/vol → GC9A01 screen
```

---

## Services

| Service | Purpose |
|---------|---------|
| `lva.service` | LVA Docker container (ESPHome API → HA Assist pipeline) |
| `voice-leds.service` | LED ring daemon (Docker log → animation) |
| `voice-display.service` | Display daemon (10 FPS Pillow render loop) |

---

## Getting Started

### 1. Hardware

Wire all components following [WIRING.md](WIRING.md). Prototype on a breadboard first.

### 2. OS Setup

```bash
# Flash Raspberry Pi OS Lite 64-bit with Raspberry Pi Imager
# Enable SSH and set hostname/wifi in the imager before flashing

# After first boot:
sudo apt update && sudo apt upgrade -y
sudo apt install -y git python3-pip python3-venv pipewire pipewire-alsa pipewire-pulse mpv python3-docker
sudo pip3 install rpi_ws281x spidev RPi.GPIO pillow numpy --break-system-packages
```

### 3. Enable Interfaces

`/boot/firmware/config.txt` (verified working):

```ini
# I2S bus — full-duplex: INMP441 capture + MAX98357A playback
dtparam=i2s=on
dtoverlay=googlevoicehat-soundcard

# SPI — GC9A01 display
dtparam=spi=on

# Disable analog audio (using I2S instead)
dtparam=audio=off
```

Then reboot. Audio will appear as ALSA card 0 at 48kHz / 32-bit stereo.

### 4. Install systemd services

```bash
sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable lva voice-leds voice-display
sudo systemctl start lva voice-leds voice-display
```

---

## Project Structure

```
voice-assistant/
├── README.md           — this file
├── WIRING.md           — full hardware wiring diagram
├── CLAUDE.md           — AI assistant context
├── src/
│   ├── config.py       — shared constants (GPIO, states, colors)
│   ├── leds/
│   │   ├── ring.py     — thread-safe WS2812B wrapper
│   │   ├── animations.py — per-state animation threads
│   │   └── daemon.py   — Docker log streaming → ring
│   └── display/
│       ├── driver.py   — GC9A01 SPI driver
│       ├── ui.py       — Pillow frame renderer
│       └── daemon.py   — 10 FPS render loop
└── systemd/
    ├── lva.service
    ├── voice-leds.service
    └── voice-display.service
```

---

## Hardware Gotchas

> **WS2812B:** use DMA channel 5, GPIO 12 (PWM0). DMA channel 10 causes single-LED signal issue.
>
> **GC9A01:** set `spi.no_cs = True` and control CS (GPIO 8) manually. SPI chunks must be ≤ 64 bytes when audio is active — larger chunks trigger BCM2835 SPI DMA which conflicts with I2S PCM DMA and causes `TimeoutError: [Errno 110]`. Max reliable SPI speed on breadboard: 20 MHz.

---

## Features

- [x] Hardware wiring diagram
- [x] All peripherals verified (mic, amp, LED ring, display)
- [x] LED ring state machine (idle / listening / processing / speaking / error)
- [x] GC9A01 display UI (clock, rotating arcs, state text — French)
- [x] LVA Docker container (ESPHome API → HA Assist)
- [x] Systemd services for auto-start
- [ ] End-to-end wake word test
- [ ] Radio / media playback via HA media_player entity → LVA mpv

---

## References

- [OHF-Voice/linux-voice-assistant](https://github.com/OHF-Voice/linux-voice-assistant)
- [INMP441 datasheet](https://invensense.tdk.com/wp-content/uploads/2015/02/INMP441.pdf)
- [MAX98357A datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/MAX98357A-MAX98357B.pdf)
- [rpi_ws281x library](https://github.com/rpi-ws281x/rpi-ws281x-python)
- [RPi GPIO pinout](https://pinout.xyz)
