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
