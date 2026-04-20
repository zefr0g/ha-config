# Hardware Wiring — Raspberry Pi 4 Voice Assistant

## Components

| # | Module | Interface | Voltage |
|---|--------|-----------|---------|
| 1 | INMP441 I2S Microphone | I2S | 3.3V |
| 2 | MAX98357A I2S Amplifier + 3W 4Ω speaker | I2S | 5V |
| 3 | WS2812B 12-LED RGB Ring | PWM (GPIO 12) | 5V |
| 4 | GC9A01 1.28" Round TFT 240×240 | SPI | 3.3V |

---

## Raspberry Pi 4 — 40-Pin GPIO Diagram

```
                    ┌─────────────────┐
              3.3V  │  1 ●  ● 2  │ 5V
  INMP441_VDD──────┘            └──────── MAX98357A_VIN
                                          WS2812B_VDD (shared, careful on current)
         (SDA1) GPIO2  │  3 ●  ● 4  │ 5V
         (SCL1) GPIO3  │  5 ●  ● 6  │ GND ──── INMP441_GND
                GPIO4  │  7 ●  ● 8  │ GPIO14
                  GND  │  9 ●  ● 10 │ GPIO15
                GPIO17  │ 11 ●  ● 12 │ GPIO18 (PCM_CLK) ──── INMP441_SCK
                                                          ──── MAX98357A_BCLK
                GPIO27  │ 13 ●  ● 14 │ GND ──── WS2812B_GND
                                               MAX98357A_GND
                GPIO22  │ 15 ●  ● 16 │ GPIO23 ──── GC9A01_BLK
              3.3V  │ 17 ●  ● 18 │ GPIO24 ──── GC9A01_DC
  GC9A01_VCC──────┘
    (SPI0_MOSI) GPIO10  │ 19 ●  ● 20 │ GND ──── GC9A01_GND
  GC9A01_SDA ─────────┘
    (SPI0_MISO) GPIO9  │ 21 ●  ● 22 │ GPIO25 ──── GC9A01_RST
    (SPI0_CLK) GPIO11  │ 23 ●  ● 24 │ GPIO8  (SPI0_CE0) ──── GC9A01_CS
  GC9A01_SCL ─────────┘
                  GND  │ 25 ●  ● 26 │ GPIO7
                GPIO0  │ 27 ●  ● 28 │ GPIO1
                GPIO5  │ 29 ●  ● 30 │ GND
                GPIO6  │ 31 ●  ● 32 │ GPIO12 (PWM0) ──── WS2812B_DIN
                                                     (via 300Ω series resistor)
  (PWM1) GPIO13  │ 33 ●  ● 34 │ GND
  (PCM_FS) GPIO19  │ 35 ●  ● 36 │ GPIO16
  INMP441_WS ──────┘
  MAX98357A_LRC ───┘
  (PCM_DIN) GPIO20  │ 37 ●  ● 38 │ GPIO20 (PCM_DIN) ──── INMP441_SD
  (PCM_DOUT) GPIO21  │ 39 ●  ● 40 │ GPIO21 (PCM_DOUT)
                  GND  │              └──── MAX98357A_DIN
                       └─────────────────┘
```

> Note: Pins 37–40 label correction — physical layout below is authoritative.

---

## Clean Physical Pin Reference

```
Physical  GPIO      Signal              → Component
────────  ────────  ──────────────────  ────────────────────────
Pin  1    3.3V      Power               INMP441 VDD
                                        GC9A01 VCC
Pin  2    5V        Power               MAX98357A VIN
Pin  4    5V        Power               WS2812B VDD  ⚠ see note
Pin  6    GND       Ground              INMP441 GND
Pin  9    GND       Ground              MAX98357A GND
Pin 12    GPIO18    I2S BCLK            INMP441 SCK  +  MAX98357A BCLK
Pin 14    GND       Ground              WS2812B GND
Pin 16    GPIO23    GC9A01 Backlight    GC9A01 BLK
Pin 17    3.3V      Power               GC9A01 VCC  (shared with Pin 1)
Pin 18    GPIO24    GC9A01 DC           GC9A01 DC
Pin 19    GPIO10    SPI0 MOSI           GC9A01 SDA
Pin 20    GND       Ground              GC9A01 GND
Pin 22    GPIO25    GC9A01 Reset        GC9A01 RST
Pin 23    GPIO11    SPI0 CLK            GC9A01 SCL
Pin 24    GPIO8     SPI0 CE0            GC9A01 CS
Pin 32    GPIO12    PWM0 (WS2812B)      WS2812B DIN  (via 300Ω)
Pin 35    GPIO19    I2S LRCLK           INMP441 WS   +  MAX98357A LRC
Pin 38    GPIO20    I2S RX              INMP441 SD
Pin 40    GPIO21    I2S TX              MAX98357A DIN
```

---

## Per-Component Wiring

### 1. INMP441 — I2S Microphone (6 pins)

```
INMP441 Pin │ Connects to          │ Notes
────────────┼──────────────────────┼──────────────────────────
VDD         │ RPi Pin 1  (3.3V)   │
GND         │ RPi Pin 6  (GND)    │
SCK         │ RPi Pin 12 (GPIO18) │ I2S Bit Clock
WS          │ RPi Pin 35 (GPIO19) │ I2S Word Select / LRCLK
SD          │ RPi Pin 38 (GPIO20) │ I2S Serial Data out (mic)
L/R         │ GND                  │ GND = Left ch, 3.3V = Right
```

### 2. MAX98357A — I2S Amplifier (7 pins)

```
MAX98357A Pin │ Connects to          │ Notes
──────────────┼──────────────────────┼──────────────────────────
VIN           │ RPi Pin 2  (5V)     │ Higher voltage = more headroom
GND           │ RPi Pin 9  (GND)    │
BCLK          │ RPi Pin 12 (GPIO18) │ Shared with INMP441 SCK
LRC           │ RPi Pin 35 (GPIO19) │ Shared with INMP441 WS
DIN           │ RPi Pin 40 (GPIO21) │ I2S data to amp
SD            │ 3.3V (or float)     │ HIGH = enabled, LOW = shutdown
GAIN          │ leave floating       │ Default 9dB (float=9, GND=12, 3V3=15)
SPK+          │ Speaker +           │ BTL output — no coupling cap needed
SPK−          │ Speaker −           │
```

### 3. WS2812B — 12-LED RGB Ring (3 signal pins + power)

```
WS2812B Pin │ Connects to                    │ Notes
────────────┼────────────────────────────────┼──────────────────────────────────
VDD         │ RPi Pin 4  (5V)               │ ⚠ At full white: ~720mA total
GND         │ RPi Pin 14 (GND)              │
DIN         │ RPi Pin 32 (GPIO12 / PWM0)    │ Via 300–470Ω series resistor
            │                                │ Use DMA channel 5 (not 10) with rpi_ws281x
            │                                │ ⚠ 3.3V signal — add level shifter
            │                                │   (74AHCT125) for production use
```

**Current budget note:** 12 LEDs × 60mA (max per LED) = 720mA.
The RPi 5V rail is fused at ~2.5A total (shared with the board itself).
For full-brightness use, power the ring from a dedicated 5V supply and tie GNDs.

**Level shifter (optional but recommended):**
```
GPIO12 ──► [74AHCT125 OE=GND] ──► WS2812B DIN
            VCC = 5V, GND = GND
```

### 4. GC9A01 — 1.28" Round TFT Display (7–8 pins)

```
GC9A01 Pin │ Connects to          │ Notes
───────────┼──────────────────────┼──────────────────────────
VCC        │ RPi Pin 1  (3.3V)   │
GND        │ RPi Pin 20 (GND)    │
SCL        │ RPi Pin 23 (GPIO11) │ SPI0 Clock
SDA        │ RPi Pin 19 (GPIO10) │ SPI0 MOSI
CS         │ RPi Pin 24 (GPIO8)  │ SPI0 Chip Select (CE0)
DC         │ RPi Pin 18 (GPIO24) │ Data / Command select
RST        │ RPi Pin 22 (GPIO25) │ Hardware reset
BLK        │ RPi Pin 16 (GPIO23) │ Backlight PWM (or tie to 3.3V always-on)
```

---

## Breadboard Wiring Diagram (ASCII top view)

```
 ┌──────────────────────────────────────────────────────────────────┐
 │                    BREADBOARD LAYOUT                            │
 │                                                                  │
 │  [RPi 4]  40-pin header ──────────────────────────────────────  │
 │                                                                  │
 │  ┌─────────┐     ┌────────────┐     ┌──────────┐               │
 │  │ INMP441 │     │  MAX98357A │     │ GC9A01   │               │
 │  │   MIC   │     │    AMP     │     │  DISPLAY │               │
 │  │         │     │            │     │          │               │
 │  │ VDD─3V3 │     │ VIN─5V     │     │ VCC─3V3  │               │
 │  │ GND─GND │     │ GND─GND    │     │ GND─GND  │               │
 │  │ SCK─G18 │──┐  │ BCLK─G18  │──┘  │ SCL─G11  │               │
 │  │ WS──G19 │──┼──│ LRC──G19  │     │ SDA─G10  │               │
 │  │ SD──G20 │  │  │ DIN──G21  │     │ CS──G8   │               │
 │  │ L/R─GND │  │  │ SD───3V3  │     │ DC──G24  │               │
 │  └─────────┘  │  │ SPK+──────┼──►  │ RST─G25  │               │
 │               │  │ SPK−──────┼──►  │ BLK─G23  │               │
 │     I2S bus ──┘  └────────────┘  ──└──────────┘               │
 │  (BCLK + LRCLK                  SPI0 bus                       │
 │   shared between                (SCL, SDA, CS shared bus)      │
 │   mic and amp)                                                  │
 │                                                                  │
 │  ┌──────────────────────┐                                       │
 │  │  WS2812B 12-LED RING │                                       │
 │  │                      │                                       │
 │  │ VDD ─── 5V           │   ← Ideally from external 5V PSU     │
 │  │ GND ─── GND          │     with shared GND to RPi           │
 │  │ DIN ─[300Ω]─ G12     │   ← Series resistor near DIN pin     │
 │  └──────────────────────┘                                       │
 │                                                                  │
 │  SPEAKER:  MAX98357A SPK+ / SPK−  ──►  3W 4Ω speaker           │
 │            (BTL bridged output — no coupling capacitor needed)  │
 └──────────────────────────────────────────────────────────────────┘
```

---

## Decoupling Capacitors (strongly recommended)

Place as close to each module's power pins as possible:

| Location | Cap |
|----------|-----|
| 3.3V rail (near RPi header) | 10µF electrolytic |
| 5V rail (near RPi header) | 100µF electrolytic |
| INMP441 VDD–GND | 100nF ceramic |
| MAX98357A VIN–GND | 100nF ceramic + 10µF electrolytic |
| GC9A01 VCC–GND | 100nF ceramic |
| WS2812B VDD–GND | 100µF electrolytic |

---

## `/boot/firmware/config.txt` Entries

```ini
# ── Audio ──────────────────────────────────────────────
# I2S bus enable
dtparam=i2s=on

# MAX98357A DAC (I2S output)
dtoverlay=hifiberry-dac

# INMP441 requires manual ALSA config (see docs/alsa.md)

# ── SPI (GC9A01 display) ───────────────────────────────
dtparam=spi=on

# ── PWM (WS2812B via rpi_ws281x) ──────────────────────
# No overlay needed; rpi_ws281x takes PWM0 (GPIO12) directly
# Make sure audio does not use PWM mode (use I2S instead — already done above)
```

---

## GPIO Summary Table

| GPIO | Pin | Alt Function | Connected To |
|------|-----|-------------|--------------|
| GPIO8 | 24 | SPI0_CE0 | GC9A01 CS |
| GPIO10 | 19 | SPI0_MOSI | GC9A01 SDA |
| GPIO11 | 23 | SPI0_CLK | GC9A01 SCL |
| GPIO12 | 32 | PWM0 | WS2812B DIN |
| GPIO18 | 12 | PCM_CLK | INMP441 SCK + MAX98357A BCLK |
| GPIO19 | 35 | PCM_FS | INMP441 WS + MAX98357A LRC |
| GPIO20 | 38 | PCM_DIN | INMP441 SD |
| GPIO21 | 40 | PCM_DOUT | MAX98357A DIN |
| GPIO23 | 16 | — | GC9A01 BLK |
| GPIO24 | 18 | — | GC9A01 DC |
| GPIO25 | 22 | — | GC9A01 RST |
