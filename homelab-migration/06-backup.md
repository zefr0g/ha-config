# 06 — Backup strategy (zero-spend)

## The reframe

You don't have a storage-cost problem, you have a **~330 GB problem**. The NAS is mostly
**replaceable** data (downloaded movies) — RAID1 already covers that. The only
**irreplaceable** slice is **photos (~148 G) + documents (~182 G) ≈ 330 GB**. Backing up
330 GB is trivial with drives you already own. Stop sizing backup against the whole
multi-TB NAS.

**Where it lives:** the LIVE copy is on the **dd-nas 2 TB RAID1** (`/media/volume1`).
There's also a *stale* copy on the 4 TB from the ESXi→Proxmox migration, but it's
in-box, same-machine, and frozen — it is **NOT a backup**. Both data drives are
currently 100 % full, so this is also the moment to give the precious data room.
**Backup source = dd-nas `/media/volume1`, not the 4 TB.**

## Available spare drives

| Drive | Role in this plan |
|---|---|
| **3 TB** (unused) | PBS datastore on the Gen8 — versioned backup target |
| **500 GB** ×2 | Offsite rotation (one always off-premises, encrypted) |
| **320 GB** | Scratch / spare |

## Target: real 3-2-1 for the precious ~330 GB

| Copy | Where | Drive | Protects against |
|---|---|---|---|
| 1 — live | NAS on new server | 2 TB RAID1 | disk failure |
| 2 — versioned | **Gen8 / PBS** | 3 TB | deletion, corruption, ransomware, box death |
| 3 — offsite | relative's / desk | 500 GB (encrypted) | fire, theft, flood |

Three copies, two machines, one offsite — for **€0**.

## Step 0 — Separate precious from replaceable

On the NAS the precious folders (`documents`, `photo`) already live alongside movies on
the full 2 TB. Keep them grouped so the backup job has a clean, small target and can
never pull in the movies. Conceptually:

```
/media/volume1/<movies, downloads ...>   <- replaceable, NOT backed up
/media/volume1/{documents,photo}         <- ~330 GB, backed up everywhere
```

## Step 1 — Health-check the sitting drives first

They've been idle; verify before trusting them.

```bash
smartctl -a /dev/sdX | grep -Ei 'Reallocated|Pending|Uncorrect|Power_On_Hours|health'
smartctl -t short /dev/sdX        # then re-read after a few minutes
```

## Copy 2 — versioned backup to PBS (3 TB on the Gen8)

You're already deploying PBS on the Gen8. `proxmox-backup-client` does **file-level,
versioned, deduplicated, encrypted** backups — not just VMs.

### On the Gen8 (PBS side)
```bash
# Create a datastore on the 3 TB drive
mkfs.ext4 /dev/sdX                       # the 3 TB (or add as ZFS for scrubbing)
mkdir -p /mnt/pbs-store
echo 'UUID=<uuid> /mnt/pbs-store ext4 defaults,nofail 0 2' >> /etc/fstab && mount -a
proxmox-backup-manager datastore create backup /mnt/pbs-store
proxmox-backup-manager user create backup@pbs
# grant it on the datastore via the PBS UI or:
proxmox-backup-manager acl update /datastore/backup DatastoreBackup --auth-id backup@pbs
```

### On the NAS (client side) — push the precious dataset
```bash
apt install -y proxmox-backup-client      # if not present in the guest

# One-time: generate an encryption key, store it OFF this machine too
proxmox-backup-client key create /root/pbs-precious.key

export PBS_REPOSITORY='backup@pbs@gen8:backup'
export PBS_PASSWORD='<datastore-user-password>'

proxmox-backup-client backup \
  precious.pxar:/media/volume1/precious \   # adjust to the real photos+docs path(s)
  --repository "$PBS_REPOSITORY" \
  --keyfile /root/pbs-precious.key
```

### Schedule + retention (on the NAS, via cron/systemd-timer)
```bash
# nightly backup, then prune to a sane history
proxmox-backup-client prune precious \
  --repository "$PBS_REPOSITORY" \
  --keep-daily 7 --keep-weekly 4 --keep-monthly 6
```
Dedup means months of ~330 GB versions still use a fraction of the 3 TB. Periodically
run a **verify** job in PBS so you find rot before you need the backup.

> Keep the `pbs-precious.key` somewhere other than the NAS (password manager / the
> offsite drive). No key = no restore.

## Copy 3 — offsite, encrypted (500 GB, rotated)

`restic` is encrypted-by-default, dedups, and is dead simple. Refresh every month or two
and swap which 500 GB lives off-premises.

```bash
# Mount the 500 GB (optionally LUKS-encrypt the whole disk for physical theft)
export RESTIC_REPOSITORY=/mnt/offsite500/restic-precious
export RESTIC_PASSWORD_FILE=/root/.restic-pass        # keep this safe + off-disk

restic init                                            # first time only
restic backup /media/volume1/documents /media/volume1/photo
restic forget --keep-monthly 12 --prune
restic check                                           # verify integrity
```
Then physically take the drive off-site and bring the other one back for next round.

## Restore drills (do these — an untested backup isn't a backup)

```bash
# From PBS:
proxmox-backup-client restore precious.pxar /tmp/restore-test \
  --repository "$PBS_REPOSITORY" --keyfile /root/pbs-precious.key

# From restic offsite:
restic restore latest --target /tmp/restore-test
```
Confirm a few photos/docs open correctly. Schedule a reminder to re-drill twice a year.
