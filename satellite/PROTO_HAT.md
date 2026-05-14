# Proto HAT Wiring — Raspberry Pi 4 Voice Assistant

RPi 2/B+/A+ Proto HAT with EEP. All required GPIOs are exposed on this hat.

---

## Power Rails

Use the hat's labeled power/GND rails as a bus.

| Hat Label | Connected To |
|-----------|-------------|
| `+3.3V` | INMP441 VDD, ST7796S VCC, MAX98357A SD (enable) |
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

## Shared SPI Bus — use horizontal proto rails

The ST7796S display and touch controller share SPI0 (CLK, MOSI, MISO).
Use three horizontal rows on the proto area as bus rails:

```
Hat CLK   ──► [horizontal rail C]  ──► ST7796S SCK
                                   ──► ST7796S T_CLK

Hat MOSI  ──► [horizontal rail D]  ──► ST7796S SDI
                                   ──► ST7796S T_DIN

Hat MISO  ──► [horizontal rail E]  ──► ST7796S SOOK
                                   ──► ST7796S T_DO
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

## WS2812B — LED Ring

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

## ST7796S — 4.0" TFT Display (480×320)

| ST7796S Pin | Hat Label | Notes |
|-------------|-----------|-------|
| VCC | `+3.3V` rail | |
| GND | `GND` rail | |
| CS | `CEO` | SPI0 CE0 — manual CS in software |
| RESET | `#25` | Hardware reset |
| DC/RS | `#24` | Data/Command select |
| SDI (MOSI) | rail D → `MOSI` | SPI0 MOSI shared bus |
| SCK | rail C → `CLK` | SPI0 CLK shared bus |
| LED | `#23` | Backlight (GPIO-controlled) |
| SOOK (MISO) | rail E → `MISO` | SPI0 MISO shared bus |

## ST7796S Touch Controller

| ST7796S Pin | Hat Label | Notes |
|-------------|-----------|-------|
| T_CLK | rail C → `CLK` | SPI0 CLK shared bus |
| T_DIN | rail D → `MOSI` | SPI0 MOSI shared bus |
| T_DO | rail E → `MISO` | SPI0 MISO shared bus |
| T_CS | `CE1` | SPI0 CE1 — separate CS from display |
| T_IRQ | `#22` | Touch interrupt (active low) |

---

## Decoupling Caps (solder on proto area, as close to module power pins as possible)

| Location | Cap |
|----------|-----|
| INMP441 VDD–GND | 100nF ceramic |
| MAX98357A VIN–GND | 100nF ceramic + 10µF electrolytic |
| ST7796S VCC–GND | 100nF ceramic |
| WS2812B VDD–GND | 100µF electrolytic |

---

## GPIO Usage Summary

| Hat Label | GPIO | Connected To |
|-----------|------|-------------|
| `#18` | GPIO18 | I2S BCLK → INMP441 SCK + MAX98357A BCLK (via rail A) |
| `#19` | GPIO19 | I2S LRCLK → INMP441 WS + MAX98357A LRC (via rail B) |
| `#20` | GPIO20 | I2S RX → INMP441 SD |
| `#21` | GPIO21 | I2S TX → MAX98357A DIN |
| `#12` | GPIO12 | PWM0 → WS2812B DIN (via 300Ω) |
| `MOSI` | GPIO10 | SPI0 MOSI → ST7796S SDI + T_DIN (via rail D) |
| `CLK` | GPIO11 | SPI0 CLK → ST7796S SCK + T_CLK (via rail C) |
| `MISO` | GPIO9 | SPI0 MISO → ST7796S SOOK + T_DO (via rail E) |
| `CEO` | GPIO8 | SPI0 CE0 → ST7796S CS |
| `CE1` | GPIO7 | SPI0 CE1 → ST7796S T_CS |
| `#22` | GPIO22 | ST7796S T_IRQ (touch interrupt) |
| `#23` | GPIO23 | ST7796S LED (backlight) |
| `#24` | GPIO24 | ST7796S DC/RS |
| `#25` | GPIO25 | ST7796S RESET |

## Unused Hat Pins

`SDA`, `SCL`, `TXD`, `RXD`, `#4`, `#17`, `#27`, `#5`, `#6`, `#13`, `#16`
