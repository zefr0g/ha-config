# CLAUDE.md — ha-config monorepo context

Everything is local, no cloud. HA host: `dd-ha:8123`. Language: French.

---

## Repo layout

```
ha-config/
├── automations/          — HA automation YAML files
├── esphome/              — ESPHome device configs (subtree-merged from standalone repo)
├── satellite/            — RPi4 voice assistant (subtree-merged from voice-assistant repo)
│   ├── src/              — Python daemons (LEDs, display, HA context)
│   ├── systemd/          — Service unit files
│   ├── wakeword_training/— microWakeWord training scripts
│   └── case/             — 3D case designs (hub_case_v3.scad + assets)
├── dashboard_*.yaml      — Lovelace dashboard files (deployed via push_dashboards.py)
├── scripts.yaml          — HA scripts (radio, PTZ camera, alarm, schedule helper)
├── sensors_*.yaml        — Template/history_stats sensors
├── input_boolean_piscine.yaml
├── push_dashboards.py    — Deploy dashboards to dd-ha via HA REST API
├── ha_history_service.py — Query entity history, returns voice-friendly summaries
└── coordinator.py        — Proxmox VE data coordinator
```

---

## Home Assistant instance (dd-ha)

- HA 2026.4.x on Proxmox QEMU VM
- Key addons: Whisper (STT), Piper (TTS), openWakeWord, Music Assistant, Mosquitto MQTT, ESPHome, Matter Server, Linky, rtl_433, Frigate (separate VM)

### Key entities / scripts
- `media_player.rpi_satellite_media_player` — voice satellite speaker
- `media_player.enceinte_entree` — MASS entry speaker
- `input_select.rpi_watchface` — satellite watchface (aurora/ember/signal)
- `script.radio_*` — 5 radio stations (France Inter, France Info, RTL, RTL2, Europe 2)
- `script.espkyogate_*` — alarm arm/disarm
- `script.ptz_*` — Ezviz garage camera PTZ

### Energy stack
- Solar: APSystems + Enphase Envoy + MSunPV inverter (`192.168.1.17`)
- Grid: Linky smart meter (teleinfo), tariff OHM Énergie (HC 0.1289 €/kWh, HP 0.1658 €/kWh)
- Templates: `templates.yaml` aggregates solar/grid into consumption sensors

### Devices
- Pool: ESPHome relay + Inkbird ITH20R temp sensor
- Irrigation: valve(s) driven by solar surplus automations
- Alarm: Bentel Kyogate via ESPHome (`esphome/espkyogate_configuration.yaml`)
- Climate: Mitsubishi AC (salon + couloir), MaxPilot radiators (3 bedrooms + bathroom)
- BLE sensors: Xiaomi ATC (multiple rooms)
- Camera: Reolink doorbell + Frigate NVR + go2rtc
- 3D printer: X4 Pro, Klipper/Moonraker

### Dashboards
Deploy with: `python3 push_dashboards.py`
Token in `.ha_token` (not committed — gitignored).

---

## Satellite (RPi4 — `pi-satellite`)

See `satellite/CLAUDE.md` for full hardware/software detail. Summary:

| Component | Module | Interface | Key detail |
|-----------|--------|-----------|------------|
| Microphone | INMP441 | I2S GPIO18/19/20 | 48kHz S32_LE stereo |
| Amp + speaker | MAX98357A | I2S GPIO18/19/21 | shared clock with mic |
| LED strip | WS2812B 3 LEDs | PWM GPIO12 | DMA channel **5**, 5V, 300Ω |
| Display | ST7796S 4.0" 480×320 (landscape) | SPI0 | 40MHz, `no_cs=True`, manual CS GPIO8 |
| Touch | XPT2046 (on display) | SPI0 CE1 | GPIO7 (T_CS), GPIO22 (T_IRQ) — reserved, no driver yet |

**Critical constraints:**
- SPI chunks ≤ 64 bytes — larger chunks trigger BCM2835 DMA, conflicts with I2S PCM DMA → `TimeoutError`
- No `subprocess.Popen` in display process — fork races with SPI DMA
- WS2812B DMA channel 5 only (channel 10 = only 1 LED lights)
- ST7796S: never toggle CS between chunks — resets write-address counter

**Wake word:** "Hey Jarvis" (built-in microWakeWord). A custom "petit pois" model exists at `~/.config/linux-voice-assistant/wakewords/petit_pois.tflite` on pi-satellite but is **not used** — it under-performs. Set via `select.rpi_satellite_mot_d_activation`. Note: recreating the LVA container resets this to a default, so re-select "Hey Jarvis" afterwards.

**Systemd services** (all running):
- `lva.service` (user dd) — LVA Docker container, ESPHome API → dd-ha:6053
- `voice-leds.service` (root) — LED daemon, Docker SDK log streaming → /tmp/va_state
- `voice-display.service` (root) — Pillow render loop (480×320), reads /tmp/va_state
- `voice-display-control.service` (dd) — MQTT bridge: display brightness/contrast/gamma/power in HA

**Deploy satellite changes:**
```bash
rsync -av satellite/src/ dd@pi-satellite:/home/dd/dev/voice-assistant/src/
ssh dd@pi-satellite "sudo systemctl restart voice-display.service"
```

---

## ESPHome (esphome/)

Deploy via ESPHome addon on dd-ha, or `esphome run <device>.yaml` locally.
Key devices: `satellite.yaml` (ESP32 satellite), `teleinfo.yaml` (Linky), `espkyogate_configuration.yaml` (alarm), `piscine.yaml` (pool), `maxpilot*.yaml` (heating).

---

## Do Not

- No cloud API calls — everything local
- No hard-coded IPs — use hostnames
- No subprocess.Popen in display daemon
- No SPI chunks > 64 bytes
- No Co-Authored-By lines in commits
