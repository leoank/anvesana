---
id: AGS-20261107-k1ae4y
type: agent_session
schema_version: 1
title: NixOS daily-driver live image (GNOME) with boot-log collection
model: claude-opus-5-5
harness: claude-code
started: 2026-11-07T17:19+00:00
finished: null
created_entities: []
edited_entities: []
outcome: pending          # done | failed | aborted | pending
created: 2026-11-07
author: agent:claude
---

## Task

Ank asked for a minimal NixOS daily-driver image for bbaum-pc-7, still only a live image, to try
out what works on the laptop. Every boot's logs must be collectable and handed back for analysis.
Then: boot it in QEMU and check that log collection works there and that the early boot output
on screen can be seen. Ank chose GNOME (touch, pen, tablet mode).

## What happened
- Split the shared parts of the benchmark live image into `nix/live-common.nix` (N1X module,
  initrd diagnostics, SPARKDATA automount, repo and `bench`); `nix/live.nix` keeps only the
  benchmark parts.
- `nix/desktop-live.nix` (`.#rtx-spark-desktop`): the nixos-26.05 GNOME installer profile without
  Plymouth or VM guest agents, Bluetooth and iio-sensor-proxy on. Entries: default (SSPM override
  when built with it, else `acpi_osi`), `osi`, `safe-graphics` (simpledrm), `serial` (ttyAMA0).
- `nix/anvesana-collect.sh`: journal + dmesg into `SPARKDATA/bootlogs/<host>/<boot>/`, and a full
  snapshot (`summary.txt` with OK / MISSING per feature, one file per subsystem, `bench inventory
  collect`). Runs 2 min after boot, every 5 min (journal), after resume, at shutdown, and from a
  "Collect logs" app. Decided without asking: SPARKDATA as the destination (it is already on
  every boot), RAM fallback in /var/log/anvesana.
- `scripts/vm-test.sh`: QEMU (TCG, no KVM in WSL) with a blank SPARKDATA disk, the ISO's `serial`
  entry, serial log, a screenshot every 10 s, a power-button shutdown, then the disk's contents.
- First VM run: nothing reached SPARKDATA (collector output only in the VM's journal) and the
  screenshot command never reached QEMU. Second run, with an explicit mount and console output:
  boot, periodic and shutdown collections all landed. Remaining bugs (no hostname in the path,
  `bench` not on PATH, accelerometer false positive, PNG screendump rejected by QEMU 10) fixed for
  the third run.
- Third run (serial entry): folder `bootlogs/bbaum-pc-7/<boot>_sspm-serial_<id>/`, boot snapshot
  with `bench inventory`, journal every 5 min, shutdown copy; 21 distinct screens. GNOME's desktop
  appeared about 7 min after boot under TCG, then blanked after its 5-min idle default.
- The screen showed only warnings: NixOS appends `loglevel=4` (boot.consoleLogLevel) after our
  `loglevel=7`. Now `boot.consoleLogLevel = 7`; the fourth run's screens show kernel lines and
  systemd's status lines together. "Collect logs" pinned first in the dash.
- GNOME intercepts the VM's power button and asks, so a test could not end cleanly. Added a
  test-only `anvesana.vmtest_poweroff=<s>` kernel parameter (unit skipped without it). Fifth run:
  self power-off after 600 s, shutdown collection written, 51 files on the data disk, fsck clean.
- Seen in the VM, also expected on the laptop: a 90 s non-blocking wait for a serial login on
  ttyAMA0 (the kernel adds the SPCR console; the laptop has an SPCR table too).
- ISO 2484c6ca (sspm default) copied to `C:\Users\<user>\anvesana-rtx-spark-desktop-2484c6ca.iso`,
  hash checked.
- First laptop boots (ISO 2484c6ca, `sspm` entry, twice, 19:32 and 19:45): GNOME unusably laggy,
  minutes from the login screen to the desktop; both ended in forced restarts. From the logs on
  SPARKDATA (`bootlogs/bbaum-pc-7/2026-11-07_193219_sspm_1a8b13b8`, `..._194531_sspm_46431b2d`):
  - Works: SSPM bound, GPU (nvidia-smi), eDP panel and `nvidia_0` backlight, keyboard
    (MKB0001), touchpad (SYNA1513), touchscreen and pen (ELAN9024), Wi-Fi device (MT7925,
    `wlP6s6`), Bluetooth `hci0`, four `/dev/video*`, battery, cppc_cpufreq, two ALSA cards
    (NVIDIA HDA, mt8901-soundwire), `deep` listed in mem_sleep.
  - Missing or broken: keyboard backlight LED, accelerometer and ambient light (only a proximity
    IIO device), NetworkManager cannot start wpa_supplicant ("Failed to D-Bus activate").
  - GNOME: the autologin session (uid 1000, Wayland) started at 19:32:42, 20 s after boot; mutter
    reported `Created gbm renderer for /dev/dri/card1` (nvidia-drm), `Obtained a high priority
    EGL context`, and `Device '/dev/dri/card1' prefers shadow buffer`. No flip timeouts, Xid or
    stall messages in the kernel log. So the session was up long before the screen showed it.
  - The collector's in-session probes (EGL/Vulkan/GLX renderer, audio sinks, sensor proxy) ran
    with no user: `getent` is not on the script's PATH. Fixed; the collector now also records,
    at every collection, top CPU users, `nvidia-smi dmon` for 5 s and the GL/EGL libraries mapped
    into gnome-shell and Xwayland, plus the KMS debugfs state in full snapshots.
  - ProArt comparison: same driver tuple and nvidia_drm options; its `libnvidia-rmapi-tegra`
    fix is already in nixpkgs' nvidia-x11; it documents no desktop.
- Laptop A/B, ISO 70c366cf (2026-11-07 22:35 to 2026-11-08 00:16): `sspm` and `osi` (both
  `nvidia_drm vblank=1`) lagged as before; `sspm, nvidia_drm without vblank=1` ran smoothly.
  Both had GNOME on NVIDIA GL (gnome-shell holds /dev/nvidia0; EGL/GL/Vulkan renderer "NVIDIA RTX
  Spark N1X"); the only difference was /sys/module/nvidia_drm/parameters/vblank Y vs N. So the
  ProArt tuple's vblank=1 stalls page flips on this panel (3840x2400@120, VRR OLED). Now off by
  default (`n1x.nvidiaVblank = false`).
- Working on that boot: Wi-Fi connected (wpa_supplicant fix), Bluetooth, keyboard, touchpad,
  touchscreen and pen, panel backlight, camera devices, battery, CPU scaling; Firefox WebGL on
  NVIDIA at 3840x2400@120 scale 2 (Ank's about:support and screenshot on SPARKDATA).
- Not working:
  - Sound: SoundWire is up (2x RT1320 uid 0/1 on link 0, RT712 on link 1) and the ALSA card
    `mt8901-soundwire` exists, but alsa-ucm-conf 1.2.15.3 has no profile ("no backend DAIs enabled
    for DL0_FE"), so PipeWire shows only a dummy output. NVIDIA's open alsa-ucm-conf PR 862 has a
    board-validated profile for exactly this topology (HiFi-rt1320x2-rt712.conf); added pinned at
    7d3555a through ALSA_CONFIG_UCM2 (`n1x.alsaUcm2`), no rebuild of alsa-lib users.
  - Accelerometer / light sensor: the sensor hub MSFW1111 (`\_SB.SENH`) is HID over SPI and has
    no driver; the kernel config has hid-sensor-hub and accel_3d but no HID-over-SPI transport.
    The only IIO device is the webcam's presence sensor. Needs an out-of-tree or backported driver.
  - Keyboard backlight: no LED class device (EC-driven on Windows).
  - Hardware video decode in Firefox (no VA-API driver for NVIDIA).
