---
id: EXP-20261104-ssfv1c
type: experiment
schema_version: 1
title: "Native NixOS with stock ACPI: is the GPU clock locked on AC only, and how much memory does Linux get?"
project: PRJ-0001
status: planned           # planned | active | paused | concluded | abandoned
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

## Conclusion
Written once, by a human, when status becomes `concluded`.
