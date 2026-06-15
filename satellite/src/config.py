# Shared hardware constants and state definitions

# ── GPIO ──────────────────────────────────────────────────────────────
LED_PIN        = 12       # GPIO12 / PWM0
SPI_DC         = 24       # ST7796S Data/Command
SPI_CS         = 8        # ST7796S Chip Select (CE0, manual control)
SPI_RST        = 25       # ST7796S Reset
SPI_BLK        = 23       # ST7796S Backlight
TOUCH_CS       = 7        # ST7796S Touch CS (CE1)
TOUCH_IRQ      = 22       # ST7796S Touch interrupt (active low)

# ── LED ring ──────────────────────────────────────────────────────────
LED_COUNT      = 3
LED_DMA        = 5        # DMA channel 5 (10 caused single-LED issue)
LED_FREQ_HZ    = 800000
LED_INVERT     = False
LED_CHANNEL    = 0
LED_BRIGHTNESS = 40       # 0-255, keep low for 5V ring on 3.3V PWM

# ── Display ───────────────────────────────────────────────────────────
DISPLAY_WIDTH  = 480
DISPLAY_HEIGHT = 320
DISPLAY_CX     = 240
DISPLAY_CY     = 160
DISPLAY_SPI_SPEED = 40_000_000  # 40 MHz — proto hat (soldered) handles it; 307 KB frame needs >25 MHz for 10 FPS

# ── VA states (int, shared between LED and display daemons) ───────────
STATE_IDLE       = 0
STATE_LISTENING  = 1
STATE_PROCESSING = 2
STATE_SPEAKING   = 3
STATE_ERROR      = 4

# ── LED colors per state (R, G, B) — aligned with ACCENT_COLORS ──────
LED_COLORS = {
    "idle":       (0,   0,  30),
    "wake":       (0, 100, 255),  # same hue as listening
    "listening":  (0, 100, 255),
    "processing": (160,  0, 220),
    "speaking":   (0, 200,  60),
    "error":      (255,  40,   0),
}

# ── Display accent colors per state (R, G, B) ────────────────────────
ACCENT_COLORS = {
    STATE_IDLE:       (0,  40,  80),
    STATE_LISTENING:  (0, 100, 255),
    STATE_PROCESSING: (160,  0, 220),
    STATE_SPEAKING:   (0, 200,  60),
    STATE_ERROR:      (255, 40,   0),
}

# ── MQTT ──────────────────────────────────────────────────────────────
MQTT_BROKER       = "dd-ha"
MQTT_PORT         = 1883
MQTT_TOPIC_PREFIX = "pi-satellite/display"
# Credentials file: one line "username:password" (chmod 600)
MQTT_CREDS_FILE   = "/home/dd/dev/voice-assistant/.mqtt_creds"

# ── Display config IPC ────────────────────────────────────────────────
DISPLAY_CONFIG_FILE = "/tmp/display_config.json"

# ── Bluetooth speaker IPC (display ↔ bt_bridge service) ───────────────
# The display process must never fork, so all bluetoothctl calls live in the
# bt_bridge service; the two sides talk through these files only.
BT_STATUS_FILE = "/tmp/va_bt_status.json"   # bridge writes; display reads
BT_CMD_FILE    = "/tmp/va_bt_cmd"           # display writes; bridge consumes
BT_PAIR_WINDOW = 120                        # seconds discoverable after a pair request

# ── Log → state mapping (shared parse logic) ─────────────────────────
# Speaking window: "Playing TTS response" fires when mpv starts the URL;
# "TTS response finished" fires when playback actually ends — this matches
# the real audio duration, unlike VOICE_ASSISTANT_TTS_START/RUN_END which
# fire before playback completes.
LOG_STATE_MAP = {
    "Detected wake word":        "wake",
    "VOICE_ASSISTANT_STT_START":   "listening",
    "VOICE_ASSISTANT_STT_VAD_END": "processing",
    "Playing TTS response":      "speaking",
    "TTS response finished":     "idle",
    "VOICE_ASSISTANT_RUN_END":   "idle",    # fallback (e.g. no TTS)
    "VOICE_ASSISTANT_ERROR":     "error",
    "Connected to Home Assistant": "idle",
}

# ── State name → int (for display) ───────────────────────────────────
STATE_INT = {
    "idle":       STATE_IDLE,
    "wake":       STATE_IDLE,       # wake flashes then returns to idle display
    "listening":  STATE_LISTENING,
    "processing": STATE_PROCESSING,
    "speaking":   STATE_SPEAKING,
    "error":      STATE_ERROR,
}
