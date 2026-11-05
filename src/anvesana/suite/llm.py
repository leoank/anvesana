"""LLM inference throughput with a pinned llama.cpp build (llama-bench).

Measures what people quote for local inference: prompt processing (prefill)
and token generation (decode) in tokens/s, with the GPU power and clock
sampled separately for each, so a clock lock shows up next to the number it
explains. Built to check the "RTX Spark runs at a third of its Windows speed
on Linux" report (docs/rtx-spark-replication.md), and useful as a fleet
benchmark on its own.

Everything that changes the result is pinned here: the llama.cpp release
(same commit on every OS: the Windows ARM64 and Ubuntu ARM64 CUDA builds; the
Ubuntu one also runs in WSL and, through nix-ld, on the NixOS live image) and
the model files (Hugging Face revision, size and sha256). `scripts/llm-fetch.py`
downloads and verifies both.

  llm.<model>_pp<N>   prefill tokens/s for an N-token prompt
  llm.<model>_tg<N>   decode tokens/s for N generated tokens

Each headline metric has .avg_power, .efficiency (tok/s per W), .avg_sm_clock
and .throttle_reasons (NVML clock-event bits OR-ed over the measurement)
sub-metrics.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..framework.console import banner, report, step, summary
from ..framework.records import Metric
from ..hw.telemetry import GpuSampler, power_metrics

NAME = "llm"
VERSION = 1  # bump when results stop being comparable with earlier runs
DESCRIPTION = "LLM prefill/decode tokens/s with pinned llama.cpp (llama-bench) and GPT-OSS GGUF models"

LLAMA_CPP_BUILD = "b12119"
LLAMA_CPP_COMMIT = "6f1e6543704bc5b080c7a98e7b6f707b31f6ed51"

# Release assets per OS tag: (asset, sha256). The cudart archive carries the
# CUDA runtime and cuBLAS the build links against (CUDA 13.4).
LLAMA_CPP_ASSETS = {
    "windows": [
        ("llama-b12119-bin-win-cuda-13.4-arm64.zip",
         "1b72e70c98aa79e854141d50d9e5ac39133e268a2d330c0ace41910f04c455e0"),
        ("cudart-llama-bin-win-cuda-13.4-arm64.zip",
         "642dcde8805b3e3165ca710a5443b3b4044b27d96bd3ee3132473988c9bcb774"),
    ],
    "linux": [
        ("llama-b12119-bin-ubuntu-cuda-13.4-arm64.tar.gz",
         "1d31d13d8ac781385e7d5738a645c73a2ef5a375f8ac07e0ed4cd098f4ac97dd"),
        ("cudart-llama-b12119-bin-ubuntu-cuda-13.4-arm64.tar.gz",
         "9b8410a2bc5f10e1c8e27906fa6438bcb9b63b081f95075aed191d78342dbc2c"),
    ],
}

# name -> Hugging Face repo, revision, file, size in bytes, sha256 (LFS oid).
MODELS = {
    "gpt-oss-20b": {
        "repo": "ggml-org/gpt-oss-20b-GGUF",
        "revision": "15dcfc7e7c608c6161507211ed43c5b590801b4b",
        "file": "gpt-oss-20b-MXFP4.gguf",
        "size": 12109566624,
        "sha256": "27cd6c432c7672cb812a92f611cf3ba7bbc35928262bb1e1253ff4ee6ae35901",
    },
    "gpt-oss-120b": {
        "repo": "ggml-org/gpt-oss-120b-GGUF",
        "revision": "7200b74bea78b0a2964ef9f3897eefa401e890ff",
        "file": "gpt-oss-120b-MXFP4.gguf",
        "size": 63387346208,
        "sha256": "582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d",
    },
}


# Power, clock and throttle sub-metrics use only samples at or above this GPU utilisation.
BUSY_UTIL_PCT = 50


def default_models_dir() -> Path:
    env = os.environ.get("ANVESANA_MODELS_DIR")
    return Path(env) if env else Path.home() / ".cache" / "anvesana" / "models"


def default_llama_dir() -> Path:
    return Path.home() / ".cache" / "anvesana" / "llama.cpp" / LLAMA_CPP_BUILD


def find_llama_bench(explicit: str | None) -> str | None:
    """--llama-bench, then $ANVESANA_LLAMA_BENCH, then PATH, then the fetch cache."""
    exe = "llama-bench.exe" if sys.platform == "win32" else "llama-bench"
    for candidate in (explicit, os.environ.get("ANVESANA_LLAMA_BENCH")):
        if candidate:
            return candidate
    found = shutil.which("llama-bench")
    if found:
        return found
    cached = next(default_llama_dir().rglob(exe), None) if default_llama_dir().is_dir() else None
    return str(cached) if cached else None


def add_arguments(p):
    p.add_argument("--models", default="gpt-oss-20b", help="comma list of: " + ", ".join(MODELS))
    p.add_argument("--models-dir", default=None, help="directory with the GGUF files "
                   "(default: $ANVESANA_MODELS_DIR or ~/.cache/anvesana/models)")
    p.add_argument("--llama-bench", default=None, help="llama-bench executable (default: see find_llama_bench)")
    p.add_argument("--prompt", type=int, default=512, help="prompt tokens for the prefill test")
    p.add_argument("--gen", type=int, default=128, help="generated tokens for the decode test")
    p.add_argument("--reps", type=int, default=5, help="llama-bench repetitions per test")
    p.add_argument("--ngl", type=int, default=999, help="layers offloaded to the GPU")
    p.add_argument("--mmap", action="store_true",
                   help="load weights through mmap (default off: on unified memory it doubles the footprint)")


def _llama_bench(exe: str, model: Path, args, n_prompt: int, n_gen: int) -> dict:
    cmd = [exe, "-m", str(model), "-p", str(n_prompt), "-n", str(n_gen), "-r", str(args.reps),
           "-ngl", str(args.ngl), "-fa", "on", "-lm", "mmap" if args.mmap else "none", "-o", "json"]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"llama-bench failed ({out.returncode}): {out.stderr.strip()[-2000:]}")
    rows = json.loads(out.stdout)
    if len(rows) != 1:
        raise RuntimeError(f"expected one llama-bench result, got {len(rows)}")
    return rows[0]


def _throttle_mask(sampler: GpuSampler) -> int | None:
    vals = sampler._values("throttle_reasons")
    if not vals:
        return None
    mask = 0
    for v in vals:
        mask |= int(v)
    return mask


def run(args) -> list[Metric]:
    exe = find_llama_bench(args.llama_bench)
    models_dir = Path(args.models_dir) if args.models_dir else default_models_dir()
    names = [m.strip() for m in args.models.split(",") if m.strip()]
    banner("LLM inference - llama.cpp " + LLAMA_CPP_BUILD,
           f"Models: {', '.join(names)} in {models_dir}",
           f"pp{args.prompt} / tg{args.gen}, {args.reps} reps, flash attention, mmap {'on' if args.mmap else 'off'}")
    if not exe:
        print("llama-bench not found: run `uv run python scripts/llm-fetch.py llama-cpp` or pass --llama-bench.")
        return []

    metrics = []
    for name in names:
        spec = MODELS.get(name)
        if spec is None:
            print(f"unknown model '{name}' (known: {', '.join(MODELS)})")
            continue
        path = models_dir / spec["file"]
        if not path.is_file() or path.stat().st_size != spec["size"]:
            print(f"{path}: missing or wrong size; run `uv run python scripts/llm-fetch.py models --models {name}`")
            continue
        key = name.replace("-", "_")
        for label, n_prompt, n_gen in (("pp", args.prompt, 0), ("tg", 0, args.gen)):
            n = n_prompt or n_gen
            step(f"{name}: {'prefill' if label == 'pp' else 'decode'} {label}{n} ...")
            with GpuSampler(interval_s=0.05) as sampler:
                row = _llama_bench(exe, path, args, n_prompt, n_gen)
            # llama-bench loads the model inside the same call, which can take minutes
            # from a slow drive: keep only the samples where the GPU was working.
            sampler.samples = [s for s in sampler.samples if (s.get("util_pct") or 0) >= BUSY_UTIL_PCT]
            tps = float(row["avg_ts"])
            build = f"build {row.get('build_number')} ({str(row.get('build_commit', ''))[:7]})"
            if str(row.get("build_commit", "")) and not LLAMA_CPP_COMMIT.startswith(str(row["build_commit"])):
                build += f", not the pinned {LLAMA_CPP_BUILD}"
            report(f"{name} {label}{n}", tps, "tok/s", f"+/- {float(row.get('stddev_ts', 0)):.2f} {sampler.describe()}")
            prefix = f"llm.{key}_{label}{n}"
            metrics.append(Metric(prefix, tps, "tok/s", note=f"llama.cpp {build}; {row.get('gpu_info', '')}"))
            metrics += power_metrics(prefix, tps, sampler, unit="tok/s")
            mask = _throttle_mask(sampler)
            if mask is not None:
                metrics.append(Metric(f"{prefix}.throttle_reasons", mask, "NVML mask", higher_is_better=False,
                                      note="OR of nvmlDeviceGetCurrentClocksEventReasons over the test"))
    summary("LLM inference", metrics)
    return metrics
