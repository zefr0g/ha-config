# 05 — Setup review & improvements

Assessment of the post-migration architecture. The design is sound; these are
resilience/efficiency items ranked by value. Tracked here so they don't get lost
behind the migration mechanics.

## Verdict

The core choices are right: **LXC for Frigate/TTS/Pi-hole, VM only for HAOS, one GPU
shared across detector + TTS + Ollama, Gen8 retired to PBS rather than scrapped.** The
real shift is going from 3 boxes to 1 — that trades **redundancy for capability**.
That's fine *if* the two things that can't tolerate downtime — **DNS and the
irreplaceable data** — each have an independent safety net. Close those and it's a
setup worth running.

## Improvements (ranked)

### 1. DNS is the worst single point of failure — FIX
Pi-hole at `192.168.x.x` is the only resolver, and it's about to live on the same box
as everything else. A host reboot/update = **whole-house DNS outage**, and HA's `.home`
lookups break with it.
- **Fix:** run a lightweight **secondary resolver on a different always-on device**
  (Pi satellite, router, or a tiny `unbound`/second Pi-hole). Hand clients both via
  DHCP. Decouples DNS from hypervisor uptime for near-zero cost.

### 2. Real backup for the irreplaceable data — FIX
RAID1 protects against a disk dying, **not** deletion/corruption/ransomware/box-death.
The precious slice is only ~330 GB (photos + docs); movies are replaceable. Full plan
with existing spare drives in **[06-backup.md](06-backup.md)** — zero spend.

### 3. Offload Frigate decode to the 5700G iGPU — OPTIMIZE
The Vega iGPU sits idle while the 3060 does everything. Point Frigate's ffmpeg at
**VAAPI (iGPU)** for stream *decode*, keep the **3060 for the detector + Ollama**.
Splits load, frees VRAM, lowers 3060 power/thermals. Easy win once running.

### 4. ZFS-mirror for the NAS instead of mdadm + ext4 — LATER
mdadm RAID1 can't detect **silent bit-rot** — it mirrors whatever it's handed. A ZFS
mirror checksums every block and self-heals on scrub. Matters for long-term photos/docs.
Not in-place (needs a copy), so this is a "when you build the real NAS" item, not now.

## Already handled / accepted
- **UPS:** Gen8 is already on one — make sure the **new server shares it** (and wire NUT
  for clean auto-shutdown). ✔ mostly done.
- **Frigate disk 100 % full:** tune retention as part of the move, don't carry the
  problem over.
- **No ECC** on the 5700G (non-Pro) + Corsair kit — slight integrity downgrade vs the
  Gen8 for NAS use. Accepted; mitigated by the ZFS-later + backup plan.
