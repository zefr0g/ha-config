# 01 — Current inventory (ground truth)

Inspected live on `root@prox` 2026-06-30. Host: **HP MicroServer Gen8**,
Proxmox VE **9.1.7**, kernel 6.17, **16 GB RAM** (oversubscribed — see below).

## Guests

| ID | Name | Type | RAM | Role | GPU | Bulk storage / extras |
|---|---|---|---|---|---|---|
| 102 | dd-nas | VM | 2 G | NAS | — | `scsi1=/dev/md0` passthrough → **2 TB RAID1** |
| 103 | dd-haos | VM | 4 G | Home Assistant (`dd-ha`) | — | 32 G OS disk; **USB**: `usb1=0bda:2838` (RTL-SDR), `usb2=0b05:190e` (ASUS) |
| 105 | dd-pihole | LXC | 0.5 G | **Pi-hole DNS @ 192.168.x.x** (the `.home` resolver) | — | 4 G OS disk |
| 106 | dd-frigate | LXC | 6 G | Frigate NVR | GTX 1650 (bind) | 25 G OS + `mp0=/mnt/frigate-storage` (**4 TB, 100 % full**) |
| 107 | dd-tts | LXC | 6 G | STT/TTS | GTX 1650 (bind) | 25 G OS disk |

**RAM oversubscription:** 4 + 6 + 6 + 2 + 0.5 = **18.5 G committed on 16 G physical**
→ box is swapping (~3.3 G in swap). The new server's 32 GB removes this entirely.

**GPU:** single **GTX 1650 4 GB** (TU117), shared by **dd-frigate AND dd-tts** via
LXC `/dev/nvidia*` bind-mounts (NOT VFIO/PCIe passthrough). Relevant `106.conf` /
`107.conf` lines:

```
lxc.cgroup2.devices.allow: c 195:* rwm   # nvidia
lxc.cgroup2.devices.allow: c 508:* rwm
lxc.cgroup2.devices.allow: c 511:* rwm
lxc.mount.entry: /dev/nvidia0 dev/nvidia0 none bind,optional,create=file
lxc.mount.entry: /dev/nvidiactl dev/nvidiactl none bind,optional,create=file
lxc.mount.entry: /dev/nvidia-uvm dev/nvidia-uvm none bind,optional,create=file
lxc.mount.entry: /dev/nvidia-uvm-tools dev/nvidia-uvm-tools none bind,optional,create=file
lxc.mount.entry: /dev/nvidia-caps/nvidia-cap1 ... 
lxc.mount.entry: /dev/nvidia-caps/nvidia-cap2 ...
```

## Physical disks

| Dev | Size | Model | Use | Migrate? |
|---|---|---|---|---|
| sda + sdb | 2× 2 TB | WD20EFRX (WD Red) | `md0` **RAID1** → dd-nas live data (`/media/volume1`) | **YES — live precious data. 100 % FULL (1.7 T)** |
| sdc | 4 TB | WD40EFZX (WD Red) | ext4 `/mnt/frigate-storage` → Frigate recordings **+ stale NAS copy** | **100 % FULL** — recordings disposable; the NAS copy is reclaimable cruft |
| sde | 240 GB | SanDisk Ultra II | Proxmox boot + `local-lvm` (all guest OS disks) | No — stays in Gen8 |
| sdd | 120 GB | Intel SSDSC2CW120A3 | **unused** (stale ESXi VMFS partitions) | Free to repurpose/wipe |

**Storage pools (PVE):**
- `local` (dir, 64 G) on pve-root
- `local-lvm` (lvmthin, 146 G, ~71 % used) — holds all tiny guest disks
  (15/32/25/4/25 G). Note benign thin-overprovision warning on `vm-106-disk-0`.

**NAS data path:** `dd-nas` gets the raw array via `scsi1: /dev/md0,size=1953382464K`.
`md0` = mdadm RAID1, active, members `/dev/sda` + `/dev/sdb`, 1862 GiB. Inside the VM
it's `/dev/sdb` → `/media/volume1`, **1.7 T used / 1.8 T (100 % full)** — the LIVE copy
of documents/photos/music/movies. (dd-nas root is also tight: 13 G/14 G, 95 %.)

**The 4 TB (`/mnt/frigate-storage`) is mixed-use, NOT a Frigate-only disk:**
```
1.9T recordings   ← Frigate (~80 days retention; the big consumer)
857G downloads    ← replaceable
231G zRH0v6L8Pg   ← ??? (Syncthing/Nextcloud-style folder name)
182G documents    ┐ STALE one-time copy of the NAS data, made during the
148G photo        │ ESXi→Proxmox migration. Live copies are on the 2 TB above.
 47G music        ┘ → reclaimable (~1.3 T) once the live copy is verified.
 30G clips        ← Frigate
```
⚠ The precious data (documents + photos ≈ **330 GB**) lives **live on the 2 TB RAID1**,
with only a stale, in-box, same-machine second copy on the 4 TB. No real/offsite backup
yet — see [06-backup.md](06-backup.md).
