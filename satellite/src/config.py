# Shared hardware constants and state definitions

# ── GPIO ──────────────────────────────────────────────────────────────
LED_PIN        = 12       # GPIO12 / PWM0
SPI_DC         = 24       # GC9A01 Data/Command
SPI_CS         = 8        # GC9A01 Chip Select (CE0, manual control)
SPI_RST        = 25       # GC9A01 Reset
SPI_BLK        = 23       # GC9A01 Backlight

# ── LED ring ──────────────────────────────────────────────────────────
LED_COUNT      = 3
LED_DMA        = 5        # DMA channel 5 (10 caused single-LED issue)
LED_FREQ_HZ    = 800000
LED_INVERT     = False
LED_CHANNEL    = 0
LED_BRIGHTNESS = 40       # 0-255, keep low for 5V ring on 3.3V PWM

# ── Display ───────────────────────────────────────────────────────────
DISPLAY_WIDTH  = 240
DISPLAY_HEIGHT = 240
DISPLAY_CX     = 120
DISPLAY_CY     = 120
DISPLAY_SPI_SPEED = 20_000_000  # 20 MHz, reliable on breadboard

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
