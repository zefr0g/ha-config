#!/usr/bin/env python3
"""LED ring daemon — follows LVA docker logs and drives ring animations."""

import signal
import sys
import time

import docker

sys.path.insert(0, "/home/dd/dev/voice-assistant/src")

from config import LOG_STATE_MAP
from leds.ring import LEDRing
from leds.animations import AnimationController


def parse_log_line(line):
    for keyword, state in LOG_STATE_MAP.items():
        if keyword in line:
            return state
    return None


STATE_FILE = "/tmp/va_state"
RING_FILE = "/tmp/va_timer_ring"   # "1" while a voice timer is ringing


def write_state(state_str):
    """Write the current VA state to a shared file for the display daemon."""
    try:
        with open(STATE_FILE, "w") as f:
            f.write(state_str)
    except Exception:
        pass


def write_ring(active):
    """Surface the timer-ring state for the display daemon.

    HA drops finished timers from its 'timer status' intent the moment they
    fire, so the display can't see the ring via HA — but LVA logs it, and we're
    already tailing those logs here."""
    try:
        with open(RING_FILE, "w") as f:
            f.write("1" if active else "0")
    except Exception:
        pass


def follow_docker_logs(controller):
    """Stream LVA logs via Docker SDK (no subprocess fork — safe alongside SPI)."""
    client = docker.from_env()
    print("[LED] Following docker logs for container 'lva'...")
    tts_playing = False
    while True:
        try:
            container = client.containers.get("lva")
            for chunk in container.logs(stream=True, follow=True, tail=0):
                line = chunk.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                # Timer ring start/stop (independent of the LED state machine).
                if "VOICE_ASSISTANT_TIMER_FINISHED" in line:
                    write_ring(True)
                elif "finished sound" in line:   # "Stopping timer finished sound"
                    write_ring(False)
                state = parse_log_line(line)
                if not state:
                    continue
                # Mirror ESPHome's "wait_until: not voice_assistant.is_running":
                # VOICE_ASSISTANT_RUN_END fires before TTS playback ends.
                # Suppress the idle transition while TTS is in flight; only
                # "TTS response finished" (which fires after mpv completes) ends it.
                if state == "speaking":
                    tts_playing = True
                elif state == "idle" and "VOICE_ASSISTANT_RUN_END" in line and tts_playing:
                    continue  # audio still playing — wait for "TTS response finished"
                elif state == "idle":
                    tts_playing = False
                print(f"[LED] {state} ← {line[:80]}")
                controller.set_state(state)
                write_state(state)
        except Exception as e:
            print(f"[LED] Docker log error: {e}")
        tts_playing = False
        write_ring(False)   # log stream broke (LVA restart) — don't leave it stuck
        print("[LED] Retrying in 5s...")
        time.sleep(5)


def main():
    ring = LEDRing()
    controller = AnimationController(ring)

    def cleanup(sig=None, frame=None):
        print("\n[LED] Shutting down...")
        controller.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print("[LED] Starting — idle state")
    controller.set_state("idle")
    write_ring(False)
    follow_docker_logs(controller)


if __name__ == "__main__":
    main()
