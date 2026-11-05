---
id: EXP-20261104-ssfqvw
type: experiment
schema_version: 1
title: "Windows baseline: GPT-OSS decode speed and GPU clock on AC and battery, with NVPCF on and off"
project: PRJ-0001
status: planned           # planned | active | paused | concluded | abandoned
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

## Conclusion
Written once, by a human, when status becomes `concluded`.
