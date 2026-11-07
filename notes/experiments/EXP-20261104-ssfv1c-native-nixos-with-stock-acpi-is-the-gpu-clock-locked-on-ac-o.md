---
id: EXP-20261104-ssfv1c
type: experiment
schema_version: 1
title: "Native NixOS with stock ACPI: is the GPU clock locked on AC only, and how much memory does Linux get?"
project: PRJ-0001
status: active            # planned | active | paused | concluded | abandoned
outcome: null             # null | positive | negative | inconclusive | infra
influenced_by: []
created: 2026-11-04
author: agent:claude
protocols: []
materials: []
tags: [llm, nixos, linux, rtx-spark-replication]
review: pending
---

## Question
On the NixOS live image (NV-Kernels 7.0.14-1022, driver 615.78.08 open, stock ACPI tables), is
the GPU clock locked low on AC and not on battery (C1, C2, C3), and how much memory do Linux
and CUDA see with the default 96 GB reservation and with a smaller one (C6)?

## Hypothesis and predictions
H1 (the article): without the Windows NVPCF driver the GPU falls back to a conservative AC
budget. If true, `nixos-default-ac` runs near 780 MHz SM at about a fifth to a third of the
Windows decode rate, `nixos-default-dc` near 1.8 GHz and close to Windows, below 50 °C in both.
If false, AC and battery runs are within tolerance of each other.

H2: the GPU reservation is a firmware carve-out that Linux cannot reclaim. If true, with 96 GB
reserved Linux sees about 28–32 GB of system RAM; the ProArt P16 (91 GiB reserved on Windows)
showed 116 GiB as both RAM and CUDA memory on Linux, which would contradict it.

## Plan
1. Gates 2–3 of the guide (BitLocker key stored, suspend), Secure Boot off.
2. Boot the default entry; `bench inventory collect`; `free -g`, `nvidia-smi -q -d MEMORY,PERFORMANCE,CLOCK,POWER`.
3. `llm-conditions.py --label nixos-default --conditions ac,dc` (20B; 120B if memory allows).
4. If memory blocks 120B: lower the reservation in the NVIDIA app, repeat the memory check, set it back.

## Success criteria
`nixos-default-ac`/`-dc` runs with clocks, power, temperature and throttle bits; memory
seen by Linux and CUDA at each reservation; an inventory snapshot for the Linux gap list.

## Runs
One line per run after its link, what was tried and what it showed; `yajna validate`
rejects a bare link here. Metric runs also land in results.tsv.

## Results
Added 2026-11-07 (agent:claude). Live image: NV-Kernels 7.0.14-1022, driver 615.78.08 (open).
Boot details and console transcripts: `data/boot-logs/2026-11-06-nixos-default-no-usb.md`.

- **The stock-ACPI condition cannot be run on this machine.** With the stock tables Linux has no
  USB and no I2C (keyboard, touchpad): every xHCI and I2C controller is powered through the
  `power_wrap` driver, which asks SSPM over SCMI, and SSPM (NVDA8400) is hidden from any OS that
  claims `_OSI("Windows 2022")`, as Linux does. The boot stick is never found. The closest
  conditions are the `osi` entry (`acpi_osi="!Windows 2022"`) and `sspm` ([[EXP-20261104-ssfy1p]]).
- H1 is not supported. `osi` entry, Performance Boost set from Windows, models on a USB drive:

| NixOS `osi` | 20B AC | 20B battery | 120B AC | 120B battery |
|---|---|---|---|---|
| 96 GB reservation | 5,311 / 92.4 | | out of memory | |
| 4 GB reservation | 5,355 / 93.4 | 4,779 / 89.2 | 2,133 / 65.7 | 1,887 / 63.4 |

  Decode ran at 2.52–2.56 GHz and 52 W on AC, 1.89–1.90 GHz and 22 W on battery, below 60 °C.
  Linux decodes 7–12 % faster than Windows at the same reservation; no 780 MHz lock on AC.
- H2 holds: with 96 GB reserved Linux sees 30.36 GB of RAM (inventory 2026-11-07_013207_linux),
  and loading the 59 GiB 120B model ran the machine out of memory (it hung). With the reservation
  lowered to 4 GB in the NVIDIA app, Linux sees 128.9 GB (120 GiB) and runs 120B. CUDA memory
  was not read separately; llama.cpp's allocation of 120B shows it reaches beyond 59 GiB.
- `nvidia-drm` drives the console (`fb0: nvidia-drmdrmfb`); there is no desktop on this image.
- Each NixOS run took about 80 minutes, almost all model loading from the USB drive; that does not
  enter tok/s.

## Conclusion
Written once, by a human, when status becomes `concluded`.
