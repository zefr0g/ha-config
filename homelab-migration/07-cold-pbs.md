# 07 — Cold PBS (wake-for-backup, sleep after)

Goal: keep the Gen8 / `pbs` **powered off most of the time**, woken only for the backup
window, then shut back down. Benefits: it's **air-gapped while cold** (ransomware /
accidental deletes can't reach an off machine), near-zero idle power, and less wear on
old hardware.

## Architecture — prox orchestrates the cycle

Push-backup model: `prox` initiates, so it knows when the job finishes and can safely
power `pbs` back down.

```
prox  (nightly systemd timer)
  1. WoL magic packet → pbs
  2. poll until pbs is up (ping + port 8007)   [timeout → alert, abort]
  3. vzdump 102 103 105 106 107  → PBS datastore
  4. proxmox-backup-client  → push dd-nas precious data (see 06-backup)
  5. PBS verify + prune                         [must finish before poweroff]
  6. ssh pbs 'poweroff'  (locked key)
  7. notify HA (success / failure)
```

## Prerequisites

### Wake-on-LAN on the Gen8
- Enable **WoL** in BIOS (and optionally **RTC power-on** as a fallback, below).
- Persist on the NIC: `ethtool -s <iface> wol g` (via a systemd unit or
  `/etc/network/interfaces` `post-up`). Verify with `ethtool <iface> | grep Wake-on`.
- Note the NIC **MAC** for the magic packet.

### Locked SSH key prox → pbs (reuse the dd-room pattern)
On `pbs`, restrict the key to a whitelist wrapper so even a leaked key can only power off
(see the `project_ddroom_power` design — `command="/usr/local/bin/power-control.sh"` in
`authorized_keys`, allowing only `poweroff`). PBS suspend/poweroff over SSH may need a
polkit rule like dd-room did.

## Orchestration script (on prox)

`/usr/local/bin/backup-cycle.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
PBS_MAC="AA:BB:CC:DD:EE:FF"      # Gen8 NIC
PBS_HOST="pbs"
GUESTS="102 103 105 106 107"

notify() { ssh root@dd-ha "ha ..." 2>/dev/null || true; }   # or HA webhook

# 1. Wake
wakeonlan "$PBS_MAC" || etherwake "$PBS_MAC"

# 2. Wait for PBS (max ~5 min)
up=0
for i in $(seq 1 60); do
  if ping -c1 -W1 "$PBS_HOST" >/dev/null 2>&1 && nc -z "$PBS_HOST" 8007 2>/dev/null; then
    up=1; break
  fi
  sleep 5
done
[ "$up" = 1 ] || { notify "PBS failed to wake — backup ABORTED"; exit 1; }

# 3. Guest backups → PBS storage (define a 'pbs' storage in prox pointing at the datastore)
vzdump $GUESTS --storage pbs --mode snapshot --quiet 1

# 4. Precious file-level backup is pushed from dd-nas (cron inside the guest, or:)
ssh root@dd-nas '/usr/local/bin/backup-precious.sh'   # wraps proxmox-backup-client (06)

# 5. Verify + prune on PBS BEFORE shutdown (never poweroff mid-GC)
ssh root@"$PBS_HOST" 'proxmox-backup-manager verify backup --quiet || true'
# prune is configured as a PBS retention job; let it complete

# 6. Sleep
ssh pbs-power 'poweroff'      # ssh alias using the locked key
notify "PBS backup complete — powered down"
```

systemd timer:

```ini
# /etc/systemd/system/backup-cycle.timer
[Timer]
OnCalendar=*-*-* 03:30:00
Persistent=true
[Install]
WantedBy=timers.target
```

## Fast-restore safety net (important)

Cold PBS means restores wait ~1–2 min for it to boot. So **also keep a short local
retention on prox** (2–3 days of vzdump on a local disk) for instant "oops" restores.
PBS holds the long history; local holds the quick-grab copy.

## Wake fallback — BIOS RTC

If you'd rather not depend on prox's timer, set the Gen8 BIOS to **auto power-on at
03:25** daily. Then PBS's own scheduled jobs run, and a **post-job hook** powers it off
when idle. Belt-and-suspenders: combine RTC wake + prox-driven poweroff.

## HA backup indicator (DONE — dashboard card off the existing MQTT status)

Fully wired 2026-07-30, no prox changes needed. The orchestrator **already** publishes
its outcome as a retained message, and HA now consumes it:

- **Publisher (existing):** `pbs-backup-cycle.sh` → retained topic `prox/pbs_backup/status`
  (paho, best-effort, creds `/etc/ha-host-temps.creds`). Payload:
  `{"result":"ok|fail|running","msg":"...","finished":"YYYY-MM-DD HH:MM:SS"}` (a
  `running` message carries `started` instead).
- **HA sensor:** `mqtt_pbs.yaml` → `sensor.pbs_backup_status` (state = `result`, attrs
  `msg`/`finished`). Wired via `mqtt: !include mqtt_pbs.yaml` in `configuration.yaml`
  (one-time HA restart to register the `mqtt:` key; later edits reload via the
  `mqtt.reload` service).
- **Dashboard:** a "Sauvegardes" card at the top of the Proxmox view derives health
  **inline** — cold PBS means offline is *healthy*, so it shows outcome/freshness, not
  up/down:

| Card state | Meaning |
|------------|---------|
| ✅ ok | last cycle succeeded, recent |
| 🔄 running | a cycle is in progress |
| ⚠️ stale | last result ok but >48h old (timer stopped firing) |
| ❌ failed | last cycle reported `fail` (wake timeout / backup error) |
| ⏳ waiting | no report received yet |

Retained means HA shows the last outcome even while prox **and** the Gen8 are asleep, and
it survives HA restarts. The card also carries a zero-plumbing "Config HA" section for
HA's own native backup manager.

**Optional next step:** a proactive push notification on `failed`/`stale` (dashboard-only
today) — e.g. an automation on `sensor.pbs_backup_status` → `fail`, plus a daily template
check for staleness.

## Caveats

- **Exposure window:** PBS is reachable from prox during the backup minutes. If prox
  itself is compromised it could reach PBS then. Mitigation: PBS verify + retention, and
  rely on the **offsite 500 GB (copy 3)** as the truly-offline copy.
- **Don't poweroff during verify/GC** — the script sequences these before shutdown.
- **Missed windows:** `Persistent=true` runs a missed nightly on next boot of prox;
  alert on wake-failure so a dead Gen8 doesn't silently skip backups for weeks.
