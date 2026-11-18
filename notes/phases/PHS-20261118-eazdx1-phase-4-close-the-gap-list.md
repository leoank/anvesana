---
id: PHS-20261118-eazdx1
type: phase
schema_version: 1
title: Phase 4 Close the gap list
project: PRJ-0001
status: active
since: null               # the commit it started at: yajna phase start
until: null               # the commit it finished at: yajna phase done
created: 2026-11-18
author: agent:claude
tags: []
---

## Goal

Drivers, firmware and quirks for each GAP / MISSING, controllers before the devices behind them, up to NixOS as the daily driver on bbaum-pc-7 (`nixosModules.n1x`, `n1x-desktop`). Checked by `inventory compare` exiting 0 for the SoC blocks.

## Progress
One item per piece of work, ticked when it lands; add items as the plan grows and keep the
done ones. The project page's *Progress* lists this phase on one line.
- [ ] Gap list `compare bbaum-pc-7@windows bbaum-pc-7@linux`, SoC controllers first (phase 4)
- [x] nvidia-drm display with the ProArt fixes, and N1X hardware support as `nixosModules.n1x` (ADR-0017)
- [x] Sensor hub on Linux: accelerometers, light and orientation through iio-sensor-proxy ([[EXP-20261113-0c42xp]])
- [ ] Tablet mode from the hinge angle: a SW_TABLET_MODE bridge for GNOME ([[EXP-20261117-sm6c0e]])
- [ ] Installed NixOS as the daily driver on bbaum-pc-7: audio, keyboard backlight (Fn + F8), Wi-Fi, suspend; the ProArt audio and keyboard parts are ASUS-specific

## Notes
Migrated from PRJ-0001's Progress by `yajna phase migrate`.
