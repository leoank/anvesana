"""CPU and memory benchmark (port of stress_cpu_ram.ps1, plus FP64 GEMM).

  cpu_math    the original FP64 sqrt/sin/cos recurrence, one process per core,
              vectorised with numpy over L1-resident arrays (MOps/s)
  fp64_gemm   numpy/OpenBLAS DGEMM on all cores (GFLOPS)
  mem_copy    streaming copy, one process per core with private 64 MiB
              buffers; counts read + write bytes like the original (GB/s)

Processes, not threads, so the GIL never limits scaling. Absolute numbers are
not comparable with the C#/PowerShell version (different code generation),
but Windows-vs-Linux runs of this module are.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import time

import numpy as np

from ..framework.console import banner, report, step, summary
from ..framework.records import Metric

NAME = "cpu"
VERSION = 1  # bump when results stop being comparable with earlier runs
DESCRIPTION = "Multi-core FP64 math, FP64 GEMM and memory bandwidth (port of stress_cpu_ram.ps1)"

MATH_ELEMS = 2048  # 2 arrays x 16 KiB: stays in L1


def _cpu_math_worker(seconds: float, start_at: float, queue):
    a = np.full(MATH_ELEMS, 1.000001)
    b = np.full(MATH_ELEMS, 0.999999)
    t1 = np.empty(MATH_ELEMS)
    t2 = np.empty(MATH_ELEMS)
    while time.time() < start_at:
        pass
    t0 = time.perf_counter()
    ops = 0
    while time.perf_counter() - t0 < seconds:
        for _ in range(200):
            # a = sqrt(a*b + c) * sin(a); b = cos(b*1.0001) + a*1e-5, as in the C# loop
            np.multiply(a, b, out=t1)
            t1 += 1.5
            np.sqrt(t1, out=t1)
            np.sin(a, out=t2)
            np.multiply(t1, t2, out=a)
            np.multiply(b, 1.0001, out=t1)
            np.cos(t1, out=b)
            np.multiply(a, 0.00001, out=t1)
            b += t1
        ops += 200 * MATH_ELEMS
    queue.put((ops, time.perf_counter() - t0))


def _mem_copy_worker(seconds: float, start_at: float, buffer_mb: int, queue):
    n = buffer_mb * 2**20 // 8
    src = np.arange(n, dtype=np.int64)
    dst = np.empty_like(src)
    np.copyto(dst, src)  # fault in pages before timing
    while time.time() < start_at:
        pass
    t0 = time.perf_counter()
    passes = 0
    while time.perf_counter() - t0 < seconds:
        np.copyto(dst, src)
        passes += 1
    queue.put((2 * src.nbytes * passes, time.perf_counter() - t0))


def _parallel(target, workers: int, *args) -> tuple[float, float]:
    """Runs ``target`` in ``workers`` processes released at the same instant.
    Returns (total work, longest elapsed)."""
    ctx = mp.get_context("spawn")
    queue = ctx.Queue()
    start_at = time.time() + 1.0 + workers * 0.1  # time for every process to spawn
    procs = [ctx.Process(target=target, args=(*args[:1], start_at, *args[1:], queue)) for _ in range(workers)]
    for p in procs:
        p.start()
    results = [queue.get() for _ in procs]
    for p in procs:
        p.join()
    return sum(r[0] for r in results), max(r[1] for r in results)


def fp64_gemm(seconds: float, n: int = 4096) -> float:
    rng = np.random.default_rng(0)
    a, b = rng.random((n, n)), rng.random((n, n))
    c = a @ b  # warm-up / thread-pool start
    t0, iters = time.perf_counter(), 0
    while time.perf_counter() - t0 < seconds:
        np.matmul(a, b, out=c)
        iters += 1
    return 2.0 * n**3 * iters / (time.perf_counter() - t0) / 1e9


def add_arguments(p):
    p.add_argument("--threads", type=int, default=0, help="worker processes (default: all logical CPUs)")
    p.add_argument("--cpu-only", action="store_true")
    p.add_argument("--mem-only", action="store_true")


def run(args) -> list[Metric]:
    workers = args.threads or os.cpu_count()
    secs = args.duration
    banner("NVIDIA RTX Spark - CPU & Memory Benchmark", f"Workers: {workers} | Duration: {secs:.0f}s per test")
    metrics = []

    if not args.mem_only:
        step(f"[1/4] FP64 math recurrence, {workers} processes ({secs:.0f}s)...")
        ops, elapsed = _parallel(_cpu_math_worker, workers, secs)
        mops = ops / elapsed / 1e6
        report("Throughput", mops, "MOps/s", f"({mops / workers:.1f} per core)")
        metrics.append(Metric("cpu.math_mops", mops, "MOps/s"))

        step(f"[2/4] FP64 math recurrence, single core ({secs / 3:.0f}s)...")
        ops, elapsed = _parallel(_cpu_math_worker, 1, secs / 3)
        report("Single-core throughput", ops / elapsed / 1e6, "MOps/s")
        metrics.append(Metric("cpu.math_mops_1core", ops / elapsed / 1e6, "MOps/s"))

        step(f"[3/4] FP64 GEMM 4096^3 via numpy BLAS ({secs:.0f}s)...")
        gflops = fp64_gemm(secs)
        report("DGEMM", gflops, "GFLOPS")
        metrics.append(Metric("cpu.fp64_gemm", gflops, "GFLOPS"))

    if not args.cpu_only:
        step(f"[4/4] Memory streaming copy, {workers} x 64 MiB buffers ({secs:.0f}s)...")
        nbytes, elapsed = _parallel(_mem_copy_worker, workers, secs, 64)
        report("All-core copy bandwidth", nbytes / elapsed / 1e9, "GB/s")
        metrics.append(Metric("cpu.mem_copy_bandwidth", nbytes / elapsed / 1e9, "GB/s"))
        nbytes, elapsed = _parallel(_mem_copy_worker, 1, secs / 3, 256)
        report("Single-core copy bandwidth", nbytes / elapsed / 1e9, "GB/s")
        metrics.append(Metric("cpu.mem_copy_bandwidth_1core", nbytes / elapsed / 1e9, "GB/s"))

    summary("CPU & Memory Summary", metrics)
    return metrics
