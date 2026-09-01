# 08 — Phasing out the 2×2 TB WD Red drives

**Status:** planned (2026-07-22). The two 2 TB WD Reds are *working fine* — this is a
scheduled retirement, not an emergency. The point is to move the NAS off them
**before** they fail, on our schedule, with the old mirror kept as a live rollback the
whole time.

## Why

`md0` (RAID1) = 2× WD20EFRX at **~107,000 power-on hours (~12.3 years)**, same model,
same batch, same hours → classic correlated-failure risk (twin often dies during the
resilver after the first one goes). They hold the dd-nas live data. SMART says PASSED,
but at these hours that means little.

Key facts that shape the plan:
- NAS volume `/media/volume1` = **1.3 T used / 1.8 T**. Breakdown: downloads 890 G
  (disposable), photo 223 G (precious, backed up), documents 155 G (precious, backed up),
  music 47 G (**not** backed up), cloud 41 M.
- Precious data (photo+documents) is already in PBS nightly, and will gain a second copy
  once the SMR copy datastore is live. So a **single** NAS drive is acceptable — we are
  not buying a mirror. (RAID ≠ backup; see notes in this repo.)
- The healthy **4 TB WD Red Plus (CMR)** currently doing Frigate is the ideal new NAS
  drive. Frigate footage is disposable, so it drops down to an old 2 TB.

## Drive roles: before → after

| Drive | Now | After |
|---|---|---|
| Samsung 980 1 TB NVMe (prox) | rpool / guests | unchanged |
| WD40EFZX 4 TB Red Plus (prox `sdc`) | Frigate `/mnt/frigate-storage` | **dd-nas `/media/volume1`** |
| WD20EFRX 2 TB #1 (prox) | `md0` RAID1 → NAS | **Frigate** (disposable) |
| WD20EFRX 2 TB #2 (prox) | `md0` RAID1 → NAS | **cold spare** (shelved/retired) |
| MB3000 3 TB (pbs `sdd`) | `backup` datastore | unchanged |
| ST4000DM004 4 TB SMR (pbs `sda`) | unassigned (stale NTFS) | **`copy` datastore** |
| 500 GB + 320 GB junk (pbs) | idle | **removed** |

End state: dying drives out of every precious role (one earns its keep on disposable
Frigate duty, one shelved), NAS bigger and on a healthy CMR disk, backup redundancy
restored, two Gen8 bays freed. **No purchase.**

## The circular dependency (and how we break it)

The 4 TB we want for NAS is busy with Frigate; the 2 TB we want for Frigate is busy with
NAS. We break the loop using the fact that **Frigate data is disposable**: park Frigate
first, free the 4 TB, migrate NAS onto it while `md0` stays fully intact as a fallback,
and only *after* the new NAS is proven do we break the mirror to give Frigate a 2 TB.

> ⚠️ Always address drives by `/dev/disk/by-id/...`, never `sdX` — letters move when you
> add/remove disks. Confirm every device with `lsblk -o NAME,SIZE,MODEL,SERIAL` first.

---

## Phase 0 — Preflight (no disruption)

1. Confirm last night's cold cycle was green end-to-end (backup → GC → sync → copy GC →
   poweroff): on prox `systemctl status pbs-backup-cycle.service` and check PBS task log.
2. Note the current NAS numbers as your verification baseline:
   ```
   ssh root@dd-nas.home 'df -h /media/volume1; find /media/volume1 -xdev | wc -l; du -sb /media/volume1'
   ```
3. `smartctl -a` snapshot of both 2 TB drives (so you can watch for any change mid-move).

## Phase 1 — Close the backup gaps FIRST (before touching any drive)

The whole plan leans on "precious data is backed up." Make that fully true first.

1. Add **music/** (47 G) to the dd-nas PBS backup (extend the `proxmox-backup-client`
   archive list that already covers `documents` and `photo`). Downloads stay excluded by
   choice (disposable).
2. Run one manual cycle and confirm the new `music.pxar` lands in `host/dd-nas`.
3. **Prove a restore** — restore one photo folder from PBS to a temp dir. A backup you
   haven't restored from is a hypothesis, not a backup.

## Phase 2 — Free the 4 TB and copy NAS onto it (NAS stays UP, `md0` stays INTACT)

Frigate goes down here and stays down until Phase 4. Accept the recording gap, or see
"Shortening Frigate downtime" below.

1. Stop Frigate: `pct stop 106` (on prox).
2. Unmount and wipe the 4 TB (its Frigate data is disposable):
   ```
   umount /mnt/frigate-storage
   wipefs -a /dev/disk/by-id/ata-WDC_WD40EFZX-...     # confirm it's the 4 TB!
   mkfs.ext4 -L nas-data /dev/disk/by-id/ata-WDC_WD40EFZX-...
   ```
3. Attach the 4 TB to the dd-nas VM as a new raw disk (mirrors the current passthrough
   architecture), keeping it out of vzdump:
   ```
   qm set 102 -scsi2 /dev/disk/by-id/ata-WDC_WD40EFZX-...,backup=0
   ```
4. Inside dd-nas, mount it and copy **live** (NAS keeps serving off `md0`):
   ```
   mkdir -p /mnt/nas-new && mount /dev/sdc /mnt/nas-new     # confirm the new disk letter
   rsync -aHAX --info=progress2 --delete /media/volume1/ /mnt/nas-new/
   ```
   `md0` remains the live, mirrored volume throughout — full rollback safety net.

## Phase 3 — Cut NAS over to the 4 TB (keep `md0` as rollback)

1. Quiesce writers (stop services that write to the NAS, or do this at a quiet time).
2. Final delta sync + verify against the Phase 0 baseline:
   ```
   rsync -aHAX --delete /media/volume1/ /mnt/nas-new/
   find /mnt/nas-new -xdev | wc -l          # compare file count
   du -sb /mnt/nas-new                       # compare bytes
   ```
   Spot-check a few `sha256sum` pairs on important files.
3. Swap the mount so `/media/volume1` is the new disk (persist by **UUID** in the VM's
   `/etc/fstab`; get it with `blkid`):
   ```
   umount /media/volume1        # this is md0
   # edit /etc/fstab: /media/volume1 -> UUID=<4TB> ext4 defaults 0 2
   mount /media/volume1
   ```
4. Bring NAS services back. Confirm reads/writes land on the 4 TB (`df -h /media/volume1`,
   `lsblk`). Re-run the desktop `backup-to-nas.sh --dry-run` to confirm the share path.
5. **Soak: leave `md0` assembled and untouched for ~a week.** It still holds the old data
   — instant rollback if anything looks off (just remount md0 at `/media/volume1`).

## Phase 4 — Break the mirror, hand Frigate a 2 TB, shelve the other (after soak)

Only once the 4 TB NAS is proven:

1. Detach `md0` from the VM and stop the array:
   ```
   qm set 102 -delete scsi1        # removes the old /dev/md0 passthrough
   mdadm --stop /dev/md0
   mdadm --zero-superblock /dev/disk/by-id/ata-WDC_WD20EFRX-...#1   # and #2
   ```
2. Pick one 2 TB for Frigate (either — they're twins; prefer the lower reallocated count),
   format and mount it as the Frigate store:
   ```
   mkfs.ext4 -L frigate /dev/disk/by-id/ata-WDC_WD20EFRX-...#1
   # mount at /mnt/frigate-storage (add to prox /etc/fstab by UUID)
   pct start 106                    # Frigate records again, on a disposable drive
   ```
3. Physically pull the other 2 TB → label it and shelf it as a cold spare (when the
   Frigate one dies, swap this in; lose nothing that matters).

## Phase 5 — PBS `copy` datastore on the SMR (independent — do anytime)

Restores your second local copy of backups; gives photo/documents 3 copies total.

1. On pbs, wipe the SMR's stale NTFS and format:
   ```
   wipefs -a /dev/disk/by-id/ata-ST4000DM004-...
   mkfs.ext4 -L pbs-copy /dev/disk/by-id/ata-ST4000DM004-...
   ```
2. Repoint the copy mount to the new UUID. Either edit
   `/etc/systemd/system/mnt-datastore-copy.mount` (`What=/dev/disk/by-uuid/<new>`) and
   `systemctl daemon-reload && systemctl start mnt-datastore-copy.mount`, **or** delete +
   re-add the `copy` datastore in the PBS UI (regenerates the unit cleanly).
3. Run the `s-copy` sync job to repopulate, then verify + GC. Confirm the nightly cycle
   picks it up again.

## Phase 6 — Cleanup

1. Pull the junk 500 GB + 320 GB from the Gen8 (frees two bays).
2. Watch one full nightly `pbs-backup-cycle` run green end-to-end with the new copy disk.

---

## Shortening Frigate downtime

Frigate is down from Phase 2 → Phase 4 (potentially a week of soak). If a camera gap that
long bothers you, either:
- **Break the mirror early** (do Phase 4's 2 TB step right after Phase 3 verify, skipping
  the soak) — trades the `md0` fallback for faster Frigate restore; acceptable because
  precious data is still in PBS. Or
- **Park Frigate on NVMe temporarily** during the soak (rpool has ~730 G free; wears the
  SSD a little, tolerable for a week).

## Rollback summary

- **During Phases 2–3:** `md0` is intact and mirrored — remount it at `/media/volume1` to
  revert instantly.
- **After Phase 4:** rollback is a PBS restore (precious data) + re-download (disposable);
  the shelved 2 TB is your hardware spare.
- **Precious data is never at single-point risk:** it lives on the NAS *and* PBS `backup`
  *and* (Phase 5+) PBS `copy` throughout.
