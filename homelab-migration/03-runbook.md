# 03 — Migration runbook

Order is chosen so the old Gen8 keeps running as a live rollback until each service
is verified on the new server. Commands assume `root@prox` = Gen8 (old),
`root@prox2` = new server (rename as you like).

> Back up **before** touching anything. The ~330 GB of photos/docs on the 2 TB NAS
> (`/media/volume1`) is the only irreplaceable data — get a verified copy off-box first
> (see [06-backup.md](06-backup.md)).

---

## Phase 0 — Prep (old stack stays live)

On the Gen8:

```bash
# Snapshot the current config for reference
ssh root@prox 'qm config 102; qm config 103; for c in 105 106 107; do pct config $c; done' > gen8-configs.txt

# Fresh backups of every guest to the dir storage (or an NFS/USB target)
ssh root@prox 'vzdump 102 103 105 106 107 --storage local --mode snapshot --compress zstd'
# -> /var/lib/vz/dump/vzdump-{qemu,lxc}-<id>-*.{vma,tar}.zst
```

Independently back up the **precious NAS data** (~330 GB photos+docs on
`/media/volume1`), not just the VM config. Copy it to the spare **3 TB** or an external
disk — **NOT the 4 TB, which is 100 % full**. This is the safety net if the disk
relocation in Phase 3 goes wrong; see [06-backup.md](06-backup.md). Don't rely solely on
the relocation step.

---

## Phase 1 — Build + base install (new server)

> **Hardware shuffle:** the new server is built **in dd-room's case**, using dd-room's
> RTX 3060. So this phase starts by **tearing dd-room down** — which takes your desktop
> offline. dd-room's internals (board/CPU/RAM/drives, **minus the 3060**) get rebuilt
> into the spare **mini-ITX** box afterward; that can run in parallel with the migration.
> Same board ⇒ same MAC ⇒ dd-room's HA wake/power controls keep working unchanged.

0. **Tear down dd-room:** power it off, pull the **RTX 3060**, strip the board/CPU/RAM
   out of the case. Set the dd-room parts aside for the mini-ITX rebuild.
1. Assemble the new server **in the dd-room case**: RAM in **A2/B2**, enable **DOCP**
   (3200), seat the **1 TB SSD on M.2_1**, install the **RTX 3060**. Leave the WD HDDs
   OUT for now (added in Phase 3/4).
2. Install **Proxmox VE 9.x** on the 1 TB SSD (ZFS-on-root recommended for snapshots,
   or LVM-thin to mirror the Gen8 — either is fine).
3. Network: bridge `vmbr0`, new hostname (`prox2`) + a free static IP. It now sits on
   the LAN beside the Gen8, nothing migrated yet.
4. Copy the backups over:
   ```bash
   scp root@prox:/var/lib/vz/dump/vzdump-*.zst root@prox2:/var/lib/vz/dump/
   ```

### NVIDIA driver on the new host (needed before Frigate/TTS/Ollama)

```bash
# On prox2 — install the SAME driver branch you'll use inside the containers.
apt update && apt install -y pve-headers-$(uname -r) build-essential
# Use a recent enough branch for Ampere (RTX 3060). Driver pkg or .run installer:
#   nvidia-smi must show "NVIDIA GeForce RTX 3060".
nvidia-smi
ls -l /dev/nvidia*   # confirm /dev/nvidia0, nvidiactl, nvidia-uvm exist
```

The major/minor numbers may differ from the Gen8's (195/508/511). Read the new ones
and update the `lxc.cgroup2.devices.allow` lines accordingly (see 04-cutover-gotchas).

---

## Phase 2 — Restore the small/non-critical guests first

These have no physical-disk dependency; restore onto `local-lvm`, keep them **stopped**
(old copies still serve traffic).

```bash
# On prox2 — restore guests, keep original IDs
qmrestore /var/lib/vz/dump/vzdump-qemu-103-*.zst 103   # HA  (don't start yet)
pct restore 107 /var/lib/vz/dump/vzdump-lxc-107-*.zst  # TTS
pct restore 106 /var/lib/vz/dump/vzdump-lxc-106-*.zst  # Frigate
pct restore 105 /var/lib/vz/dump/vzdump-lxc-105-*.zst  # Pi-hole
```

`qmrestore`/`pct restore` **preserve the NIC MAC**, so each guest keeps its DHCP
lease / static IP when it eventually boots.

---

## Phase 3 — NAS storage move (2 TB RAID1)

The clean part: the mdadm superblock lives on the disks, so the array reassembles
itself on the new host. **No data copy.**

```bash
# 1. Stop the NAS on the Gen8
ssh root@prox 'qm stop 102'

# 2. Physically move sda + sdb into the new server (power off prox2 first)

# 3. On prox2 — the array should auto-assemble; if not:
mdadm --assemble --scan
cat /proc/mdstat                       # expect md0 active, raid1, 2 devices
blkid /dev/md0                         # confirm the ext4 fs is seen

# 4. Persist the array name across reboots
mdadm --detail --scan >> /etc/mdadm/mdadm.conf
update-initramfs -u

# 5. Restore the NAS VM and attach the array
qmrestore /var/lib/vz/dump/vzdump-qemu-102-*.zst 102
# The restored 102.conf still references scsi1: /dev/md0 — verify the path matches:
qm set 102 --scsi1 /dev/md0,size=1953382464K
qm start 102
```

> **Zero-downtime variant (optional):** because it's a mirror, move ONE disk to prox2,
> assemble degraded (`mdadm --assemble --run /dev/md0 /dev/sdX`), verify reads, then
> move the second disk and `mdadm --add` to resync. More steps; only worth it if you
> can't take the NAS down briefly.

Verify shares/data, then leave the Gen8's dd-nas powered off as rollback.

---

## Phase 4 — Frigate + TTS (GPU services)

> ⚠ **sdc is NOT disposable.** Besides Frigate recordings it holds a stale
> ESXi-migration copy of NAS data (photos/documents/music) — see 01-inventory. The
> *recordings* are disposable; the NAS copy is reclaimable only AFTER you've verified
> the live 2 TB copy (Phase 3) is intact. Don't `mkfs` this disk.

**Recommended: re-architect rather than carry two full drives over.** Move sdc, mount
it, then reclaim the stale NAS copy and cap Frigate retention so CCTV can't crowd out
data again.

```bash
# Relocate: move sdc into prox2, then on prox2:
mkdir -p /mnt/frigate-storage
blkid /dev/sdc                          # get UUID
echo 'UUID=<uuid> /mnt/frigate-storage ext4 defaults,nofail 0 2' >> /etc/fstab
mount -a
df -h /mnt/frigate-storage

# Reclaim ~1.3 T of stale migration copy — ONLY after verifying the live 2 TB NAS:
#   rm -rf /mnt/frigate-storage/{documents,photo,music,downloads,zRH0v6L8Pg}
# Then cap Frigate retention in its config (e.g. days: 80 -> 30) to free more.

# Start the GPU containers (after the NVIDIA driver is confirmed in Phase 1)
pct start 107        # TTS
pct start 106        # Frigate
```

Inside each container, align the NVIDIA userspace driver to the host version and, if
Frigate uses the **TensorRT** detector, regenerate the model for Ampere (sm_86) —
details in [04-cutover-gotchas.md](04-cutover-gotchas.md).

---

## Phase 5 — DNS + Home Assistant cutover (critical infra)

### Pi-hole (DNS @ 192.168.x.x)

```bash
# Stop the OLD one FIRST so .254 isn't claimed twice, then start the new one.
ssh root@prox 'pct stop 105'
pct start 105                            # same static IP from 105.conf
```

Have the **router DNS as a temporary fallback** on clients in case of a hiccup —
losing .254 means `.home` names (incl. some HA lookups) stop resolving.

### Home Assistant (dd-haos)

```bash
# Physically move the 2 USB dongles (RTL-SDR 0bda:2838 + 0b05:190e) to prox2.
lsusb                                    # confirm both enumerate on the new host
ssh root@prox 'qm stop 103'              # stop OLD HA
# Restored 103.conf keeps usb1/usb2 lines + same NIC MAC -> same IP (dd-ha)
qm start 103
```

Verify `http://dd-ha:8123`, that rtl_433/Linky + the other dongle work, and that
`push_dashboards.py` from this repo still deploys.

---

## Phase 6 — New: Ollama on the 3060

```bash
# New LXC modeled on dd-tts (same nvidia bind-mount + cgroup allows), install Ollama.
# Point the voice-assistant LLM at it instead of dd-home's CPU.
```

---

## Phase 7 — Retire Gen8 → Proxmox Backup Server

Once everything is verified on the new server for a few days:

```bash
# Wipe the 240 GB SanDisk, install Proxmox Backup Server.
# Add it as a storage target on prox2 and schedule nightly backups of all guests.
# The 120 GB Intel SSD is free scratch; the spare 3 TB becomes the PBS datastore.
```

- **Rename now that the dust has settled:** the new server `prox2` → **`prox`**, the
  Gen8 → **`pbs`**.
- Set up the **cold/wake-for-backup** cycle so `pbs` stays powered off except during the
  backup window — see [07-cold-pbs.md](07-cold-pbs.md).
- Backup *destination* details (3 TB datastore, precious-data file backup, offsite
  rotation) are in [06-backup.md](06-backup.md).

---

## Phase 8 — Repo / HA touch-ups (this repo)

`dd-room` is **not** retiring — it lives on as a GPU-less desktop in the mini-ITX box —
so **keep** its power-control plumbing (`dashboard_controle.yaml` chips, the dd-ha
`shell_command`/`command_line` sensors, the locked SSH key). Same board ⇒ same MAC ⇒
WoL/suspend/shutdown all still work. Only adjust:

- **GPU power term drops:** the power estimate's `gpu_w` (via `nvidia-smi`) is now always
  null — dd-room has no GPU. The sensor still reports CPU + DRAM + baseline. Optionally
  drop the GPU line from the reader and the card's "(estimé)" wording. See
  `project_ddroom_power` memory.
- **If the mini-ITX rebuild changes the NIC** (different board/onboard NIC), update the
  WoL MAC (`AA:BB:CC:DD:EE:FF`) in HA. Same board = no change needed.
