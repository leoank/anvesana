---
id: PHS-20261118-eazdsa
type: phase
schema_version: 1
title: Phase 1 Windows reference inventory
project: PRJ-0001
status: done
since: null               # the commit it started at: yajna phase start
until: null               # the commit it finished at: yajna phase done
created: 2026-11-18
author: agent:claude
tags: []
---

## Goal

`bench inventory` on Windows: devices, drivers, firmware, CPU, HID, WMI, ESRT, display, power and vendor settings, as the reference Linux is compared against. Checked by unprivileged snapshots of bbaum-pc-7 in about 50 s, and `show` listing all 32 NVIDIA ACPI devices with drivers and resources.

## Progress
One item per piece of work, ticked when it lands; add items as the plan grows and keep the
done ones. The project page's *Progress* lists this phase on one line.
- [x] `bench inventory` on Windows: devices, drivers, resources, ACPI tables, SMBIOS, CPU registers ([ADR-0001, 0002](../docs/decisions/README.md))
- [x] Cross-OS `inventory compare` with GAP / MISSING verdicts and exit code (ADR-0003, 0006)
- [x] HID collections, ACPI-WMI blocks, ESRT, opt-in firmware copies (ADR-0005, 0007)
- [x] Display (EDID, modes, HDR, brightness, colour profiles), power (sleep states, overlay, powercfg) and vendor settings
- [x] BIOS and system product in every `run.json` (ADR-0010)
- [x] Repo initialised as a yajna `project` notebook; architecture and decision records written

## Notes
Migrated from PRJ-0001's Progress by `yajna phase migrate`.
