---
id: EXP-20261104-ssfy1p
type: experiment
schema_version: 1
title: Does exposing the hidden SSPM (NVDA8400) device give Linux working GPU power management?
project: PRJ-0001
status: active            # planned | active | paused | concluded | abandoned
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

## Results
Added 2026-11-07 (agent:claude). `sspm` entry: the DSDT override from
`scripts/acpi-hidden-devices.py --expose SSPM`, prepended to the initrd. It works only from a stick
written directly: Ventoy's injected initramfs hid the override, and SSPM stayed at `_STA=0`.

- SSPM is present and bound: `NVDA8400:00: _STA=15 driver=SSPM_CI`, `SSPM_CI_SET IRQ = 39`,
  `SSPM_CI_GET IRQ = 40`, `ACPI: Table Upgrade: override [DSDT-  NVDA-ANGUS   ]`. Only NVDA8400 of
  the five hidden devices is exposed (inventory 2026-11-07_073440_linux).
- What SSPM does on Linux: it is the SCMI endpoint NVIDIA's kernel uses to power the SoC's USB,
  I2C, SPI, DSP and PCIe controllers (75 devices in `PEPD`'s DPMT). Without it Linux cannot boot
  from USB at all ([[EXP-20261104-ssfv1c]]).
- GPU, 4 GB reservation, Performance Boost set from Windows:

| NixOS `sspm` | 20B AC | 20B battery | 120B AC | 120B battery |
|---|---|---|---|---|
| tok/s pp512 / tg128 | 5,344 / 93.2 | 4,802 / 89.2 | 2,132 / 65.6 | 1,872 / 63.5 |

  The same as `osi` within noise (2.53–2.55 GHz on AC, 1.89 GHz on battery). The other four
  hidden devices make no difference to inference.
- H1 as phrased (SSPM restores AC clocks lost without it) cannot be tested: there was no low-clock
  state to restore, because without SSPM Linux does not boot.

## Conclusion
Written once, by a human, when status becomes `concluded`.
