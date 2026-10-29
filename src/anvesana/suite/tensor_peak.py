"""Peak tensor-core throughput per precision, straight from the MMA instructions.

Each warp issues back-to-back ``mma.sync`` instructions on register-resident
operands with several independent accumulators, so nothing but the tensor
cores is exercised. This is the ceiling any GEMM library (cuBLASLt,
CUTLASS, TensorRT) can approach, and the right number to hold against a
vendor's advertised peak (machine profile [expected] section).

Kernels are CUDA C++ with inline PTX, compiled by NVRTC for the device's
arch-specific target (e.g. sm_121a). Precisions the GPU lacks (FP4 before
Blackwell, FP8 before Ada) fail to compile and are skipped.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from ..hw import cuda
from ..framework.console import banner, report, step, summary
from ..framework.records import Metric
from ..hw.telemetry import GpuSampler, power_metrics

NAME = "tensor"
VERSION = 1  # bump when results stop being comparable with earlier runs
DESCRIPTION = "Peak tensor-core TFLOPS per precision (FP16/BF16/FP8/NVFP4/MXFP4, dense and 2:4 sparse)"


@dataclass
class Mma:
    asm: str
    a_regs: int
    b_regs: int
    c_regs: int  # accumulator registers per thread
    flops: int  # 2*M*N*K (dense-equivalent K for sparse)
    sparse: bool = False
    scaled: bool = False
    acc_type: str = "f"  # inline-asm constraint for the accumulator: "f" float, "r" packed half


# Operand order inside each asm string: accumulators, A, B, [sparsity metadata], [scale factors].
MMAS = {
    "fp16": Mma("mma.sync.aligned.m16n8k16.row.col.f32.f16.f16.f32 {%0,%1,%2,%3}, {%4,%5,%6,%7}, {%8,%9}, {%0,%1,%2,%3};",
                4, 2, 4, 2 * 16 * 8 * 16),
    "fp16_f16acc": Mma("mma.sync.aligned.m16n8k16.row.col.f16.f16.f16.f16 {%0,%1}, {%2,%3,%4,%5}, {%6,%7}, {%0,%1};",
                       4, 2, 2, 2 * 16 * 8 * 16, acc_type="r"),
    "bf16": Mma("mma.sync.aligned.m16n8k16.row.col.f32.bf16.bf16.f32 {%0,%1,%2,%3}, {%4,%5,%6,%7}, {%8,%9}, {%0,%1,%2,%3};",
                4, 2, 4, 2 * 16 * 8 * 16),
    "fp8": Mma("mma.sync.aligned.m16n8k32.row.col.f32.e4m3.e4m3.f32 {%0,%1,%2,%3}, {%4,%5,%6,%7}, {%8,%9}, {%0,%1,%2,%3};",
               4, 2, 4, 2 * 16 * 8 * 32),
    "nvfp4": Mma("mma.sync.aligned.m16n8k64.row.col.kind::mxf4nvf4.block_scale.scale_vec::4X.f32.e2m1.e2m1.f32.ue4m3 "
                 "{%0,%1,%2,%3}, {%4,%5,%6,%7}, {%8,%9}, {%0,%1,%2,%3}, %10, {0, 0}, %10, {0, 0};",
                 4, 2, 4, 2 * 16 * 8 * 64, scaled=True),
    "mxfp4": Mma("mma.sync.aligned.m16n8k64.row.col.kind::mxf4.block_scale.scale_vec::2X.f32.e2m1.e2m1.f32.ue8m0 "
                 "{%0,%1,%2,%3}, {%4,%5,%6,%7}, {%8,%9}, {%0,%1,%2,%3}, %10, {0, 0}, %10, {0, 0};",
                 4, 2, 4, 2 * 16 * 8 * 64, scaled=True),
    "fp16_sparse": Mma("mma.sp::ordered_metadata.sync.aligned.m16n8k32.row.col.f32.f16.f16.f32 "
                       "{%0,%1,%2,%3}, {%4,%5,%6,%7}, {%8,%9,%10,%11}, {%0,%1,%2,%3}, %12, 0x0;",
                       4, 4, 4, 2 * 16 * 8 * 32, sparse=True),
    "fp8_sparse": Mma("mma.sp::ordered_metadata.sync.aligned.m16n8k64.row.col.f32.e4m3.e4m3.f32 "
                      "{%0,%1,%2,%3}, {%4,%5,%6,%7}, {%8,%9,%10,%11}, {%0,%1,%2,%3}, %12, 0x0;",
                      4, 4, 4, 2 * 16 * 8 * 64, sparse=True),
    "nvfp4_sparse": Mma("mma.sp::ordered_metadata.sync.aligned.m16n8k128.row.col.kind::mxf4nvf4.block_scale.scale_vec::4X.f32.e2m1.e2m1.f32.ue4m3 "
                        "{%0,%1,%2,%3}, {%4,%5,%6,%7}, {%8,%9,%10,%11}, {%0,%1,%2,%3}, %12, 0x0, %13, {0, 0}, %13, {0, 0};",
                        4, 4, 4, 2 * 16 * 8 * 128, sparse=True, scaled=True),
}

UNROLL = 4


def kernel_source(m: Mma, chains: int) -> str:
    acc_ctype = "float" if m.acc_type == "f" else "unsigned"
    ins = [f'"r"(a[{i}])' for i in range(m.a_regs)] + [f'"r"(b[{i}])' for i in range(m.b_regs)]
    if m.sparse:
        ins.append('"r"(meta)')
    if m.scaled:
        ins.append('"r"(scale)')
    body = ""
    for c in range(chains):
        outs = ", ".join(f'"+{m.acc_type}"(acc{c}[{i}])' for i in range(m.c_regs))
        body += f'      asm volatile("{m.asm}" : {outs} : {", ".join(ins)});\n'
    decl = "\n".join(f"  {acc_ctype} acc{c}[{m.c_regs}] = {{}};" for c in range(chains))
    fold = " + ".join(f"(float)acc{c}[{i}]" for c in range(chains) for i in range(m.c_regs))
    return f"""
extern "C" __global__ void mma_peak(float* out, unsigned iters, unsigned seed) {{
  unsigned a[{m.a_regs}], b[{m.b_regs}];
  #pragma unroll
  for (int i = 0; i < {m.a_regs}; ++i) a[i] = (seed * (i + 1)) ^ threadIdx.x;
  #pragma unroll
  for (int i = 0; i < {m.b_regs}; ++i) b[i] = (seed * (i + 7)) ^ threadIdx.x;
  unsigned meta = 0x44444444u;   // valid 2:4 pattern: elements {{0,1}} of each group of 4
  unsigned scale = 0x38383838u;  // 1.0 in UE4M3; UE8M0 2^-71, value is irrelevant here
{decl}
  for (unsigned it = 0; it < iters; ++it) {{
    #pragma unroll
    for (int u = 0; u < {UNROLL}; ++u) {{
{body}    }}
  }}
  float r = {fold};
  if (r == 1234.5f) out[blockIdx.x * blockDim.x + threadIdx.x] = r;  // keep results live
}}
"""


def measure(name: str, seconds: float, chains: int = 4, blocks_per_sm: int = 4, block: int = 256):
    dev = cuda.get_device()
    m = MMAS[name]
    module = cuda.Module(cuda.compile_cuda(kernel_source(m, chains), dev.arch, f"mma_{name}.cu"))
    kernel = module.kernel("mma_peak")
    grid = dev.sm_count * blocks_per_sm
    iters = 2000
    flops_per_launch = (grid * block // 32) * iters * UNROLL * chains * m.flops
    with cuda.DeviceBuffer(grid * block * 4) as out, GpuSampler() as sampler:
        args = cuda.KernelArgs(np.uint64(out.ptr), np.uint32(iters), np.uint32(3))
        kernel.launch(grid, block, args)  # warm-up
        cuda.Device.synchronize()
        timer = cuda.EventTimer()
        timer.start()
        t0, launches = time.perf_counter(), 0
        while time.perf_counter() - t0 < seconds:
            kernel.launch(grid, block, args)
            launches += 1
        elapsed = timer.stop()
    module.unload()
    return flops_per_launch * launches / elapsed / 1e12, sampler


def add_arguments(p):
    p.add_argument("--precisions", default=",".join(MMAS),
                   help="comma-separated subset of: " + ", ".join(MMAS))
    p.add_argument("--chains", type=int, default=4, help="independent accumulators per warp")
    p.add_argument("--blocks-per-sm", type=int, default=4)


def run(args) -> list[Metric]:
    names = [n.strip() for n in args.precisions.split(",") if n.strip()]
    per_test = max(2.0, args.duration / 3)
    dev = cuda.get_device()
    banner("Tensor-core peak throughput (mma.sync microbenchmark)",
           f"{dev.name} | {dev.arch} | {dev.sm_count} SMs | {per_test:.0f}s per precision")
    metrics, rows = [], []
    for i, name in enumerate(names, 1):
        step(f"[{i}/{len(names)}] {name}")
        try:
            tflops, s = measure(name, per_test, args.chains, args.blocks_per_sm)
        except cuda.CudaError as e:
            print(f"  !! skipped: {e}")
            continue
        report(name, tflops, "TFLOPS", s.describe())
        metrics.append(Metric(f"tensor.{name}", tflops, "TFLOPS"))
        metrics += power_metrics(f"tensor.{name}", tflops, s)
        rows.append((name, tflops))

    best = max(rows, key=lambda r: r[1], default=None)
    if best:
        print(f"\nPeak: {best[1]:.1f} TFLOPS ({best[0]}) = {best[1] / 1000:.3f} PFLOPS")
    summary("Tensor Peak Summary", [m for m in metrics if m.unit == "TFLOPS"])
    return metrics
