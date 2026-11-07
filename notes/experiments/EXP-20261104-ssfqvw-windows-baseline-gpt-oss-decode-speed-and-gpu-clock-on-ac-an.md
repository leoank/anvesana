---
id: EXP-20261104-ssfqvw
type: experiment
schema_version: 1
title: "Windows baseline: GPT-OSS decode speed and GPU clock on AC and battery, with NVPCF on and off"
project: PRJ-0001
status: active            # planned | active | paused | concluded | abandoned
outcome: null             # null | positive | negative | inconclusive | infra
influenced_by: []
created: 2026-11-04
author: agent:claude
protocols: []
materials: []
tags: [llm, nvpcf, windows, rtx-spark-replication]
review: pending
---

## Question
On Windows, what do GPT-OSS-20B and 120B decode at, and at what GPU clock, on AC and on
battery; and does disabling the NVPCF device reproduce the article's Linux slowdown (C1
Windows side, C3, C4)?

## Hypothesis and predictions
H1: NVPCF sets the GPU's power/clock budget on Windows. If true, `win-npcf-off-ac` drops to
about 790 MHz SM and roughly a third of `win-npcf-on-ac` decode tok/s, with NVML reporting a
power or software clock-event reason and the GPU below 50 °C; if false, the two runs are within
the health tolerance.

## Plan
1. Elevated `scripts/rtx-spark-preflight.ps1`; record the verdicts.
2. `scripts/llm-fetch.py` for llama.cpp b12119 and both models (sha256 checked).
3. `scripts/llm-conditions.py --label win-npcf-on --conditions ac,dc`.
4. `rtx-spark-state.ps1 restore-point`, `npcf-disable`, reboot; `--label win-npcf-off`.
5. `npcf-enable`, reboot, `rtx-spark-state.ps1 status` shows NPCF OK.

## Success criteria
Four tagged runs (npcf on/off × AC/battery) with `llm.*` metrics, avg SM clock, temperature
and throttle bits; NPCF back to OK in the journal.

## Runs
One line per run after its link, what was tried and what it showed; `yajna validate`
rejects a bare link here. Metric runs also land in results.tsv.

## Results
Added 2026-11-07 (agent:claude). All runs are in `data/curated_runs/` (index in its README);
llama.cpp b12119, flash attention, pp512 / tg128, 5 reps. "Boost" = MSI Performance Boost.

| GPT-OSS, Boost | 20B AC | 20B battery | 120B AC | 120B battery |
|---|---|---|---|---|
| NPCF on, 96 GB reservation | 5,259 / 78.4 | 4,515 / 82.5 | 2,198 / 63.5 | 1,874 / 61.1 |
| NPCF off, rebooted | 5,484 / 88.7 | 4,563 / 86.1 | 2,139 / 64.0 | 1,887 / 61.7 |
| NPCF off, live (no reboot) | 5,464 / 89.4 | | | |
| NPCF on again (check) | 5,352 / 87.3 | | | |
| NPCF on, 4 GB reservation | 5,345 / 84.3 | 4,598 / 82.0 | 2,112 / 58.5 | 1,829 / 57.2 |

- Decode SM clock with NPCF off: 2.32–2.39 GHz on AC (47–48 W), 1.96–2.04 GHz on battery
  (24–25 W), the same as with NPCF on. Temperatures stayed below 65 °C.
- H1 is not supported: disabling `ACPI\NVDA0820\NPCF`, live or across a reboot, changes neither
  the clock nor tok/s. The article's 83 → 31 tok/s and 2 GHz → 786 MHz did not appear.
- The 120B AC number (63.5 tok/s) matches the article's Windows figure (65.4).
- MSI modes move compute (cuBLASLt fp16 41 / 61 / 82 / 85 TFLOPS on AC, ECO to Boost) but barely
  move decode (20B 76–85 tok/s); on battery every mode is held near 30–35 W.
- The 4 GB reservation gives Windows 122.5 GiB of RAM and costs 120B about 8 % of decode.
- NPCF was re-enabled and checked; the state journal (`data/curated_runs/bbaum-pc-7/state/`)
  records every change.

## Conclusion
Written once, by a human, when status becomes `concluded`.
