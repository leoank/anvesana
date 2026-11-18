---
id: EXP-20261118-ejmvrd
type: experiment
schema_version: 1
title: "Does native Linux (curiosity, NixOS) match Windows on the compute suite: CPU, GPU, tensor cores, cuBLASLt and TensorRT for RTX?"
project: PRJ-0001
status: active            # planned | active | paused | concluded | abandoned
outcome: null             # null | positive | negative | inconclusive | infra
influenced_by: [EXP-20261104-ssfv1c, EXP-20261104-ssfqvw]
created: 2026-11-18
author: agent:claude
review: pending
protocols: []
materials: []
tags: [phase-5, benchmarks, linux, windows, gpu, cpu]
---

## Question

Phase 5 ([[PHS-20261118-eazdzb]]): with Linux working on bbaum-pc-7 (curiosity, NixOS from the
curiosity-live ISO: kernel 7.0.14-1022-nvidia, open driver 615.78.08), does the compute suite
match the Windows baseline (`baselines/bbaum-pc-7/windows.json`, 2026-10-29: driver 621.01,
Windows power mode Best performance, AC)? The RTX Spark replication compared llama.cpp only
([[EXP-20261104-ssfv1c]]); this covers CPU, GPU memory and ALUs, tensor cores, cuBLASLt GEMM and
TensorRT for RTX, plus the Linux-only full TensorRT and CUTLASS for the record.

## Hypothesis and predictions
H1: Linux is at least as fast as Windows on the GPU. On AC Linux decoded 7-12 % faster at
2.52-2.56 GHz against Windows' 2.32-2.39 GHz ([[EXP-20261104-ssfv1c]]). If true, `gpu.*`,
`tensor.*`, `cublaslt.*` and `tensorrt_rtx.*` are within the health tolerances (5-8 %) of
Windows or above, with SM clocks at or above Windows'; if false, some are lower at the same or
lower clocks, which points at the driver or libraries rather than power.

H2: the CPU matches Windows under the performance profile (CPPC autonomous mode, energy
preference 0). If false, `cpu.*` is lower, and the CPU frequency setup on Linux is next.

## Plan
1. `nix develop` (the flake's dev shell, uv on Nix's Python 3.12), `bench setup`, then
   `bench run --skip disk,llm` on AC with the performance power profile ([[RUN-20261118-ejmvy1]]).
2. `bench compare bbaum-pc-7@baseline:windows` the run; read clocks, power and temperatures per
   benchmark next to the metrics.
3. Curate the run into `data/curated_runs/bbaum-pc-7/`; promoting it to the Linux baseline is
   Ank's call.

## Success criteria

A complete Linux run with every benchmark's metrics and telemetry, and a comparison against
the Windows baseline that says, metric by metric, which way and by how much, with the clocks and
power behind each difference.

## Runs
One line per run after its link, what was tried and what it showed; `yajna validate`
rejects a bare link here. Metric runs also land in results.tsv.
- [[RUN-20261118-ejmvy1]] first Linux run against the Windows baseline: tensor and gpu within 3 %, cuBLASLt 7-13 % slower at a ~51 W power cap (Windows ~61 W), TensorRT for RTX 14-27 % faster, CPU math 9-12 % slower; full TensorRT and CUTLASS failed (API, cmake on NixOS)
- [[RUN-20261118-g2tm8p]] compute run, not yet described
- [[RUN-20261118-g2z7h4]] CPU probes: big cores hold 4.0 GHz; cpu.math is mostly glibc sin/cos (~75 % of the loop); fp64_gemm on 20 threads is paced by the A725s (397 vs 533 GFLOPS on the X925s alone); H2 false for the CPU, but for the C library and the benchmark, not the CPU

## Conclusion
Written once, by a human, when status becomes `concluded`.
