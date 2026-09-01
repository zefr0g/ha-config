# 04 — Cutover gotchas

The traps specific to this stack. Read before Phase 4–5.

## 1. GPU swap GTX 1650 → RTX 3060 (Turing → Ampere)

Because the GPU is shared into the containers via **LXC bind-mounts** (not VFIO), the
container configs barely change — but three things must line up:

- **Host driver:** install a driver branch new enough for Ampere on `prox2`.
  `nvidia-smi` must report the RTX 3060 before starting any GPU container.
- **In-container driver version must MATCH the host.** LXC shares the host kernel
  module, so the userspace libs inside dd-frigate/dd-tts must be the same version as
  the host driver, or CUDA calls fail. Reinstall the matching driver **with
  `--no-kernel-module`** inside each container after the host is updated.
- **Device major/minor numbers may change.** The Gen8 used `c 195:*`, `c 508:*`,
  `c 511:*`. On the new host, check and update the `lxc.cgroup2.devices.allow` lines:
  ```bash
  ls -l /dev/nvidia* /dev/nvidia-caps/*    # note the major:minor of each
  ```
  The `195` (nvidia0/nvidiactl) is stable; the `508`/`511` (uvm, caps) can differ.

- **Frigate TensorRT model:** if the detector is `tensorrt`, the engine is compiled for
  the GPU's compute capability. 1650 = sm_75, 3060 = **sm_86** — the old engine won't
  load. Regenerate it (Frigate's `tensorrt` model generator, set the correct
  `USE_FP16`/arch), or switch the detector to ONNX/OpenVINO which is arch-agnostic.

## 2. Pi-hole = single point of DNS failure

`dd-pihole` serves DNS at **192.168.x.x** for the whole house, and HA Core resolves
`.home` names through it. During cutover:

- **Never run two Pi-holes on .254** — stop the old before starting the new.
- Keep the **router's DNS as a fallback** on clients during the swap window.
- After cutover, re-verify a `.home` lookup from the HA VM
  (e.g. `dd-room.home` if still referenced) before assuming success.

## 3. HA USB dongles are physical

`dd-haos` passes two USB devices straight through:

| ID | Likely device |
|---|---|
| `0bda:2838` | Realtek RTL2838 **RTL-SDR** (rtl_433 / 433 MHz sensors / Linky) |
| `0b05:190e` | ASUS — Bluetooth or second SDR/Zigbee dongle |

These must be **physically moved** to the new server. After moving, `lsusb` to confirm
both enumerate, then start the VM. The `usb1:`/`usb2:` lines in `103.conf` reference
them by `vendor:product`, so as long as the same dongles are plugged in, no config
change is needed. If you have other identical dongles, pin by USB path instead.

## 4. RAM is no longer the constraint — VRAM is

The Gen8 was swapping (18.5 G committed / 16 G). With 32 G that's gone. The new limit
is the **3060's 12 GB VRAM**, shared by Frigate + TTS + Ollama. Budget:
~Frigate 1–2 G + Whisper/Piper 1–2 G + Ollama 7–8B ≈ 6 G → fits, but don't load a
13B+ model without checking `nvidia-smi` headroom under real load.

## 5. mdadm array must persist across reboot

After the array assembles on the new host, write it to config or it may come up with a
different name (`md127`) on next boot:

```bash
mdadm --detail --scan >> /etc/mdadm/mdadm.conf
update-initramfs -u
```

Then confirm `dd-nas`'s `scsi1` path still matches `/dev/md0` after a reboot.

## 6. Don't touch the Samsung 980

It's earmarked for the **future NAS**, not this build. The new server's VM storage is
the dedicated 1 TB SSD. Keep the 980 out of `prox2`.
