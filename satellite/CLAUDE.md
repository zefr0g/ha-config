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
- `voice-splash.service` — oneshot boot splash at 7.3s uptime
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
- **Mic placement caps AEC performance** — `hub_case_v6.scad` keeps the v5 layout:
  `mic_cut()` on the **top** face with the INMP441 glued into a pocket, speaker on
  bosses on the **rear** wall. Three coupling paths, only one of which is distance:
  (1) mic and speaker share one rigid shell, so vibration reaches the diaphragm
  through the plastic with different timing than the airborne path; (2) the mic
  pocket vents into the interior air volume, so the speaker's *back* wave hits the
  mic from inside — moving the mic to the front face alone does not fix this;
  (3) top and rear are adjacent faces, so the mic sits in the speaker's
  edge-diffracted output. Fix before printing v6: front-mount the mic, seal the
  pocket from the interior, and gasket both the mic PCB and the speaker rim
  (foam/silicone) instead of gluing. This is what limits wake-word-over-music
  (see the AEC section), not the software.

---

## Services

| Service | File | User | Purpose |
|---------|------|------|---------|
| `lva.service` | `systemd/lva.service` | dd | LVA Docker container (docker compose up in /home/dd/lva/) |
| `voice-leds.service` | `systemd/voice-leds.service` | root | LED ring daemon (DMA/PWM requires root) |
| `voice-splash.service` | `systemd/voice-splash.service` | root | Boot splash — pushes `assets/boot_splash.rgb565` at 7.3s uptime, before Python can afford numpy/Pillow (see `docs/boot-tuning.md`) |
| `voice-display.service` | `systemd/voice-display.service` | root | Display render loop (SPI/GPIO requires root); shows a live boot checklist until the voice stack is up |
| `voice-display-control.service` | `systemd/voice-display-control.service` | dd | MQTT discovery bridge → display tunables in HA |
| `bt-agent.service` | `systemd/bt-agent.service` | root | Just-Works pairing agent for Bluetooth speaker mode |
| `voice-bt.service` | `systemd/voice-bt.service` | root | BT control bridge: writes `/tmp/va_bt_status.json`, reads `/tmp/va_bt_cmd` (pairing/status for the touch UI) |

---

## Acoustic echo cancellation (AEC)

`pipewire/60-aec.conf` → `/etc/pipewire/pipewire.conf.d/`. Creates `aec_mic`
(source) + `aec_sink` (sink) from `libpipewire-module-echo-cancel`. LVA is
pointed at both in `~/lva/docker-compose.yml` (not in this repo):
`--audio-input-device "aec_mic"` and `--audio-output-device "pulse/aec_sink"`.

**`aec_sink` must be the default sink** (`wpctl set-default <id>`, WirePlumber
persists it) — the canceller can only subtract what passes through it, and that
is what puts *Bluetooth* music into the reference. Because it is the default,
the module's own playback stream is pinned with `target.object` to the real
ALSA sink, or it would connect to itself and loop.

Verify the chain with `pw-link -l`; it must read
`alsa_input → echo-cancel-capture → aec_mic → linux_voice_assistant` and
`bluez_input/LVA → aec_sink → echo-cancel-playback → alsa_output`.

**Post-processing is all off on purpose** (`aec.args`). The plugin supports
`gain_control`, `noise_suppression`, `voice_detection`, `transient_suppression`,
`high_pass_filter` (`strings libspa-aec-webrtc.so | grep webrtc\.`) and defaults
most ON — telephony tuning, wrong for a wake-word model. With them on, `aec_mic`
measured ~0.5 rms in *every* condition (idle, ambient, music): speech squeaked
through but everything else was gated flat and "Okay Nabu" never landed over
music. Off, `aec_mic` tracks the raw mic (3.5 vs 5.3 rms in a quiet room).

**How to measure** — `audioop` is gone in Python 3.13, so compute RMS by hand:
```bash
timeout 5 pw-record --target aec_mic --rate 16000 --channels 1 --format s16 /tmp/a.wav
timeout 5 pw-record --target alsa_input.platform-soc_sound.stereo-fallback \
                    --rate 16000 --channels 1 --format s16 /tmp/r.wav
python3 -c "import wave,array,math
w=wave.open('/tmp/a.wav');a=array.array('h');a.frombytes(w.readframes(w.getnframes()))
print(math.sqrt(sum(x*x for x in a)/len(a)), max(abs(x) for x in a))"
```
A quiet room reads ~5 rms raw; **300–700 rms means music is playing**, which
invalidated two of our measurements. Don't trust a synthetic test tone either
unless it clearly exceeds that floor.

**Where it stands (2026-08-14):** wake word over BT music works at *reduced*
music volume, not at normal listening volume. Above some SPL the INMP441
saturates inside the enclosure and the echo goes nonlinear — nothing linear can
subtract a clipped signal. Dropping the wake threshold to 0.60
(`number.entree_rpi_satellite_wake_word_1_sensitivity`; LVA overrides the
configured value with the model default 0.850 at every start) did **not** help,
confirming the limit is acoustic, not decision-threshold. The remaining fix is
the enclosure — see the mic-placement note under Known Issues.

---

## Bluetooth speaker mode (A2DP sink)

The Pi doubles as a Bluetooth speaker: a phone connects and plays through the
MAX98357A. Works **fully offline** (no Wi-Fi/HA needed) — for portable/battery
use. Audio path: phone → A2DP → **PipeWire** (already the audio hub; LVA plays
through it too via the PulseAudio socket) → mixed onto the I2S sink → amp. No
device contention because PipeWire mixes; sustained BT audio is no heavier on
the SPI/I2S-DMA balance than radio, which already works.

**Setup (done; pieces tracked in repo):**
- `apt install libspa-0.2-bluetooth` — the PipeWire↔BlueZ SPA plugin. Without it
  PipeWire literally cannot do BT audio (no `spa-0.2/bluez5/`). Pulls in SBC/AAC/
  LDAC/aptX/LC3 codecs.
- `apt install bluez-tools` + `bt-agent.service` — headless Just-Works pairing.
- **`wireplumber/52-bluez-codecs.conf`** → `/etc/wireplumber/wireplumber.conf.d/`.
  Pins the A2DP sink to **aptX**. A modern phone otherwise picks the best codec
  the Pi advertises — the Pixel 7a chose **aptX HD**, ~576 kbit/s (measured
  553 kbit/s of ACL traffic), which the BCM4345 combo radio cannot hold up:
  **periodic dropouts** with *zero* evidence locally — HCI `errors:0`, PipeWire
  xruns 0 over a 60-sample `pw-top` run, load under 20%. The packets simply do
  not all make it over the air, so log-diving is a dead end.

  Measured ladder on this link: **aptX HD 553 kbit/s → dropouts**, **SBC
  341 kbit/s → clean but audibly worse**, **aptX 359 kbit/s → clean, quality
  fine** ← current setting. `sbc` stays in the list as the fallback for phones
  without aptX; SBC-XQ (~452 kbit/s) stays disabled — the bandwidth problem
  again, just smaller. AAC is not an option: the Pi registers no
  `A2DPSink/aac` endpoint.

  Diagnosis order for "BT audio glitches": `wpctl inspect <bluez node>` →
  `api.bluez5.codec`, then bitrate via two `hciconfig -a hci0 | grep 'RX bytes'`
  15 s apart. Changing the file needs `systemctl --user restart wireplumber`
  **and** a phone disconnect/reconnect — A2DP only renegotiates on connect
  (the PipeWire `bluez_input` node only exists while audio actually plays, so
  check the codec with music running, not just connected).

  Level is a *separate* axis from dropouts: BT stream, sink and amp all sit at
  1.00, unlike radio which plays through MASS at a lower volume — so clipping
  on the 3 W MAX98357A reads as crackle, not gaps. Ruled out here by A/B'ing
  the stream at 0.45.
- **`networkmanager/10-wifi-powersave-off.conf`** → `/etc/NetworkManager/conf.d/`.
  WiFi and BT share one radio on the BCM4345, and brcmfmac enables WiFi power
  save by default (`brcmf_cfg80211_set_power_mgmt: power save enabled`); its
  duty cycling steals A2DP airtime. Deployed as a drop-in because the wlan0
  connection is netplan-generated, so `nmcli con modify` gets regenerated away.
  ⚠ Deployed but **not verified** — `iw`/`iwconfig` are not installed on the Pi,
  and the aptX fix landed first, so it has never been shown to matter. It is
  the lever to pull if dropouts return. This Pi is **WiFi-only** (eth0 down):
  run any reactivation detached (`systemd-run`), never straight from the SSH
  session that issues it.
- **`wireplumber/51-headless-bluez.conf`** → `/etc/wireplumber/wireplumber.conf.d/`.
  THE non-obvious fix: WirePlumber's `main` profile keeps `monitor.bluez.seat-monitoring`
  enabled, and this headless session has no logind seat, so the bluez monitor stays
  dormant and no A2DP sink is registered (phones error with a passkey/pairing failure
  or silently no-op). Disabling seat-monitoring fixes it.
- `/etc/bluetooth/main.conf`: `AutoEnable=true` (powers adapter at boot).
- Adapter was soft-`rfkill`'d at boot; cleared via `/sys/class/rfkill/*/soft`
  (no `rfkill` CLI installed). systemd-rfkill persists the unblocked state.
- Paired phone must be **trusted** (`bluetoothctl trust <mac>`) to auto-reconnect.

**Gotchas:**
- Re-pairing a phone that the Pi still has bonded fails with a passkey error
  ("clé d'accès") — key mismatch. Fix: `bluetoothctl remove <mac>` + forget on
  phone, then pair fresh.
- `journalctl --user -u wireplumber` returns nothing over a non-login SSH session;
  read logs via `systemctl --user status wireplumber -n N` instead.
- Discoverability is **not** persistent and off by default (secure at home; only
  needed to pair NEW devices — a trusted phone reconnects without it). The touch
  UI's **Bluetooth tile** (menu → Bluetooth) opens it on demand: "Appairer un
  appareil" makes the Pi discoverable for BT_PAIR_WINDOW (120 s) with a live
  countdown, and shows the connected device. Flow: display writes `/tmp/va_bt_cmd`
  ("pair"/"stop") → `voice-bt.service` runs bluetoothctl + writes
  `/tmp/va_bt_status.json` → display reads it. No bluetoothctl in the display
  process (fork-safe). See `display/bt_bridge.py` + `display/bt_actions.py`.
- **Home now-playing pill:** when BT audio is playing, the ambient home screen
  shows a Bluetooth pill with the track title (tap → Bluetooth screen), exactly
  like the radio pill. Playback status + Title/Artist come from BlueZ AVRCP
  (`org.bluez.MediaPlayer1` via `busctl --json=short`, no PipeWire introspection,
  no extra deps). NB: BT playback does **not** go through the MASS media_player,
  so `sat_playing` is false during BT — the pill is driven purely by the bridge.
- The bridge polls bluetoothctl/busctl at 1 Hz only during a pairing window,
  else every 4 s (idle CPU); the command file and `/tmp/va_state` are read every
  tick (`BT_TICK`, 100 ms) — both are small local file reads.
- **Ducking:** the bridge drops the music while the assistant is active. It
  follows `/tmp/va_state` (written by the LED daemon from LVA's logs — `"wake"`
  lands the instant *Detected wake word* is logged, so the duck is immediate)
  and lowers the **`bluez_input` node only**, never `aec_sink` — ducking
  `aec_sink` would drag the TTS reply down with the music, since both pass
  through it. Restores the *pre-duck* level, so a phone-side volume change
  survives. Notes:
  · The node id is re-resolved on every duck: `bluez_input` only exists while
    audio actually plays, so a cached id is stale after any pause.
  · The bridge runs as root while PipeWire belongs to `dd`, so `pw-dump`/`wpctl`
    are called with `XDG_RUNTIME_DIR=/run/user/1000` (same trick as the LVA
    container's `PULSE_SERVER`).
  · Failsafe: a duck older than `BT_DUCK_MAX_SECONDS` (30 s) is released in case
    LVA dies mid-run and the state file sticks — and it then *latches* until the
    state leaves the duck set, or it would re-duck on the next tick and cycle
    forever. SIGTERM also restores, so `systemctl stop` cannot strand the phone
    at duck level.
  · This helps STT hear the command; it cannot help wake-word detection, which
    happens before there is anything to duck.
  Tunables in `config.py`: `BT_DUCK_LEVEL` (0.20), `BT_DUCK_STATES`,
  `BT_DUCK_MAX_SECONDS`, `BT_TICK`. Test without talking to it:
  `echo -n wake | sudo tee /tmp/va_state`, check `wpctl get-volume <id>`, then
  `echo -n idle`.

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
- **Night dimming** (`daemon.night_scale`) — the backlight is HA's brightness ×
  a time-of-day scale: full by day, **35 % between 22:00 and 07:00**, ramped
  over 30 min at each boundary so it never steps. A touch restores full
  brightness for 25 s then fades back. HA/MQTT brightness stays the reference
  level (a manual change still applies instantly, day or night); brightness 0
  from HA still means off. `apply_display_config` no longer touches brightness —
  the main loop owns the backlight.
- **Touch** — XPT2046 on SPI0/CE1 (`spidev0.1`, 1 MHz), pen IRQ on GPIO22. Taps
  are edge-triggered on release. Calibration is an affine raw→screen map per axis
  (`swap` + `mx,cx,my,cy`) least-squares-fit from 4 corner taps, stored in
  `.touch_calib.json`; (re)generate with `display/calibrate.py`.
- **Design rules learned the hard way** — menu glyphs share one idiom (outline,
  3 px, ~44 px box) or the tile row stops reading as a set; the menu sits on a
  *fresh* background gradient (any partial scrim ghosts the clock between the
  tiles); list rows stay at full ink (dimming the inactive ones reads as
  "disabled"); the voice waveform's glow stays tight, or it looks like RGB
  gaming kit next to the rest.
- **Product-look idiom (2026-09 pass)** — hero clock digits carry a
  white→steel vertical gradient (`T.hero_text`, mask + cached gradient);
  micro-labels are tracked uppercase (`T.text_tracked`); each screen's single
  primary action is a full accent-filled pill (`App._primary_btn`) — accent
  *tints* are for secondary/stateful surfaces only; stations are a 3×2
  logo-tile grid (album-art wall), active tile marked by accent edge + EQ;
  sliders have rounded caps and a ringed knob; back chevron is drawn, not a
  font glyph.
- **Low-contrast panel compensation** — the palette floor stays above ~8/255
  (the panel crushes darker values into one grey), elevation steps are wider
  than a monitor needs, hero/clock text is Roboto **Light**, never Thin
  (antialiasing eats half the luminance of a 1-2 px stroke), and `to_rgb565`
  applies positional Bayer 8×8 dithering (keyed on absolute screen coords so
  dirty-rect blits stay seamless — pass the crop origin) to kill gradient
  banding in 16-bit colour.
- **HA actions** (`ha_actions.py`) — radio plays through the **Music Assistant**
  player `media_player.enceinte_entree` (`media_player.play_media`, 6 stations +
  stop), NOT the raw LVA player: MASS owns the satellite speaker (`active_queue`),
  so a `play_media` on the LVA entity underneath gets clobbered by MASS's queue.
  Volume via `volume_set`; timers via the conversation agent (same path as voice
  timers). `ha_context.py` reads the *current* station from `enceinte_entree`'s
  `media_content_id` (matching the known stream URL) so the screen reflects radio
  changes made by voice or the dashboard too (`App._sync_station`).

### Assist / voice routing (on dd-ha, not the Pi)
- Satellite uses the preferred pipeline → agent `conversation.ollama_3060_12g`
  (gemma4:12b on `dd-room.local:11434`), STT `faster_whisper`, TTS Piper.
- ⚠ **"Terminé" with `success:[]` was not always gemma.** A conversation-trigger
  automation with a bare wildcard (`… {channel}`) was swallowing every "mets …"
  sentence in the house — radio, lights, heating, timers — mapping them to TV
  channel 0 and returning the trigger's default "Terminé". Sentence triggers
  outrank intents, so nothing downstream ever saw those commands. Fixed
  2026-08-14 by enumerating the channel names in
  `automations/automation_tv_salon_chaine_voix.yaml`. **Before blaming the LLM,
  check who actually matched:**
  `python3 ha_ws.py '{"type":"conversation/agent/homeassistant/debug","sentences":["mets RTL"],"language":"fr"}'`
  — `source: trigger` means an automation ate it, `custom` a custom sentence,
  `builtin` HA's own. A bare `{slot}` in a conversation trigger is a wildcard,
  not a placeholder for known values.
- gemma is *also* unreliable at tool-calling (sometimes replies "Terminé"/"c'est
  fait" with `success:[]` — no action) and the Ollama endpoint is intermittently
  unreachable (instant `intent-failed`). Mitigation: **"Prefer handling commands
  locally"** enabled on the Ollama agent → recognized device commands run on HA's
  deterministic engine (independent of dd-room), gemma only for fallback/questions.
- Voice timer phrasing that works: **"lance/démarre un minuteur de N minutes"**,
  cancel with **"annule/arrête/supprime le minuteur"**. "mets un minuteur …" does
  NOT work (no native intent). Radio: `custom_sentences/fr/radio.yaml` maps the
  station phrases to `HassTurnOn` on the `script.radio_*` entities (which each
  delegate to `script.radio_play`, so deferred playback still applies). It
  covers the STT homophones of "mets" — **"mais" / "met" / "mes"** — because
  faster_whisper renders "mets la radio RTL" as *"Mais la radio RTL"*, and
  without a recognised verb the local engine matches nothing. Note "France Info"
  is both a TNT channel and a radio: bare "mets France Info" goes to the TV,
  "mets la radio France Info" to the radio.

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
    ├── bt_actions.py  — read BT status / request pairing (file IPC; fork-safe)
    ├── bt_bridge.py   — voice-bt.service daemon: bluetoothctl ↔ status/cmd files
    ├── app.py         — UI controller + Home/Menu/Radio/Timer/Bluetooth screens + voice overlay
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
- Dev machine syncs via rsync: `rsync -av --exclude __pycache__ src/ dd@pi-satellite:/home/dd/dev/voice-assistant/src/`
  then `ssh dd@pi-satellite "sudo systemctl restart voice-display.service"`
  (`__pycache__` is owned by root from the services — rsync fails without the exclude)
- After changing the boot splash design, regenerate its frame on the Pi:
  `python3 src/display/make_splash.py` (build artefact, not committed)
- Boot ordering and the splash/checklist handoff: `docs/boot-tuning.md`

---

## Do Not

- Do not add cloud API calls — everything must be local
- Do not hard-code IP addresses — use hostnames
- Do not use subprocess.Popen in the display process — fork races with SPI DMA
- Do not use SPI chunks > 64 bytes — triggers BCM2835 DMA, conflicts with I2S PCM DMA
- Do not toggle CS between pixel chunks — resets the ST7796S write-address counter
