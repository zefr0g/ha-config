# 02 — Target architecture

## Hardware mapping

| Box | Before | After |
|---|---|---|
| **New server** | (parts received) | Primary Proxmox host, **built in dd-room's gutted case**. B550M Pro4 + Ryzen **5700G** + **32 GB** DDR4-3200 (A2/B2, DOCP on) + **RTX 3060 12 GB** (from dd-room) + **1 TB SSD** (M.2: Proxmox boot + local-lvm). Headless, new hostname/IP. |
| **prox** (Gen8) | Primary host, 16 G, GTX 1650 | Retires to **Proxmox Backup Server** (backup target). 240 GB SanDisk + 120 GB Intel stay in it. NOT decommissioned. |
| **dd-room** | Desktop w/ RTX 3060, in its (m)ATX case | **NOT retired.** Internals (minus the 3060) move into a spare **mini-ITX** box (its old case) → lives on as a **GPU-less desktop**. Its case is what the new server is built in. Same board ⇒ same MAC ⇒ **HA wake/suspend/shutdown stay working**; only the GPU-watts term of the power estimate drops (no GPU). |
| **dd-home** | DeskMini X300 daily driver | Unchanged. Now boots Crucial P2; **Samsung 980 reserved for a future NAS** (NOT used here). |

> Note: the future NAS no longer inherits dd-room's case (that's now the server). NAS
> chassis is a later, separate decision.

## Guest end-state (all move to the new server)

```
NEW SERVER (Proxmox, RTX 3060 12 GB)
 ├─ VM  dd-nas      — /dev/md0 (2 TB RAID1, disks physically relocated)
 ├─ VM  dd-haos     — Home Assistant (dd-ha); USB dongles relocated
 ├─ LXC dd-pihole   — DNS @192.168.x.x (keep same IP)
 ├─ LXC dd-frigate  — GPU bind-mount; 4 TB footage disk (relocated or fresh)
 ├─ LXC dd-tts      — GPU bind-mount
 └─ LXC dd-ollama   — NEW: LLM inference on the 3060 (off dd-home CPU)
```

## Drive layout on the new server (B550M Pro4 = 6 SATA + 2 M.2)

| Slot | Drive | Role |
|---|---|---|
| M.2_1 | 1 TB SSD | Proxmox boot + `local-lvm` (guest OS disks) |
| SATA 1+2 | 2× 2 TB WD Red | `md0` RAID1 → dd-nas (relocated from Gen8) |
| SATA 3 | 4 TB WD Red | Frigate footage (relocated, or start fresh) |

Plenty of headroom left (M.2_2 + 3 SATA free) for the future NAS expansion.

## VRAM budget — RTX 3060 12 GB (shared)

| Consumer | Approx VRAM |
|---|---|
| Frigate detector | 1–2 G |
| Whisper/Piper (dd-tts) | 1–2 G |
| Ollama 7–8B model | ~6 G |
| **Total** | **~8–10 G — fits 12 G** |

Size Ollama models against the ~6 G headroom (a 7–8B quant is the sweet spot).
