# Curated runs: RTX Spark replication (bbaum-pc-7)

Runs from the results store (`$ANVESANA_RESULTS_DIR`) that the claims in
[docs/rtx-spark-replication.md](../../docs/rtx-spark-replication.md) rest on, copied unchanged
except that local user names in paths are replaced with `<user>`. Each run directory holds
`run.json` (settings, environment, metrics), `telemetry.csv` and `run.log`; compare any two with
`bench compare <run> <run>` after pointing `ANVESANA_RESULTS_DIR` here.

Left out: two partial runs (2026-11-05_011806, an aborted first attempt; 2026-11-06_041652, WSL
llama.cpp falling back to the CPU before the cudart fix).

Tags: `<os setup>-npcf-<on|off>-<MSI mode>-[compute-]<ac|dc>`. MSI modes: eco = ECO-Silent,
balanced, perf = Performance, boost = Performance Boost. `compute` runs are the GPU compute
suite (cuBLASLt GEMM, memory bandwidth); the others are `bench llm` (llama.cpp b12119,
GPT-OSS MXFP4, pp512 / tg128).

| Group | Runs | Claim |
|---|---|---|
| First baseline, before the replication | `2026-10-29_152707_windows` | |
| Windows, NPCF on, 20B by MSI mode, AC and battery | `2026-11-05_012311` ... `022118` | C1, C3 |
| Windows, NPCF on, compute by MSI mode, AC and battery | `*-compute-ac`, `*-compute-dc` | C2, C3 |
| Windows, NPCF on, 120B, Performance Boost | `2026-11-06_030249` (AC), `035334` (battery) | C1 |
| WSL, 20B and 120B, Performance Boost, AC | `2026-11-06_042227_linux_wsl-*` | C5 |
| Windows, NPCF disabled without a reboot | `2026-11-06_213745` | C4 |
| Windows, NPCF disabled after a reboot | `2026-11-06_214733`, `215004` (AC), `220238`, `220416` (battery) | C4 |
| Windows, NPCF re-enabled, check | `2026-11-06_221940` | C4 |
| vLLM in WSL, gpt-oss-20b, 8 clients and 1 client | `concurrency/` | C5 |
| State changes (restore points, NPCF, MSI modes) and the preflight | `bbaum-pc-7/state/` | |

Headline numbers (Performance Boost, tok/s, pp512 / tg128):

| | AC | Battery |
|---|---|---|
| 120B, NPCF on | 2,198 / 63.5 | 1,874 / 61.1 |
| 120B, NPCF off (rebooted) | 2,139 / 64.0 | 1,887 / 61.7 |
| 120B, WSL | 2,233 / 61.5 | |
| 20B, NPCF on | 5,259 / 78.4 | 4,515 / 82.5 |
| 20B, NPCF off (rebooted) | 5,484 / 88.7 | 4,563 / 86.1 |
| 20B, WSL | 5,313 / 85.4 | |

vLLM in WSL: 302 tok/s aggregate with 8 clients, 58.7 tok/s with one.
