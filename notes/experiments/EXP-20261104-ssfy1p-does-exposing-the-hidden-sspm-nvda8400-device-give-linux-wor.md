---
id: EXP-20261104-ssfy1p
type: experiment
schema_version: 1
title: Does exposing the hidden SSPM (NVDA8400) device give Linux working GPU power management?
project: PRJ-0001
status: planned           # planned | active | paused | concluded | abandoned
outcome: null             # null | positive | negative | inconclusive | infra
influenced_by: []
created: 2026-11-04
author: agent:claude
protocols: []
materials: []
tags: [llm, nixos, acpi, sspm, rtx-spark-replication]
review: pending
---

## Question
The DSDT hides `\_SB.SSPM` (NVDA8400) from any OS answering `_OSI("Windows 2022")`, which
Linux does too if it claims Windows 2022 (checked in [[EXP-20261104-ssfn9a]]). If Linux sees it, does a driver bind, and do the AC clocks come back?

## Hypothesis and predictions
H1: SSPM is the non-Windows counterpart of NVPCF. If true, on the `sspm` entry the device is
present, a driver (or firmware path) binds, and `nixos-sspm-ac` clocks rise well above
780 MHz. If false, the device is present but unbound, or the clocks match `nixos-default-ac`.
The `osi` entry exposes all five hidden devices; comparing it separates SSPM's effect from the
others'.

## Plan
1. Build the override (`scripts/acpi-hidden-devices.py --expose SSPM`, 20 bytes changed,
   checksum valid) and the image with the `sspm` entry.
2. Boot `sspm`: check the override loaded (dmesg "Table Upgrade"), `NVDA8400` status and
   driver, `bench inventory collect`, `llm-conditions.py --label nixos-sspm`.
3. Boot `osi`: same, `--label nixos-osi`.

## Success criteria
Device status and binding for SSPM in both entries, and AC/battery runs comparable with [[EXP-20261104-ssfv1c]].

## Runs
One line per run after its link, what was tried and what it showed; `yajna validate`
rejects a bare link here. Metric runs also land in results.tsv.

## Conclusion
Written once, by a human, when status becomes `concluded`.
