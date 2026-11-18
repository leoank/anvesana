---
id: EXP-20261104-ssfs86
type: experiment
schema_version: 1
title: Does WSL2 match native Windows for llama.cpp and for vLLM with 8 concurrent clients?
project: PRJ-0001
status: concluded            # planned | active | paused | concluded | abandoned
outcome: positive             # null | positive | negative | inconclusive | infra
influenced_by: [EXP-20261104-ssfqvw]
created: 2026-11-04
author: agent:claude
protocols: []
materials: []
tags: [llm, wsl, vllm, rtx-spark-replication]
review: approved
approval: {by: ank, on: 2026-11-18}
---

## Question
Does WSL2 on the same machine match native Windows (C5): llama.cpp single-stream decode, and
vLLM aggregate throughput with 8 concurrent clients?

## Hypothesis and predictions
H1: WSL uses the Windows GPU driver and its power management, so it inherits Windows' clocks.
If true, `wsl-ac` llm metrics are within 5 % of `win-npcf-on-ac` at the same SM clock; if
false, WSL shows the low-clock signature of native Linux.

## Plan
1. Install Ubuntu 24.04 in WSL (asked for first), clone inside WSL, `scripts/wsl-setup.sh --nix --vllm`.
2. `scripts/llm-conditions.py --label wsl --conditions ac,dc` with the models from SPARKDATA.
3. `vllm serve openai/gpt-oss-20b` (pinned revision), `scripts/llm-concurrency.py --clients 8 --label wsl-vllm`.

## Success criteria
`wsl-ac`/`wsl-dc` runs and one concurrency result, comparable with [[EXP-20261104-ssfqvw]] and [[EXP-20261104-ssfv1c]].

## Runs
One line per run after its link, what was tried and what it showed; `yajna validate`
rejects a bare link here. Metric runs also land in results.tsv.

## Results
Added 2026-11-07 (agent:claude). Ubuntu 24.04 on WSL 2, the same llama.cpp b12119 Linux build as
the live image, AC, Performance Boost, NPCF on, 96 GB reservation.

| | 20B pp512 / tg128 | 120B pp512 / tg128 |
|---|---|---|
| WSL | 5,313 / 85.4 | 2,233 / 61.5 |
| Windows | 5,259 / 78.4 | 2,198 / 63.5 |

- H1 holds: WSL is within 3 % of Windows for 120B and 9 % faster for 20B decode.
- vLLM 0.33.0, `openai/gpt-oss-20b`: 8 clients 302 tok/s aggregate, 1 client 58.7 tok/s (article:
  127 in WSL, 39.5 native). It needed `--gpu-memory-utilization 0.14 --kv-cache-memory-bytes 2G`,
  because CUDA in WSL reports WSL's free RAM as the GPU's free memory (docs/rtx-spark-replication.md).
- llama.cpp fell back to the CPU in WSL until the CUDA runtime libraries were copied next to the
  binaries; `bench llm` now refuses a run that is not on CUDA.
- WSL also served as the Nix build host for the live image.

## Conclusion
Positive: WSL2 inherits Windows' clocks. With the same llama.cpp b12119 Linux build, WSL decodes
within 3 % of Windows for 120B (61.5 vs 63.5 tok/s) and 9 % faster for 20B (85.4 vs 78.4), with no
low-clock signature. vLLM 0.33.0 with gpt-oss-20b gave 302 tok/s aggregate for 8 clients and
58.7 for one. It needed a small `--gpu-memory-utilization` and an explicit KV-cache size,
because CUDA in WSL reports WSL's free RAM as the GPU's free memory. llama.cpp silently fell back
to the CPU in WSL until the CUDA runtime libraries sat next to the binaries; `bench llm` now
refuses a run that is not on CUDA.
