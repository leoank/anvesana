---
id: EXP-20261104-ssfn9a
type: experiment
schema_version: 1
title: Is NVPCF's power data really opaque, and which ACPI devices does the firmware hide from Linux?
project: PRJ-0001
status: active            # planned | active | paused | concluded | abandoned
outcome: null             # null | positive | negative | inconclusive | infra
influenced_by: []
created: 2026-11-04
author: agent:claude
protocols: []
materials: []
tags: [nvpcf, acpi, rtx-spark-replication]
review: pending
---

## Question
Claim C7 (docs/rtx-spark-replication.md): NVIDIA Platform Controllers and Framework's power
table is encrypted and only the Windows driver can use it. What does the firmware itself give
an OS: what do `\_SB.NPCF` (NVDA0820) and its methods return, and which devices are hidden
from an OS that answers `_OSI("Windows 2022")`?

## Hypothesis and predictions
H1: the platform's power limits are plain ACPI data (NPCF `_DSM` packages), readable by any
OS; only the Windows driver's *use* of them (dynamic CPU/GPU power sharing) is missing on
Linux. If H1 holds, the disassembled NPCF methods return power-limit tables in clear; if false,
they return only an opaque blob that the driver decrypts.

H2: the five devices whose `_STA` returns 0 under `_OSI("Windows 2022")` (SVP0 NVDA3000,
SSPM NVDA8400, HFRP MTK00055, NH1X NVDA300A, NMAP NVDA300B) are meant for non-Windows OSes, and
Linux hides them only because it claims Windows 2022. Predicted: on the live image's default
entry none of them is present; with `acpi_osi="!Windows 2022"` all five are.

## Plan
1. Disassemble the DSDT/SSDTs from the 2026-10-30 inventory snapshot with `iasl` (WSL or the
   live image); extract `\_SB.NPCF` and the five devices' methods into the log.
2. Note whether NPCF `_DSM` returns structured packages (limits, tables) or a raw buffer.
3. Check H2 on the live image: `/sys/bus/acpi/devices` on the default and osi entries.

## Success criteria
A disassembly excerpt of NPCF and each hidden device in the log, and the device lists from
both boot entries; enough to say whether "encrypted" applies to the firmware data or only to
the driver.

## Runs
One line per run after its link, what was tried and what it showed; `yajna validate`
rejects a bare link here. Metric runs also land in results.tsv.

## Results
Added 2026-11-07 (agent:claude); partial, H1 not worked on yet.

- H2 holds on the live image:
  - stock tables (`default` and the `sspm` entry booted through Ventoy): `NVDA8400:00: _STA=0`, so
    Linux answers `_OSI("Windows 2022")` true;
  - `acpi_osi="!Windows 2022"` (`osi`): all five hidden devices are present (NVDA3000, NVDA8400,
    MTK00055, NVDA300A, NVDA300B in inventory 2026-11-07_013207_linux);
  - DSDT override (`sspm`): only NVDA8400 (inventory 2026-11-07_073440_linux).
- SSPM is not optional for Linux on this machine: see [[EXP-20261104-ssfy1p]].
- H1 (NPCF's tables in clear or opaque) is open: the NPCF methods have not been disassembled. The
  NPCF-off runs in [[EXP-20261104-ssfqvw]] show the Windows driver does not set the clocks
  measured here.

## Conclusion
Written once, by a human, when status becomes `concluded`.
