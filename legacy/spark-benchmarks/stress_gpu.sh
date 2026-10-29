#!/usr/bin/env bash
#
# Blackwell GPU Compute & Unified Memory Benchmark for Linux (aarch64)
# Direct CUDA Driver API via ctypes (zero dependencies, identical to stress_gpu.ps1)
#

set -euo pipefail

DURATION="${1:-10}"

echo "=========================================================="
echo " NVIDIA RTX Spark - Blackwell GPU Compute Benchmark (Linux) "
echo " Target Duration: ${DURATION}s"
echo "=========================================================="

python3 - "$DURATION" << 'EOF'
import sys
import time
import ctypes
from ctypes import c_int, c_uint, c_ulonglong, c_void_p, c_char_p, byref, POINTER

duration_sec = float(sys.argv[1])

libcuda = None
for lib_name in ["libcuda.so.1", "libcuda.so", "/usr/lib/aarch64-linux-gnu/libcuda.so.1"]:
    try:
        libcuda = ctypes.CDLL(lib_name)
        break
    except OSError:
        continue

if not libcuda:
    print("ERROR: libcuda.so.1 not found. Ensure NVIDIA drivers are installed.")
    sys.exit(1)

libcuda.cuInit.argtypes = [c_uint]; libcuda.cuInit.restype = c_int
libcuda.cuDeviceGet.argtypes = [POINTER(c_int), c_int]; libcuda.cuDeviceGet.restype = c_int
libcuda.cuDeviceGetName.argtypes = [c_char_p, c_int, c_int]; libcuda.cuDeviceGetName.restype = c_int
libcuda.cuDeviceGetAttribute.argtypes = [POINTER(c_int), c_int, c_int]; libcuda.cuDeviceGetAttribute.restype = c_int
libcuda.cuDeviceTotalMem_v2.argtypes = [POINTER(c_ulonglong), c_int]; libcuda.cuDeviceTotalMem_v2.restype = c_int
libcuda.cuCtxCreate_v2.argtypes = [POINTER(c_void_p), c_uint, c_int]; libcuda.cuCtxCreate_v2.restype = c_int
libcuda.cuCtxDestroy_v2.argtypes = [c_void_p]; libcuda.cuCtxDestroy_v2.restype = c_int
libcuda.cuModuleLoadData.argtypes = [POINTER(c_void_p), c_char_p]; libcuda.cuModuleLoadData.restype = c_int
libcuda.cuModuleGetFunction.argtypes = [POINTER(c_void_p), c_void_p, c_char_p]; libcuda.cuModuleGetFunction.restype = c_int
libcuda.cuMemAlloc_v2.argtypes = [POINTER(c_void_p), c_ulonglong]; libcuda.cuMemAlloc_v2.restype = c_int
libcuda.cuMemFree_v2.argtypes = [c_void_p]; libcuda.cuMemFree_v2.restype = c_int
libcuda.cuMemcpyDtoD_v2.argtypes = [c_void_p, c_void_p, c_ulonglong]; libcuda.cuMemcpyDtoD_v2.restype = c_int
libcuda.cuLaunchKernel.argtypes = [c_void_p, c_uint, c_uint, c_uint, c_uint, c_uint, c_uint, c_uint, c_void_p, POINTER(c_void_p), POINTER(c_void_p)]; libcuda.cuLaunchKernel.restype = c_int
libcuda.cuCtxSynchronize.argtypes = []; libcuda.cuCtxSynchronize.restype = c_int

# 1. Device Info
libcuda.cuInit(0)
dev = c_int(0)
libcuda.cuDeviceGet(byref(dev), 0)

name_buf = ctypes.create_string_buffer(256)
libcuda.cuDeviceGetName(name_buf, 256, dev)
gpu_name = name_buf.value.decode('ascii')

sm_count = c_int(0); libcuda.cuDeviceGetAttribute(byref(sm_count), 16, dev)
cc_major = c_int(0); libcuda.cuDeviceGetAttribute(byref(cc_major), 75, dev)
cc_minor = c_int(0); libcuda.cuDeviceGetAttribute(byref(cc_minor), 76, dev)
clock_khz = c_int(0); libcuda.cuDeviceGetAttribute(byref(clock_khz), 13, dev)
total_mem = c_ulonglong(0); libcuda.cuDeviceTotalMem_v2(byref(total_mem), dev)

print("\n[Hardware Detection]")
print(f"  GPU Model           : {gpu_name}")
print(f"  Compute Capability  : {cc_major.value}.{cc_minor.value} (Blackwell Architecture)")
print(f"  Streaming Multiprocs: {sm_count.value} SMs (~{sm_count.value * 128} CUDA Cores)")
print(f"  Base/Boost Clock    : {clock_khz.value // 1000} MHz")
print(f"  Total System VRAM   : {round(total_mem.value / (1024**3), 2)} GB (Unified Memory)")

# 2. VRAM Bandwidth Test
print("\n[1/3] Benchmarking Unified Memory Bandwidth (512 MB buffer, 40 passes)...")
ctx = c_void_p(0)
libcuda.cuCtxCreate_v2(byref(ctx), 0, dev)

buf_bytes = 512 * 1024 * 1024
d_src = c_void_p(0); d_dst = c_void_p(0)
libcuda.cuMemAlloc_v2(byref(d_src), buf_bytes)
libcuda.cuMemAlloc_v2(byref(d_dst), buf_bytes)

libcuda.cuMemcpyDtoD_v2(d_dst, d_src, buf_bytes)
libcuda.cuCtxSynchronize()

passes = 40
t0 = time.perf_counter()
for _ in range(passes):
    libcuda.cuMemcpyDtoD_v2(d_dst, d_src, buf_bytes)
libcuda.cuCtxSynchronize()
dt_mem = time.perf_counter() - t0

libcuda.cuMemFree_v2(d_src)
libcuda.cuMemFree_v2(d_dst)

mem_bw = round(((512.0 * 2.0 * passes) / 1024.0) / dt_mem, 2)
print(f"  -> Measured Memory Bandwidth: {mem_bw} GB/s")

# 3. FP32 CUDA Core Test
print(f"\n[2/3] Benchmarking Standard FP32 CUDA Cores ({duration_sec}s)...")
ptx_fp32 = b"""
.version 7.0
.target sm_70
.address_size 64
.visible .entry gpu_stress(.param .u64 d_out, .param .u32 iters) {
    .reg .u64 %rd<4>; .reg .u32 %r<5>; .reg .f32 %f<18>; .reg .pred %p<2>;
    ld.param.u64 %rd1, [d_out]; ld.param.u32 %r1, [iters];
    mov.u32 %r2, %tid.x; mov.u32 %r3, %ctaid.x; mov.u32 %r4, %ntid.x; mad.lo.u32 %r2, %r3, %r4, %r2;
    mov.f32 %f1, 1.0001; mov.f32 %f2, 1.0002; mov.f32 %f3, 1.0003; mov.f32 %f4, 1.0004; mov.f32 %f5, 0.5001;
    mov.u32 %r3, 0;
L_loop:
    fma.rn.f32 %f1, %f1, %f2, %f5; fma.rn.f32 %f2, %f2, %f3, %f5; fma.rn.f32 %f3, %f3, %f4, %f5; fma.rn.f32 %f4, %f4, %f1, %f5;
    fma.rn.f32 %f1, %f1, %f3, %f5; fma.rn.f32 %f2, %f2, %f4, %f5; fma.rn.f32 %f3, %f3, %f1, %f5; fma.rn.f32 %f4, %f4, %f2, %f5;
    fma.rn.f32 %f1, %f1, %f2, %f5; fma.rn.f32 %f2, %f2, %f3, %f5; fma.rn.f32 %f3, %f3, %f4, %f5; fma.rn.f32 %f4, %f4, %f1, %f5;
    fma.rn.f32 %f1, %f1, %f3, %f5; fma.rn.f32 %f2, %f2, %f4, %f5; fma.rn.f32 %f3, %f3, %f1, %f5; fma.rn.f32 %f4, %f4, %f2, %f5;
    add.u32 %r3, %r3, 1; setp.lt.u32 %p1, %r3, %r1; @%p1 bra L_loop;
    mul.wide.u32 %rd2, %r2, 4; add.u64 %rd3, %rd1, %rd2; add.f32 %f1, %f1, %f2; st.global.f32 [%rd3], %f1; ret;
}
"""
mod_fp32 = c_void_p(0)
libcuda.cuModuleLoadData(byref(mod_fp32), ptx_fp32)
fn_fp32 = c_void_p(0)
libcuda.cuModuleGetFunction(byref(fn_fp32), mod_fp32, b"gpu_stress")

grid_x = 384; block_x = 512; total_threads = grid_x * block_x
dptr_fp32 = c_void_p(0)
libcuda.cuMemAlloc_v2(byref(dptr_fp32), total_threads * 4)
iters_fp32 = c_uint(20000)
flops_per_thread_fp32 = 32.0 * iters_fp32.value
total_flops_batch_fp32 = total_threads * flops_per_thread_fp32

args_fp32 = (c_void_p * 2)(ctypes.cast(byref(dptr_fp32), c_void_p), ctypes.cast(byref(iters_fp32), c_void_p))
libcuda.cuLaunchKernel(fn_fp32, grid_x, 1, 1, block_x, 1, 1, 0, None, args_fp32, None)
libcuda.cuCtxSynchronize()

t_start = time.perf_counter()
batches_fp32 = 0
while (time.perf_counter() - t_start) < duration_sec:
    libcuda.cuLaunchKernel(fn_fp32, grid_x, 1, 1, block_x, 1, 1, 0, None, args_fp32, None)
    batches_fp32 += 1
libcuda.cuCtxSynchronize()
dt_fp32 = time.perf_counter() - t_start
libcuda.cuMemFree_v2(dptr_fp32)
tflops_fp32 = round(((total_flops_batch_fp32 * batches_fp32) / 1e12) / dt_fp32, 2)
print(f"  -> Sustained FP32 Throughput : {tflops_fp32} TFLOPS")

# 4. Blackwell Tensor Core MMA Test
print(f"\n[3/3] Benchmarking 5th-Gen Blackwell Tensor Cores ({duration_sec}s)...")
ptx_mma = b"""
.version 7.8
.target sm_80
.address_size 64
.visible .entry tensor_mma_stress(.param .u64 d_out, .param .u32 iters) {
    .reg .u64 %rd<4>; .reg .u32 %r<5>; .reg .b32 %a<4>, %b<2>; .reg .f32 %c<4>, %d<4>; .reg .pred %p<2>;
    ld.param.u64 %rd1, [d_out]; ld.param.u32 %r1, [iters];
    mov.b32 %a0, 0x3c003c00; mov.b32 %a1, 0x3c003c00; mov.b32 %a2, 0x3c003c00; mov.b32 %a3, 0x3c003c00;
    mov.b32 %b0, 0x3c003c00; mov.b32 %b1, 0x3c003c00;
    mov.f32 %c0, 0.0; mov.f32 %c1, 0.0; mov.f32 %c2, 0.0; mov.f32 %c3, 0.0;
    mov.u32 %r3, 0;
L_loop:
    mma.sync.aligned.m16n8k16.row.col.f32.f16.f16.f32 {%d0, %d1, %d2, %d3}, {%a0, %a1, %a2, %a3}, {%b0, %b1}, {%c0, %c1, %c2, %c3};
    mma.sync.aligned.m16n8k16.row.col.f32.f16.f16.f32 {%c0, %c1, %c2, %c3}, {%a0, %a1, %a2, %a3}, {%b0, %b1}, {%d0, %d1, %d2, %d3};
    mma.sync.aligned.m16n8k16.row.col.f32.f16.f16.f32 {%d0, %d1, %d2, %d3}, {%a0, %a1, %a2, %a3}, {%b0, %b1}, {%c0, %c1, %c2, %c3};
    mma.sync.aligned.m16n8k16.row.col.f32.f16.f16.f32 {%c0, %c1, %c2, %c3}, {%a0, %a1, %a2, %a3}, {%b0, %b1}, {%d0, %d1, %d2, %d3};
    mma.sync.aligned.m16n8k16.row.col.f32.f16.f16.f32 {%d0, %d1, %d2, %d3}, {%a0, %a1, %a2, %a3}, {%b0, %b1}, {%c0, %c1, %c2, %c3};
    mma.sync.aligned.m16n8k16.row.col.f32.f16.f16.f32 {%c0, %c1, %c2, %c3}, {%a0, %a1, %a2, %a3}, {%b0, %b1}, {%d0, %d1, %d2, %d3};
    mma.sync.aligned.m16n8k16.row.col.f32.f16.f16.f32 {%d0, %d1, %d2, %d3}, {%a0, %a1, %a2, %a3}, {%b0, %b1}, {%c0, %c1, %c2, %c3};
    mma.sync.aligned.m16n8k16.row.col.f32.f16.f16.f32 {%c0, %c1, %c2, %c3}, {%a0, %a1, %a2, %a3}, {%b0, %b1}, {%d0, %d1, %d2, %d3};
    add.u32 %r3, %r3, 1; setp.lt.u32 %p1, %r3, %r1; @%p1 bra L_loop;
    mov.u32 %r2, %tid.x; mov.u32 %r3, %ctaid.x; mov.u32 %r4, %ntid.x; mad.lo.u32 %r2, %r3, %r4, %r2;
    mul.wide.u32 %rd2, %r2, 4; add.u64 %rd3, %rd1, %rd2; st.global.f32 [%rd3], %c0; ret;
}
"""
mod_mma = c_void_p(0)
libcuda.cuModuleLoadData(byref(mod_mma), ptx_mma)
fn_mma = c_void_p(0)
libcuda.cuModuleGetFunction(byref(fn_mma), mod_mma, b"tensor_mma_stress")

total_warps = total_threads // 32
dptr_mma = c_void_p(0)
libcuda.cuMemAlloc_v2(byref(dptr_mma), total_threads * 4)
iters_mma = c_uint(10000)
flops_per_warp_mma = 32768.0 * iters_mma.value
total_flops_batch_mma = total_warps * flops_per_warp_mma

args_mma = (c_void_p * 2)(ctypes.cast(byref(dptr_mma), c_void_p), ctypes.cast(byref(iters_mma), c_void_p))
libcuda.cuLaunchKernel(fn_mma, grid_x, 1, 1, block_x, 1, 1, 0, None, args_mma, None)
libcuda.cuCtxSynchronize()

t_start_mma = time.perf_counter()
batches_mma = 0
while (time.perf_counter() - t_start_mma) < duration_sec:
    libcuda.cuLaunchKernel(fn_mma, grid_x, 1, 1, block_x, 1, 1, 0, None, args_mma, None)
    batches_mma += 1
libcuda.cuCtxSynchronize()
dt_mma = time.perf_counter() - t_start_mma

libcuda.cuMemFree_v2(dptr_mma)
libcuda.cuCtxDestroy_v2(ctx)

tflops_mma = round(((total_flops_batch_mma * batches_mma) / 1e12) / dt_mma, 2)
print(f"  -> Sustained Tensor Throughput: {tflops_mma} TFLOPS (FP16/FP32 Mixed-Precision MMA)")
print(f"  -> Theoretical FP8 Scaling    : ~{round(tflops_mma * 2.0, 2)} TFLOPS / TOPS")
print(f"  -> Theoretical FP4 NVFP4      : ~{round(tflops_mma * 4.0, 2)} TFLOPS (Up to 1 PFLOP sparse)")

print("\n================ GPU Benchmark Summary ================")
print(f" Unified Memory Bandwidth : {mem_bw:7.2f} GB/s")
print(f" Standard FP32 CUDA Cores : {tflops_fp32:7.2f} TFLOPS")
print(f" Blackwell Tensor Cores   : {tflops_mma:7.2f} TFLOPS (FP16 MMA)")
print(f" Blackwell FP8 AI TOPS    : ~{round(tflops_mma * 2.0):6d} TOPS (Dense)")
print("=======================================================")
EOF
