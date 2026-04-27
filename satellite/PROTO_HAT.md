# Proto HAT Wiring — Raspberry Pi 4 Voice Assistant

RPi 2/B+/A+ Proto HAT with EEP. All required GPIOs are exposed on this hat.

---

## Power Rails

Use the hat's labeled power/GND rails as a bus.

| Hat Label | Connected To |
|-----------|-------------|
| `+3.3V` | INMP441 VDD, GC9A01 VCC, MAX98357A SD (enable) |
| `+5V` | MAX98357A VIN, WS2812B VDD ⚠ |
| `GND` (either rail) | All module GNDs, INMP441 L/R |

> ⚠ WS2812B at full brightness draws ~720mA. The hat's 5V rail is the RPi's own rail (fused ~2.5A total). Keep LEDs at ≤50% brightness, or power VDD from an external 5V PSU with shared GND.

---

## Shared I2S Bus — use horizontal proto rails

The INMP441 and MAX98357A both need BCLK (GPIO18) and LRCLK (GPIO19).
Use two horizontal rows on the proto area as bus rails:

```
Hat pin #18  ──► [horizontal rail A]  ──► INMP441 SCK
                                      ──► MAX98357A BCLK

Hat pin #19  ──► [horizontal rail B]  ──► INMP441 WS
                                      ──► MAX98357A LRC
```

---

## INMP441 — I2S Microphone

| INMP441 Pin | Hat Label | Notes |
|-------------|-----------|-------|
| VDD | `+3.3V` rail | |
| GND | `GND` rail | |
| SCK | `#18` → rail A | BCLK shared bus |
| WS | `#19` → rail B | LRCLK shared bus |
| SD | `#20` | |
| L/R | `GND` rail | GND = Left channel |

---

## MAX98357A — I2S Amplifier

| MAX98357A Pin | Hat Label | Notes |
|---------------|-----------|-------|
| VIN | `+5V` rail | |
| GND | `GND` rail | |
| BCLK | rail A | Shared with INMP441 |
| LRC | rail B | Shared with INMP441 |
| DIN | `#21` | |
| SD | `+3.3V` rail | Always-on enable |
| GAIN | leave floating | Default 9dB |
| SPK+ / SPK− | Speaker | BTL output, no coupling cap needed |

---

## WS2812B — 12-LED RGB Ring

Solder the 300Ω series resistor on the proto area between `#12` and the DIN wire.

```
Hat #12  ──[300Ω]──► WS2812B DIN
```

| WS2812B Pin | Hat Label | Notes |
|-------------|-----------|-------|
| VDD | `+5V` rail | See current warning above |
| GND | `GND` rail | |
| DIN | `#12` via 300Ω | Resistor soldered on proto area |

---

## GC9A01 — 1.28" Round TFT Display

| GC9A01 Pin | Hat Label | Notes |
|------------|-----------|-------|
| VCC | `+3.3V` rail | |
| GND | `GND` rail | |
| SCL | `CLK` | SPI0 clock |
| SDA | `MOSI` | SPI0 data |
| CS | `CEO` | Manual CS in software (`spi.no_cs = True`) |
| DC | `#24` | Data/Command select |
| RST | `#25` | Hardware reset |
| BLK | `#23` | Backlight |

---

## Decoupling Caps (solder on proto area, as close to module power pins as possible)

| Location | Cap |
|----------|-----|
| INMP441 VDD–GND | 100nF ceramic |
| MAX98357A VIN–GND | 100nF ceramic + 10µF electrolytic |
| GC9A01 VCC–GND | 100nF ceramic |
| WS2812B VDD–GND | 100µF electrolytic |

---

## Unused Hat Pins (available for future use)

`SDA`, `SCL`, `TXD`, `RXD`, `#4`, `#17`, `#27`, `#22`, `MISO`, `CE1`, `#5`, `#6`, `#13`, `#16`

---

## GPIO Usage Summary

| Hat Label | GPIO | Connected To |
|-----------|------|-------------|
| `#18` | GPIO18 | I2S BCLK → INMP441 SCK + MAX98357A BCLK (via rail A) |
| `#19` | GPIO19 | I2S LRCLK → INMP441 WS + MAX98357A LRC (via rail B) |
| `#20` | GPIO20 | I2S RX → INMP441 SD |
| `#21` | GPIO21 | I2S TX → MAX98357A DIN |
| `#12` | GPIO12 | PWM0 → WS2812B DIN (via 300Ω) |
| `MOSI` | GPIO10 | SPI0 MOSI → GC9A01 SDA |
| `CLK` | GPIO11 | SPI0 CLK → GC9A01 SCL |
| `CEO` | GPIO8 | SPI0 CE0 → GC9A01 CS |
| `#23` | GPIO23 | GC9A01 BLK |
| `#24` | GPIO24 | GC9A01 DC |
| `#25` | GPIO25 | GC9A01 RST |
