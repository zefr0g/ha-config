# Homelab migration — Gen8 → B550M/5700G

Migration runbook for moving the Proxmox stack off the HP MicroServer Gen8 (`prox`)
onto a new B550M / Ryzen 5700G server, and retiring the Gen8 as a backup target.

| Doc | Purpose |
|---|---|
| [01-inventory.md](01-inventory.md) | Current ground-truth: hosts, guests, GPU, disks, RAM |
| [02-target.md](02-target.md) | End-state architecture + hardware mapping |
| [03-runbook.md](03-runbook.md) | Command-by-command migration steps |
| [04-cutover-gotchas.md](04-cutover-gotchas.md) | DNS, USB, GPU-driver, VRAM traps to avoid |
| [05-improvements.md](05-improvements.md) | Setup review — resilience/efficiency items, ranked |
| [06-backup.md](06-backup.md) | Zero-spend 3-2-1 backup for the precious ~330 GB |
| [07-cold-pbs.md](07-cold-pbs.md) | Wake-for-backup: keep PBS powered off, woken only to back up |

**One-line summary:** the only irreplaceable data is **~330 GB of photos/docs** on the
**2 TB NAS RAID1** (`/media/volume1`) — the NAS disks move by physical relocation (mdadm
reassembles, no copy). The 4 TB is mixed Frigate footage + a stale, reclaimable NAS copy
(not a disposable Frigate-only disk); every guest OS disk is tiny and restores over the
network. The new server is built **in dd-room's case** (dd-room lives on, GPU-less, in a
spare mini-ITX box). The new 32 GB ends the Gen8's current RAM oversubscription/swapping.

Inspected live on `root@prox` 2026-06-30 (PVE 9.1.7).
