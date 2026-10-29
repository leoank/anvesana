"""CUTLASS GEMM throughput via NVIDIA's own cutlass_profiler (Linux only).

CUTLASS is a C++ template library, so its canonical benchmark is the C++
profiler. This module builds it once (cached) for the local GPU arch,
restricted to the kernel families relevant to low-precision AI throughput,
then runs it and reports the fastest kernel of each family:

  nvfp4           block-scaled FP4, UE4M3 scale per 16 elements
  mxfp4           block-scaled FP4, UE8M0 scale per 32 elements
  mxfp8           block-scaled FP8 (E4M3)
  fp8_blockwise   FP8 with 1x128 / 128x128 FP32 scales (DeepSeek style)
  fp4_sparse      2:4 sparse FP4 (E2M1, unscaled f8f6f4 path)
  fp8_sparse      2:4 sparse FP8 (E4M3)

(CUTLASS 4.2 does not instantiate plain FP16/BF16 SM120 kernels in its
library; cuBLASLt covers those.)

Why not Windows: CUTLASS's SM90+ kernels pass TMA descriptors in a 128-byte
aligned parameter struct, and MSVC (the only host compiler nvcc accepts on
Windows) cannot pass such a struct by value (error C2719). The toolchain
itself works; these kernels cannot be compiled with it.

Toolchain on Linux: nvcc, CUDA headers, cmake and ninja come from pip
(`uv sync --extra cutlass`); the host compiler is the system g++. The CUTLASS
source is the GitHub release matching the nvidia-cutlass wheel.
"""

from __future__ import annotations

import csv
import glob
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

from ..framework.console import banner, report, step, summary
from ..framework.records import Metric
from ..hw.telemetry import GpuSampler, power_metrics

NAME = "cutlass"
VERSION = 1  # bump when results stop being comparable with earlier runs
DESCRIPTION = "CUTLASS profiler GEMMs (NVFP4/MXFP4/MXFP8/FP8 blockwise, 2:4 sparse FP4/FP8); Linux only"

CUTLASS_VERSION = "4.2.0"

# Kernel-name globs for SM120/121 (RTX Blackwell, N1X/GB10). Other GPU generations
# (sm_90 Hopper, sm_100 datacenter Blackwell) name their kernels differently and
# need their own families here before this benchmark is useful on them.
FAMILIES = {
    "nvfp4": "cutlass3x_sm120_bstensorop_gemm_ue4m3xe2m1_ue4m3xe2m1_*",
    "mxfp4": "cutlass3x_sm120_bstensorop_gemm_ue8m0xe2m1_ue8m0xe2m1_*",
    "mxfp8": "cutlass3x_sm120_bstensorop_gemm_ue8m0xe4m3_ue8m0xe4m3_*",
    "fp8_blockwise": "cutlass3x_sm120_tensorop_gemm_1x128f32xe4m3_128x128f32xe4m3_*",
    "fp4_sparse": "cutlass3x_sm120_sptensorop_spgemm_e2m1_e2m1_*",
    "fp8_sparse": "cutlass3x_sm120_sptensorop_spgemm_e4m3_e4m3_*",
}


class ToolchainError(RuntimeError):
    pass


def default_build_root() -> Path:
    return Path.home() / ".cache" / "anvesana" / "cutlass"


def local_arch() -> str:
    """CUTLASS_NVCC_ARCHS value for GPU 0, e.g. "121a"."""
    from ..hw import cuda

    return cuda.get_device().arch.removeprefix("sm_")


def find_nvcc() -> tuple[str, Path]:
    """Returns (nvcc path, CUDA toolkit root). Prefers an installed toolkit."""
    for env in ("CUDA_HOME", "CUDA_PATH"):
        nvcc = Path(os.environ.get(env, "")) / "bin" / "nvcc"
        if os.environ.get(env) and nvcc.exists():
            return str(nvcc), nvcc.parent.parent
    on_path = shutil.which("nvcc")
    if on_path:
        return on_path, Path(on_path).resolve().parent.parent
    for base in map(Path, sys.path):
        root = base / "nvidia" / "cu13"
        if (root / "bin" / "nvcc").exists():
            return str(root / "bin" / "nvcc"), root
    raise ToolchainError("nvcc not found: install a CUDA toolkit or `uv sync --extra cutlass`")


def _tool(name: str) -> str:
    """cmake / ninja from the venv first, else PATH."""
    cand = Path(sys.executable).parent / name
    if cand.exists():
        return str(cand)
    found = shutil.which(name)
    if not found:
        raise ToolchainError(f"{name} not found: `uv sync --extra cutlass`")
    return found


def fetch_source(root: Path) -> Path:
    src = root / f"cutlass-{CUTLASS_VERSION}"
    if (src / "CMakeLists.txt").exists():
        return src
    root.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/NVIDIA/cutlass/archive/refs/tags/v{CUTLASS_VERSION}.tar.gz"
    archive = root / f"cutlass-{CUTLASS_VERSION}.tar.gz"
    print(f"     downloading {url}")
    urllib.request.urlretrieve(url, archive)
    with tarfile.open(archive) as tar:
        tar.extractall(root, filter="data")
    archive.unlink()
    return src


def build_profiler(root: Path, arch: str, jobs: int) -> Path:
    build = root / f"build-sm{arch}"
    exe = build / "tools" / "profiler" / "cutlass_profiler"
    if exe.exists():
        return exe
    if not (shutil.which("c++") or shutil.which("g++")):
        raise ToolchainError("no host C++ compiler (install g++)")
    nvcc, cuda_root = find_nvcc()
    src = fetch_source(root)
    env = dict(os.environ, CUDA_HOME=str(cuda_root), PATH=os.pathsep.join([str(Path(nvcc).parent),
                                                                            os.environ.get("PATH", "")]))
    configure = [
        _tool("cmake"), "-G", "Ninja", "-S", str(src), "-B", str(build),
        f"-DCMAKE_MAKE_PROGRAM={_tool('ninja')}",
        "-DCMAKE_BUILD_TYPE=Release",
        f"-DCMAKE_CUDA_COMPILER={nvcc}",
        f"-DCUDAToolkit_ROOT={cuda_root}",
        f"-DPython3_EXECUTABLE={sys.executable}",  # CUTLASS generates its kernels with Python
        f"-DCUTLASS_NVCC_ARCHS={arch}",
        "-DCUTLASS_LIBRARY_OPERATIONS=gemm",
        f"-DCUTLASS_LIBRARY_KERNELS={','.join(FAMILIES.values())}",
        "-DCUTLASS_ENABLE_TESTS=OFF", "-DCUTLASS_ENABLE_EXAMPLES=OFF",
        "-DCUTLASS_ENABLE_CUBLAS=OFF", "-DCUTLASS_ENABLE_CUDNN=OFF",
        "-DCUTLASS_UNITY_BUILD_ENABLED=ON",
    ]
    log = root / "build.log"
    with open(log, "w") as f:
        print(f"     configuring (log: {log})")
        if subprocess.run(configure, env=env, stdout=f, stderr=subprocess.STDOUT).returncode != 0:
            raise ToolchainError(f"CMake configure failed, see {log}")
        print(f"     compiling cutlass_profiler with {jobs} jobs (one-time, can take 30+ minutes)...")
        cmd = [_tool("cmake"), "--build", str(build), "--target", "cutlass_profiler", "-j", str(jobs)]
        if subprocess.run(cmd, env=env, stdout=f, stderr=subprocess.STDOUT).returncode != 0:
            raise ToolchainError(f"build failed, see {log}")
    return exe


def profile_family(exe: Path, family: str, pattern: str, size: int, out_dir: Path, seconds: float) -> dict | None:
    """Runs every kernel of a family and returns the fastest one's CSV row."""
    prefix = out_dir / family
    for old in glob.glob(f"{prefix}*.csv"):
        os.remove(old)
    cmd = [str(exe), f"--kernels={pattern}", f"--m={size}", f"--n={size}", f"--k={size}",
           "--verification-enabled=false", "--warmup-iterations=10",
           "--profiling-iterations=0", f"--profiling-duration={int(seconds * 1000)}",
           f"--output={prefix}.csv"]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, cwd=out_dir)
    best = None
    for path in glob.glob(f"{prefix}*.csv"):
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                if row.get("Status", "success") != "success":
                    continue
                try:
                    gflops = float(row["GFLOPs"])
                except (KeyError, ValueError):
                    continue
                if best is None or gflops > best["gflops"]:
                    best = {"gflops": gflops, "kernel": row.get("Operation", "?"), "runtime_ms": row.get("Runtime")}
    return best


def add_arguments(p):
    p.add_argument("--families", default=",".join(FAMILIES), help="subset of: " + ", ".join(FAMILIES))
    p.add_argument("--size", type=int, default=8192, help="M = N = K")
    p.add_argument("--build-root", default=str(default_build_root()), help="where CUTLASS is downloaded and built")
    p.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 4) // 2),
                   help="parallel compile jobs (each nvcc job can use several GB of RAM)")


def run(args) -> list[Metric]:
    banner("CUTLASS profiler GEMM throughput", f"CUTLASS {CUTLASS_VERSION} | M=N=K={args.size}")
    if sys.platform != "linux":
        print("  !! CUTLASS SM90+ kernels cannot be compiled with MSVC (error C2719: 128-byte aligned kernel\n"
              "     parameters), and nvcc accepts no other host compiler on Windows. Linux only.")
        return []
    root = Path(args.build_root)
    families = [f.strip() for f in args.families.split(",") if f.strip()]
    per_family = max(2.0, args.duration / 3)
    step("[build] cutlass_profiler")
    try:
        arch = local_arch()
        exe = build_profiler(root, arch, args.jobs)
    except (ToolchainError, OSError) as e:
        print(f"  !! CUTLASS unavailable: {e}")
        return []
    print(f"     {exe} (sm_{arch})")

    out_dir = root / "profiles"
    out_dir.mkdir(exist_ok=True)
    metrics = []
    for i, fam in enumerate(families, 1):
        step(f"[{i}/{len(families)}] {fam}: profiling every kernel in the family...")
        with GpuSampler() as s:
            best = profile_family(exe, fam, FAMILIES[fam], args.size, out_dir, per_family)
        if not best:
            print("  !! no kernel ran (none built for this family, or all failed)")
            continue
        tflops = best["gflops"] / 1000
        report(fam, tflops, "TFLOPS", s.describe())
        print(f"     best kernel: {best['kernel']}")
        metrics.append(Metric(f"cutlass.{fam}", tflops, "TFLOPS", note=best["kernel"]))
        metrics += power_metrics(f"cutlass.{fam}", tflops, s)

    summary("CUTLASS Summary", [m for m in metrics if m.unit == "TFLOPS"])
    return metrics
