"""Blackwell GPU compute & unified-memory benchmark (port of stress_gpu.ps1).

Uses the CUDA driver API directly: no toolkit or compiler is needed, the PTX
below is JIT-compiled by the driver. The kernels are kept identical to the
PowerShell version so results stay comparable with earlier runs.
"""

from __future__ import annotations

import time

import numpy as np
from cuda.bindings import driver as cu

from ..hw import cuda
from ..framework.console import banner, report, step, summary
from ..framework.records import Metric
from ..hw.telemetry import GpuSampler, max_sm_clock_mhz, power_metrics

NAME = "gpu"
VERSION = 1  # bump when results stop being comparable with earlier runs
DESCRIPTION = "Unified memory bandwidth, FP32 CUDA-core FMA, legacy FP16 mma.sync (port of stress_gpu.ps1)"

PTX_FP32 = r"""
.version 7.0
.target sm_70
.address_size 64

.visible .entry gpu_stress(
    .param .u64 d_out,
    .param .u32 iterations
)
{
    .reg .u64 %rd<4>;
    .reg .u32 %r<5>;
    .reg .f32 %f<18>;
    .reg .pred %p<2>;

    ld.param.u64 %rd1, [d_out];
    ld.param.u32 %r1, [iterations];

    mov.u32 %r2, %tid.x;
    mov.u32 %r3, %ctaid.x;
    mov.u32 %r4, %ntid.x;
    mad.lo.u32 %r2, %r3, %r4, %r2;

    mov.f32 %f1, 1.0001;
    mov.f32 %f2, 1.0002;
    mov.f32 %f3, 1.0003;
    mov.f32 %f4, 1.0004;
    mov.f32 %f5, 0.5001;

    mov.u32 %r3, 0;

L_loop:
    fma.rn.f32 %f1, %f1, %f2, %f5;
    fma.rn.f32 %f2, %f2, %f3, %f5;
    fma.rn.f32 %f3, %f3, %f4, %f5;
    fma.rn.f32 %f4, %f4, %f1, %f5;
    fma.rn.f32 %f1, %f1, %f3, %f5;
    fma.rn.f32 %f2, %f2, %f4, %f5;
    fma.rn.f32 %f3, %f3, %f1, %f5;
    fma.rn.f32 %f4, %f4, %f2, %f5;
    fma.rn.f32 %f1, %f1, %f2, %f5;
    fma.rn.f32 %f2, %f2, %f3, %f5;
    fma.rn.f32 %f3, %f3, %f4, %f5;
    fma.rn.f32 %f4, %f4, %f1, %f5;
    fma.rn.f32 %f1, %f1, %f3, %f5;
    fma.rn.f32 %f2, %f2, %f4, %f5;
    fma.rn.f32 %f3, %f3, %f1, %f5;
    fma.rn.f32 %f4, %f4, %f2, %f5;

    add.u32 %r3, %r3, 1;
    setp.lt.u32 %p1, %r3, %r1;
    @%p1 bra L_loop;

    mul.wide.u32 %rd2, %r2, 4;
    add.u64 %rd3, %rd1, %rd2;
    add.f32 %f1, %f1, %f2;
    add.f32 %f3, %f3, %f4;
    add.f32 %f1, %f1, %f3;
    st.global.f32 [%rd3], %f1;
    ret;
}
"""

_MMA = """
    mma.sync.aligned.m16n8k16.row.col.f32.f16.f16.f32
        {{%{d}0, %{d}1, %{d}2, %{d}3}},
        {{%a0, %a1, %a2, %a3}},
        {{%b0, %b1}},
        {{%{c}0, %{c}1, %{c}2, %{c}3}};
"""

PTX_TENSOR_MMA = r"""
.version 7.8
.target sm_80
.address_size 64

.visible .entry tensor_mma_stress(
    .param .u64 d_out,
    .param .u32 iterations
)
{
    .reg .u64 %rd<4>;
    .reg .u32 %r<5>;
    .reg .b32 %a<4>, %b<2>;
    .reg .f32 %c<4>, %d<4>;
    .reg .pred %p<2>;

    ld.param.u64 %rd1, [d_out];
    ld.param.u32 %r1, [iterations];

    mov.b32 %a0, 0x3c003c00;
    mov.b32 %a1, 0x3c003c00;
    mov.b32 %a2, 0x3c003c00;
    mov.b32 %a3, 0x3c003c00;
    mov.b32 %b0, 0x3c003c00;
    mov.b32 %b1, 0x3c003c00;
    mov.f32 %c0, 0.0;
    mov.f32 %c1, 0.0;
    mov.f32 %c2, 0.0;
    mov.f32 %c3, 0.0;

    mov.u32 %r3, 0;

L_loop:
""" + "".join(_MMA.format(d="d", c="c") if i % 2 == 0 else _MMA.format(d="c", c="d") for i in range(8)) + r"""
    add.u32 %r3, %r3, 1;
    setp.lt.u32 %p1, %r3, %r1;
    @%p1 bra L_loop;

    mov.u32 %r2, %tid.x;
    mov.u32 %r3, %ctaid.x;
    mov.u32 %r4, %ntid.x;
    mad.lo.u32 %r2, %r3, %r4, %r2;
    mul.wide.u32 %rd2, %r2, 4;
    add.u64 %rd3, %rd1, %rd2;
    st.global.f32 [%rd3], %c0;

    ret;
}
"""

GRID, BLOCK = 384, 512  # 196,608 threads, as in the PowerShell version


def memory_bandwidth(buffer_mb: int = 512, passes: int = 40) -> float:
    """Device-to-device copy bandwidth in GB/s (decimal; counts read + write)."""
    nbytes = buffer_mb * 2**20
    with cuda.DeviceBuffer(nbytes) as src, cuda.DeviceBuffer(nbytes) as dst:
        cuda.check(cu.cuMemcpyDtoD(dst.ptr, src.ptr, nbytes))
        timer = cuda.EventTimer()
        timer.start()
        for _ in range(passes):
            cuda.check(cu.cuMemcpyDtoD(dst.ptr, src.ptr, nbytes))
        seconds = timer.stop()
    return 2.0 * nbytes * passes / seconds / 1e9


def sustained_tflops(ptx: str, entry: str, iters: int, flops_per_launch: float, seconds: float) -> float:
    """Launches a kernel back-to-back for ``seconds`` and returns TFLOPS."""
    module = cuda.Module(ptx)
    kernel = module.kernel(entry)
    with cuda.DeviceBuffer(GRID * BLOCK * 4) as out:
        args = cuda.KernelArgs(np.uint64(out.ptr), np.uint32(iters))
        kernel.launch(GRID, BLOCK, args)
        cuda.Device.synchronize()
        timer = cuda.EventTimer()
        timer.start()
        t0, launches = time.perf_counter(), 0
        while time.perf_counter() - t0 < seconds:
            kernel.launch(GRID, BLOCK, args)
            launches += 1
        elapsed = timer.stop()
    module.unload()
    return flops_per_launch * launches / elapsed / 1e12


def add_arguments(p):
    p.add_argument("--mem-only", action="store_true")
    p.add_argument("--compute-only", action="store_true")


def run(args) -> list[Metric]:
    dev = cuda.get_device()
    banner("NVIDIA RTX Spark - Blackwell GPU Compute Benchmark", f"Target duration: {args.duration:.0f}s per compute test")
    print(f"\n[Hardware Detection]")
    print(f"  GPU Model           : {dev.name}")
    print(f"  Compute Capability  : %d.%d" % dev.cc)
    print(f"  Streaming Multiprocs: {dev.sm_count} SMs (~{dev.sm_count * 128} CUDA cores)")
    print(f"  Max SM Clock        : {max_sm_clock_mhz() or '?'} MHz")
    print(f"  Total Memory        : {dev.total_mem_bytes / 1e9:.2f} GB (unified)")

    metrics = []
    if not args.compute_only:
        step("[1/3] Unified memory bandwidth (cuMemcpyDtoD, 512 MiB x 40 passes)...")
        bw = memory_bandwidth()
        report("Device copy bandwidth", bw, "GB/s")
        metrics.append(Metric("gpu.mem_copy_bandwidth", bw, "GB/s"))

    if not args.mem_only:
        threads = GRID * BLOCK
        step(f"[2/3] FP32 CUDA-core FMA ({args.duration:.0f}s)...")
        iters = 20000
        with GpuSampler() as s:
            fp32 = sustained_tflops(PTX_FP32, "gpu_stress", iters, threads * 32.0 * iters, args.duration)
        report("Sustained FP32", fp32, "TFLOPS", s.describe())
        metrics += [Metric("gpu.fp32_fma", fp32, "TFLOPS")] + power_metrics("gpu.fp32_fma", fp32, s)

        step(f"[3/3] Legacy FP16 mma.sync m16n8k16, dependent chain ({args.duration:.0f}s)...")
        iters = 10000
        warps = threads // 32
        with GpuSampler() as s:
            mma = sustained_tflops(PTX_TENSOR_MMA, "tensor_mma_stress", iters, warps * 8 * 4096.0 * iters, args.duration)
        report("Sustained FP16 MMA", mma, "TFLOPS", s.describe())
        metrics += [Metric("gpu.fp16_mma_legacy", mma, "TFLOPS")] + power_metrics("gpu.fp16_mma_legacy", mma, s)

    summary("GPU Benchmark Summary", metrics)
    return metrics
