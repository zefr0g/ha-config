#!/usr/bin/env python3
"""
Headless UI preview — renders each screen to a PNG without touching the panel
or GPIO. Used to iterate on the visual design (scp the PNGs back and look).

    python3 src/display/shot.py [out_dir]    # default /tmp/shots
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import (STATE_IDLE, STATE_LISTENING, STATE_SPEAKING)
from display.app import App

NOW = datetime(2026, 6, 13, 14, 32, 8)
CTX = {
    "media": None,
    "timers": [],
    "volume_pct": 35,
    "weather": {"temp": 19, "condition": "partlycloudy"},
    "wifi": {"connected": True, "quality": 82},
}


def scene(name, configure, state=STATE_IDLE, ctx=None):
    app = App()
    configure(app)
    img = app.render(state, NOW, ctx or CTX)
    return name, img


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/shots"
    os.makedirs(out, exist_ok=True)

    scenes = [
        scene("01_home_idle", lambda a: None),
        scene("02_home_speaking", lambda a: None, state=STATE_SPEAKING),
        scene("03_menu", lambda a: setattr(a, "menu_open", True)),
        scene("04_radio", lambda a: (setattr(a, "screen", "radio"),
                                     setattr(a, "active_station", "rtl"))),
        scene("05_timer", lambda a: setattr(a, "screen", "timer"),
              ctx={**CTX, "timers": [{"name": "minuteur", "remaining_s": 228}]}),
        scene("06_timer_empty", lambda a: setattr(a, "screen", "timer")),
        scene("07_home_listening", lambda a: None, state=STATE_LISTENING),
        scene("08_radio_toast", lambda a: (setattr(a, "screen", "radio"),
              a._toast_msg("Lecture · France Inter", 99)),
              ctx={**CTX, "media": {"title": "Radio France Inter", "artist": ""}}),
        scene("09_timer_ring", lambda a: setattr(a, "screen", "timer"),
              ctx={**CTX, "timers": [{"name": "minuteur", "remaining_s": 0,
                                      "ringing": True}]}),
        scene("10_home_radio", lambda a: setattr(a, "active_station", "rtl"),
              ctx={**CTX, "sat_playing": True}),
        scene("11_home_radio_timer", lambda a: setattr(a, "active_station", "france_inter"),
              ctx={**CTX, "sat_playing": True,
                   "timers": [{"name": "minuteur", "remaining_s": 312}]}),
        scene("12_timer_custom", lambda a: (setattr(a, "screen", "timer"),
              setattr(a, "timer_custom", True), setattr(a, "custom_min", 25))),
        scene("13_menu_poweroff", lambda a: setattr(a, "menu_open", True)),
        scene("14_confirm_off", lambda a: (setattr(a, "menu_open", True),
              setattr(a, "menu_confirm_off", True))),
        scene("15_shutdown", lambda a: setattr(a, "screen", "shutdown")),
        scene("16_home_ring", lambda a: None, ctx={**CTX, "timer_ringing": True}),
        scene("17_error_toast", lambda a: (setattr(a, "screen", "radio"),
              a._toast_msg("Lecture impossible", 99, error=True))),
        scene("18_home_wifi_down", lambda a: None,
              ctx={**CTX, "wifi": {"connected": False, "quality": 0}}),
    ]
    for name, img in scenes:
        path = os.path.join(out, f"{name}.png")
        img.save(path)
        print(path)


if __name__ == "__main__":
    main()
