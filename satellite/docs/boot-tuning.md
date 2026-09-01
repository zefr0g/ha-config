# Boot tuning (pi-satellite)

Boot went from **37.3s → ~21s** (userspace 33.1s → ~17s), and the panel now
lights at **7.3s instead of ~32s**. Run-to-run variance on this SD card is a
couple of seconds (NetworkManager and containerd both swing by ~2s), so treat
single measurements with suspicion — one early run came in at 17.2s total and
never reproduced.

Host-level state on the Pi is not in this repo's deploy path — reapply it after
a reflash (see below).

## What is on screen, when

| Uptime | What |
|---|---|
| 7.3s | Boot splash — logo, pushed as a pre-rendered RGB565 frame (`voice-splash.service`) |
| 15.0s | Live boot checklist — système / réseau / docker / assistant vocal / HA, with the time each step took |
| ~25s | Normal UI, once the voice stack answers |

Two processes, one panel. `splash.py` imports nothing but the SPI/GPIO driver,
so it paints 8s before the display daemon can (numpy + Pillow + font loading
costs ~10s from a cold page cache while the rest of boot competes for the SD
card). It leaves `/run/voice-display-panel-ready`; the daemon sees that marker
and attaches with `ST7796S(init_panel=False)` instead of resetting the panel,
which would blank the splash and flash the screen black mid-boot.

The splash frame is a **build artefact**, not committed. Regenerate it after
changing the design:

```bash
python3 src/display/make_splash.py    # → assets/boot_splash.rgb565 (307200 B)
```

### Why not earlier than 7.3s?

The floor is systemd itself, not the panel:

| | |
|---|---|
| 0 → 2.6s | kernel, before `/init` |
| 2.6 → 3.3s | initramfs mounts root |
| 3.3 → 4.0s | switch_root, PID 1 starts |
| 4.0 → 6.5s | systemd loads units and runs generators (~450ms of that is generators) |
| 6.5 → 7.3s | `splash.py`: Python start, panel init (~280ms of it mandatory ST7796S sleeps), 300KB SPI push |

`voice-splash.service` is already as unconstrained as a unit can be
(`DefaultDependencies=no`, `After=-.mount`), and the SPI modules are bound in
the initramfs (`/etc/initramfs-tools/modules`) so `/dev/spidev0.0` exists before
systemd starts. Going below ~7s means not using systemd at all: a static binary
run from the initramfs could paint at ~3.5s, and a kernel-side DRM panel driver
(`panel-mipi-dbi-spi` overlay + `CONFIG_LOGO`) at ~2s — the latter would take
the SPI bus away from the userspace driver, so it is not a drop-in.

## Where the time went

The original critical chain was strictly serial:

```
cloud-init (4.5s) → NetworkManager (7.4s) → NM-wait-online (6.0s)
                  → docker (7.5s) → lva → voice-leds → multi-user
```

Every voice service — and the display, which needs none of it — sat behind the
wifi association. The fixes are all about *ordering*, not about making any single
service faster; NetworkManager is still the longest unit (~9s, most of it
NetworkManager shelling out to `netplan generate` twice), it just no longer
blocks anything that matters.

## Changes applied

| Change | Why | Saves |
|---|---|---|
| `touch /etc/cloud/cloud-init.disabled` | Box is provisioned; NM owns the wifi config | ~4.5s, serialized before sysinit |
| `systemctl mask ModemManager e2scrub_reap` | No cellular modem, no LVM | ~5.5s (parallel) |
| `systemctl disable NetworkManager-wait-online` | Its only consumers (dockerd, LVA's ESPHome client, the MQTT bridge) all retry their own connections | ~6s on the chain |
| Unit overrides on `docker`, `containerd`: `network.target`/`network-online.target` dropped from `After=` | The one container is host-networked with no published ports, so dockerd has nothing to bind | ~7s |
| Unit override on `systemd-user-sessions`: `network.target` dropped from `After=` | Legacy NIS/LDAP ordering; `nss-user-lookup.target` already covers it. It was gating `user@1000` → PipeWire → `lva` | ~10s |
| `voice-display.service`: no longer `After=docker.service lva.service` | Panel only reads `/tmp/va_state` and polls HA; both degrade gracefully | display up ~17s earlier |
| `voice-splash.service` added (`DefaultDependencies=no`) | Pre-rendered logo frame with no numpy/Pillow in the path | something on screen at 7.3s |
| SPI modules in `/etc/modules-load.d` and the initramfs | `/dev/spidev0.0` is a module-bound node, not devtmpfs — udev only created it at ~7.5s | prerequisite for the splash |
| `lva.service`: `ExecStartPre` waits for `/run/user/1000/pulse/native` | `user@1000` being "started" ≠ PipeWire socket published. The old network delay masked this race; without it the container could come up before its audio devices | correctness |
| `apt-daily{,-upgrade}.timer` drop-in `Persistent=false` | Missed cycles fired during boot and thrashed the SD card | ~4s |
| `DefaultTimeoutStopSec=15s` + persistent journal | A stuck unit was holding shutdown long enough to need a power cycle; the journal was volatile so it left no trace | shutdown |

### Caveat: the three vendor unit overrides

`docker.service`, `containerd.service` and `systemd-user-sessions.service` are
**full copies** in `/etc/systemd/system/`, each with a `# LOCAL OVERRIDE` header.
Drop-in dependency resets (`After=` on its own line) are silently ignored on this
systemd build (257), so a copy was the only thing that worked. Package upgrades
to docker/containerd/systemd will not reach these copies — re-sync them from
`/usr/lib/systemd/system/` after a major upgrade, or delete them to fall back to
stock (boot returns to ~30s, nothing breaks).

## Reapplying after a reflash

```bash
sudo touch /etc/cloud/cloud-init.disabled
sudo systemctl mask ModemManager.service e2scrub_reap.service
sudo systemctl disable NetworkManager-wait-online.service
for u in docker containerd systemd-user-sessions; do
  sudo cp /usr/lib/systemd/system/$u.service /etc/systemd/system/
done
sudo sed -i -E 's/^After=.*/After=local-fs.target dbus.service/' /etc/systemd/system/containerd.service
sudo sed -i -E 's/^After=.*/After=docker.socket firewalld.service containerd.service time-set.target/; s/^Wants=.*/Wants=containerd.service/' /etc/systemd/system/docker.service
sudo sed -i -E 's/^After=.*/After=remote-fs.target nss-user-lookup.target home.mount/' /etc/systemd/system/systemd-user-sessions.service
sudo systemctl daemon-reload
printf 'spi_bcm2835\nspidev\n' | sudo tee /etc/modules-load.d/spi-display.conf
printf '\nspi_bcm2835\nspidev\n' | sudo tee -a /etc/initramfs-tools/modules
sudo cp -a /boot/firmware/initramfs8 /boot/firmware/initramfs8.bak   # safety net
sudo update-initramfs -u
python3 /home/dd/dev/voice-assistant/src/display/make_splash.py
sudo systemctl enable voice-splash.service
```

Verify with `systemd-analyze critical-chain` and `systemctl --failed`.

## What is left

`NetworkManager.service` (~9-11s) is now the whole chain. Roughly 6s of it is the
netplan settings backend (`netplan generate` runs twice at startup, with a
permissions warning on `/lib/netplan/00-network-manager-all.yaml`); the wifi
association and DHCP themselves take under 500ms. Moving the connection off the
netplan backend onto a plain NM keyfile would likely recover most of it, but it
touches the config path that keeps this headless box reachable, so it was left
alone.
