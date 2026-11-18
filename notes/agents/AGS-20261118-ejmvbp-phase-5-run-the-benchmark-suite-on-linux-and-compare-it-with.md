---
id: AGS-20261118-ejmvbp
type: agent_session
schema_version: 1
title: "Phase 5: run the benchmark suite on Linux and compare it with the Windows baseline"
model: claude-opus-5-5
harness: claude-code
started: 2026-11-18T13:16+00:00
finished: 2026-11-18T13:32+00:00
created_entities: [EXP-20261118-ejmvrd, RUN-20261118-ejmvy1]
edited_entities: [PHS-20261118-eazdzb]
outcome: done             # done | failed | aborted | pending
created: 2026-11-18
author: agent:claude
---

## Task

Ank asked to start the benchmarks on Linux (phase 5, [[PHS-20261118-eazdzb]]) and compare them
with the Windows results. Ank chose: every benchmark but disk and llm, the performance power
profile, and the run curated into the repo.

## What happened

The suite's GPU benchmarks need the `nvidia`, `tensorrt` and `cutlass` extras (pip wheels via
uv); curiosity has no uv or nix-ld and the flake had no dev shell. Added
`devShells.aarch64-linux.default`: uv on Nix's Python 3.12, `LD_LIBRARY_PATH` with
`/run/opengl-driver/lib` (libcuda, NVML) and libstdc++/zlib. `bench setup` installed everything
and reported all nine benchmarks ready; a 3 s `bench gpu` gave 120 TFLOPS FP16 MMA at 2.55 GHz.
Opened [[EXP-20261118-ejmvrd]] and started [[RUN-20261118-ejmvy1]].

The run came back partial (full TensorRT: an RTX-only API call; CUTLASS: the pip `cmake` will
not run on NixOS) and `set -e` stopped the script before the compare; ran the compare by hand
and made the script go on after a partial run. Findings in [[RUN-20261118-ejmvy1]]: tensor and
gpu match Windows within 3 %; cuBLASLt is 7-13 % slower because the GPU's sustained power cap is
~51 W on Linux against ~61 W (both runs at NVML's software power cap); TensorRT for RTX is
14-27 % faster at higher clocks; CPU math is 9-12 % slower for a reason not found yet. Curated
the run into `data/curated_runs/` (user name in paths replaced). Not done: fixing full TensorRT
and CUTLASS, the CPU cause, the GPU power budget (phase 6: the MSI mode from Linux), promoting a
Linux baseline (Ank's call).
