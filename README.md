# anvesana: node health tracking

Run the same GPU / CPU / memory / disk benchmark suite on every machine on a schedule (monthly),
keep every run, and flag nodes that are getting slower, hotter or broken.

```
machines/<id>.toml        what each machine runs, its advertised specs, its health tolerances
baselines/<id>/<os>.json  the reviewed reference run per machine and OS (committed)
$ANVESANA_RESULTS_DIR/       every run: run.json + telemetry.csv + run.log (outside the repo)
```

## Setup

[uv](https://docs.astral.sh/uv/) installs Python and every dependency, including the native CUDA 13
libraries (pip wheels for `win_arm64` and `linux_aarch64`). No CUDA toolkit install is needed.

```bash
uv sync --extra tensorrt --extra cutlass
export ANVESANA_RESULTS_DIR=/shared/anvesana-results     # Windows: setx ANVESANA_RESULTS_DIR \\server\anvesana-results
```

The CUTLASS benchmark runs on Linux only and needs the system `g++`. Its first run builds NVIDIA's
`cutlass_profiler` once and caches it in `~/.cache/anvesana/cutlass`. On Windows, CUTLASS's
SM90+ kernels can't be compiled: nvcc only accepts MSVC there, and MSVC rejects their 128-byte-aligned
kernel parameters (error C2719).

## Adding a machine

```bash
uv run bench machines init dgx-01      # writes machines/dgx-01.toml with this host's name
# edit: benchmark list/args, [expected] vendor peaks, [health] tolerances
uv run bench run                       # first run
uv run bench baseline promote dgx-01@latest   # once a run looks right; commit the baseline
```

## Monthly workflow

```bash
uv run bench run --health        # run this host's profile, store it, check it; exit 1 on regression
uv run bench history             # trends across the last 6 runs
uv run bench health dgx-01@latest --against median   # vs the median of the last 3 runs instead of the baseline
uv run bench compare dgx-01@baseline dgx-01@latest --markdown report.md
uv run bench runs                # everything in the store
```

`scripts/scheduled-run.ps1` and `scripts/scheduled-run.sh` wrap sync, run and health for Task Scheduler,
cron or systemd. Their headers show how to register them for the first Sunday of each month.

Run references accept a path, a run id, `<machine>` / `<machine>@latest`, `<machine>@-1` (the run before
the newest), `<machine>@2026-10-29`, or `<machine>@baseline[:<os>]`.

## The run record (`run.json`)

One JSON document per run (schema version 1, details in `src/anvesana/framework/records.py`):

| Field | Contents |
|---|---|
| `run_id`, `started_at`, `finished_at`, `status` | `<machine>_<date>_<os>[_tag]`, ISO 8601 with timezone, complete / partial / aborted |
| `machine` | profile id, description, hostname, profile file |
| `settings` | duration, cooldown, tag, `--only/--skip`, every benchmark with its args, **methodology `version`** and outcome, framework version, git commit, command line |
| `environment` | OS, kernel, NVIDIA driver, CUDA/library versions, GPU, CPU, RAM, **power plan / governor**, **AC power**, GPU power limit |
| `preflight` | conditions that make the run less representative (on battery, busy system) |
| `phases`, `phase_telemetry` | per-benchmark timing, and avg/peak GPU power, SM clock, GPU/SoC temperature, CPU clock, energy |
| `metrics` | `<benchmark>.<measure>` → value, unit, higher_is_better |

Each benchmark module has a `VERSION`. Bump it when a change makes new numbers incomparable with
old ones; `health`, `history` and `compare` then refuse to compare across the change, so re-baseline.

## Health check

`bench health` compares a run with the machine's baseline. Without a baseline, it uses the median of
the last 3 runs on the same OS. Each headline metric gets a status:

- **FAIL**: worse than the tolerance (`[health]` in the profile; per-metric globs, longest match wins)
- **WARN**: worse than half the tolerance
- **MISSING**: a benchmark that used to produce a metric no longer does
- **SKIP**: the methodology version changed

It also flags a GPU or SoC running 8 °C (WARN) or 15 °C (FAIL) hotter, or clocking lower, under the
same load, which catches cooling problems before they turn into throughput losses. Exit code 1 on
FAIL or MISSING.

## Benchmarks

| Benchmark | Measures | Notes |
|---|---|---|
| `cpu` | FP64 math (all cores / 1 core), FP64 DGEMM, memory copy bandwidth | numpy, one process per core |
| `gpu` | device memory copy bandwidth, FP32 FMA, FP16 `mma.sync` | PTX through the CUDA driver API |
| `tensor` | peak tensor-core TFLOPS: FP16/BF16/FP8/NVFP4/MXFP4, dense and 2:4 sparse | NVRTC-compiled `mma.sync` microbenchmark; unsupported precisions are skipped on older GPUs |
| `cublaslt` | GEMM TFLOPS FP32/TF32/FP16/BF16/FP8/NVFP4, autotuned, random data | what frameworks actually get |
| `tensorrt` | linear-layer engines FP16/BF16/FP8/NVFP4, dense and 2:4 sparse | `backend = "rtx"` (TensorRT for RTX) or `"trt"` (full TensorRT) |
| `cutlass` | best `cutlass_profiler` kernel per family: NVFP4, MXFP4, MXFP8, FP8 blockwise, sparse FP4/FP8 | Linux only; builds CUTLASS 4.2 once for the local arch; families are SM120-specific (add patterns for other GPUs) |
| `disk` | sequential R/W, random 4K QD1 R/W + latency, random 4K QD8 | page cache bypassed (`O_DIRECT` / `FILE_FLAG_NO_BUFFERING`) |

Every GPU benchmark also records average power, SM clock and TFLOPS/W while it runs. Each benchmark
runs in its own process, with a cooldown between benchmarks.

To add a benchmark, write `src/anvesana/suite/<name>.py` with `NAME`, `VERSION`, `DESCRIPTION`,
`add_arguments(parser)` and `run(args) -> list[Metric]`. Then register it in
`framework/registry.py` and list it in the relevant machine profiles.

Run any single benchmark directly: `uv run bench tensor --duration 10 --precisions fp16,nvfp4`.

## Platform notes (NVIDIA RTX Spark N1X, Windows on ARM)

- Full TensorRT's win_arm64 wheel lacks its Myelin resource DLLs, so it cannot build engines on
  Windows. Profiles list it with `os = ["linux"]`. TensorRT for RTX works on both OSes but picks slow
  kernels in 1.7 (FP16 ≈ 28 TFLOPS).
- The N1X GPU is power-capped at about 47 W. Instruction-level kernels hold ~2.4 GHz; real GEMMs drop
  to ~1.3–1.5 GHz. Power and clock are therefore recorded alongside throughput.
- The "1 PFLOP" spec is NVFP4 with 2:4 sparsity. `tensor.nvfp4_sparse` reaches 91–97% of it.
- Old PowerShell/bash scripts and their CSVs are in `legacy/`; `bench compare` still reads those CSVs.
