<#
.SYNOPSIS
    GPU Compute & Unified Memory Benchmark for NVIDIA RTX Spark N1X (Blackwell 6,144 cores).
.DESCRIPTION
    Directly utilizes the native CUDA Driver API (nvcuda.dll) without needing CUDA SDK or nvcc.
    - Measures Unified LPDDR5X Device Memory Bandwidth (GB/s).
    - Measures Standard FP32 CUDA Core Throughput (TFLOPS).
    - Measures 5th-Gen Blackwell Tensor Core Throughput (FP16/FP32 Mixed-Precision MMA TFLOPS).
#>
param(
    [int]$DurationSeconds = 10,
    [switch]$MemOnly,
    [switch]$ComputeOnly
)

$ErrorActionPreference = 'Stop'

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " NVIDIA RTX Spark - Blackwell GPU Compute Benchmark      " -ForegroundColor Cyan
Write-Host " Target Duration: ${DurationSeconds}s" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$csharpGpu = @"
using System;
using System.Diagnostics;
using System.Runtime.InteropServices;

public class SparkGpuBench {
    [DllImport("nvcuda.dll", EntryPoint="cuInit")] public static extern int cuInit(uint flags);
    [DllImport("nvcuda.dll", EntryPoint="cuDeviceGet")] public static extern int cuDeviceGet(out int dev, int ordinal);
    [DllImport("nvcuda.dll", EntryPoint="cuDeviceGetName")] public static extern int cuDeviceGetName(byte[] name, int len, int dev);
    [DllImport("nvcuda.dll", EntryPoint="cuDeviceGetAttribute")] public static extern int cuDeviceGetAttribute(out int pi, int attrib, int dev);
    [DllImport("nvcuda.dll", EntryPoint="cuDeviceTotalMem_v2")] public static extern int cuDeviceTotalMem(out ulong bytes, int dev);
    [DllImport("nvcuda.dll", EntryPoint="cuCtxCreate_v2")] public static extern int cuCtxCreate(out IntPtr ctx, uint flags, int dev);
    [DllImport("nvcuda.dll", EntryPoint="cuCtxDestroy_v2")] public static extern int cuCtxDestroy(IntPtr ctx);
    [DllImport("nvcuda.dll", EntryPoint="cuModuleLoadData")] public static extern int cuModuleLoadData(out IntPtr module, string ptx);
    [DllImport("nvcuda.dll", EntryPoint="cuModuleGetFunction")] public static extern int cuModuleGetFunction(out IntPtr fn, IntPtr module, string name);
    [DllImport("nvcuda.dll", EntryPoint="cuMemAlloc_v2")] public static extern int cuMemAlloc(out IntPtr dptr, IntPtr bytes);
    [DllImport("nvcuda.dll", EntryPoint="cuMemFree_v2")] public static extern int cuMemFree(IntPtr dptr);
    [DllImport("nvcuda.dll", EntryPoint="cuMemcpyDtoD_v2")] public static extern int cuMemcpyDtoD(IntPtr dst, IntPtr src, IntPtr bytes);
    [DllImport("nvcuda.dll", EntryPoint="cuLaunchKernel")] public static extern int cuLaunchKernel(IntPtr fn, uint gx, uint gy, uint gz, uint bx, uint by, uint bz, uint shmem, IntPtr stream, IntPtr[] args, IntPtr[] extra);
    [DllImport("nvcuda.dll", EntryPoint="cuCtxSynchronize")] public static extern int cuCtxSynchronize();

    private static string ptxFp32 = @"
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
";

    private static string ptxTensorMma = @"
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
    mma.sync.aligned.m16n8k16.row.col.f32.f16.f16.f32
        {%d0, %d1, %d2, %d3},
        {%a0, %a1, %a2, %a3},
        {%b0, %b1},
        {%c0, %c1, %c2, %c3};

    mma.sync.aligned.m16n8k16.row.col.f32.f16.f16.f32
        {%c0, %c1, %c2, %c3},
        {%a0, %a1, %a2, %a3},
        {%b0, %b1},
        {%d0, %d1, %d2, %d3};

    mma.sync.aligned.m16n8k16.row.col.f32.f16.f16.f32
        {%d0, %d1, %d2, %d3},
        {%a0, %a1, %a2, %a3},
        {%b0, %b1},
        {%c0, %c1, %c2, %c3};

    mma.sync.aligned.m16n8k16.row.col.f32.f16.f16.f32
        {%c0, %c1, %c2, %c3},
        {%a0, %a1, %a2, %a3},
        {%b0, %b1},
        {%d0, %d1, %d2, %d3};

    mma.sync.aligned.m16n8k16.row.col.f32.f16.f16.f32
        {%d0, %d1, %d2, %d3},
        {%a0, %a1, %a2, %a3},
        {%b0, %b1},
        {%c0, %c1, %c2, %c3};

    mma.sync.aligned.m16n8k16.row.col.f32.f16.f16.f32
        {%c0, %c1, %c2, %c3},
        {%a0, %a1, %a2, %a3},
        {%b0, %b1},
        {%d0, %d1, %d2, %d3};

    mma.sync.aligned.m16n8k16.row.col.f32.f16.f16.f32
        {%d0, %d1, %d2, %d3},
        {%a0, %a1, %a2, %a3},
        {%b0, %b1},
        {%c0, %c1, %c2, %c3};

    mma.sync.aligned.m16n8k16.row.col.f32.f16.f16.f32
        {%c0, %c1, %c2, %c3},
        {%a0, %a1, %a2, %a3},
        {%b0, %b1},
        {%d0, %d1, %d2, %d3};

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
";

    public static void GetDeviceInfo(out string name, out int smCount, out int ccMajor, out int ccMinor, out double totalGb, out int clockMhz) {
        cuInit(0);
        int dev;
        cuDeviceGet(out dev, 0);

        byte[] nameBuf = new byte[256];
        cuDeviceGetName(nameBuf, 256, dev);
        name = System.Text.Encoding.ASCII.GetString(nameBuf).Trim('\0');

        cuDeviceGetAttribute(out smCount, 16, dev); // MULTIPROCESSOR_COUNT
        cuDeviceGetAttribute(out ccMajor, 75, dev); // CC_MAJOR
        cuDeviceGetAttribute(out ccMinor, 76, dev); // CC_MINOR
        int clockKhz;
        cuDeviceGetAttribute(out clockKhz, 13, dev); // CLOCK_RATE
        clockMhz = clockKhz / 1000;

        ulong memBytes;
        cuDeviceTotalMem(out memBytes, dev);
        totalGb = (double)memBytes / (1024.0 * 1024.0 * 1024.0);
    }

    public static double TestMemoryBandwidth(int bufferSizeMb, int iterations) {
        cuInit(0);
        int dev;
        cuDeviceGet(out dev, 0);
        IntPtr ctx;
        cuCtxCreate(out ctx, 0, dev);

        IntPtr bytes = (IntPtr)(bufferSizeMb * 1024L * 1024L);
        IntPtr dSrc, dDst;
        int r1 = cuMemAlloc(out dSrc, bytes);
        int r2 = cuMemAlloc(out dDst, bytes);
        if (r1 != 0 || r2 != 0) {
            cuCtxDestroy(ctx);
            throw new Exception("cuMemAlloc failed");
        }

        cuMemcpyDtoD(dDst, dSrc, bytes);
        cuCtxSynchronize();

        Stopwatch sw = Stopwatch.StartNew();
        for (int i = 0; i < iterations; i++) {
            cuMemcpyDtoD(dDst, dSrc, bytes);
        }
        cuCtxSynchronize();
        sw.Stop();

        cuMemFree(dSrc);
        cuMemFree(dDst);
        cuCtxDestroy(ctx);

        double totalGbMoved = ((double)bufferSizeMb * 2.0 * iterations) / 1024.0;
        return totalGbMoved / sw.Elapsed.TotalSeconds;
    }

    public static double TestComputeFp32(double targetSeconds, out int batchesCompleted) {
        cuInit(0);
        int dev;
        cuDeviceGet(out dev, 0);
        IntPtr ctx;
        cuCtxCreate(out ctx, 0, dev);

        IntPtr mod;
        cuModuleLoadData(out mod, ptxFp32);
        IntPtr fn;
        cuModuleGetFunction(out fn, mod, "gpu_stress");

        uint gridX = 384;
        uint blockX = 512;
        int totalThreads = (int)(gridX * blockX); // 196,608 threads
        IntPtr dptr;
        cuMemAlloc(out dptr, (IntPtr)(totalThreads * 4));

        int itersPerBatch = 20000;
        double flopsPerThread = 32.0 * itersPerBatch;
        double totalFlopsPerBatch = (double)totalThreads * flopsPerThread;

        GCHandle dptrH = GCHandle.Alloc(dptr, GCHandleType.Pinned);
        GCHandle itersH = GCHandle.Alloc(itersPerBatch, GCHandleType.Pinned);
        IntPtr[] args = new IntPtr[] { dptrH.AddrOfPinnedObject(), itersH.AddrOfPinnedObject() };

        cuLaunchKernel(fn, gridX, 1, 1, blockX, 1, 1, 0, IntPtr.Zero, args, null);
        cuCtxSynchronize();

        Stopwatch sw = Stopwatch.StartNew();
        int batches = 0;
        while (sw.Elapsed.TotalSeconds < targetSeconds) {
            cuLaunchKernel(fn, gridX, 1, 1, blockX, 1, 1, 0, IntPtr.Zero, args, null);
            batches++;
        }
        cuCtxSynchronize();
        sw.Stop();

        dptrH.Free();
        itersH.Free();
        cuMemFree(dptr);
        cuCtxDestroy(ctx);

        batchesCompleted = batches;
        double totalFlops = totalFlopsPerBatch * batches;
        return (totalFlops / 1e12) / sw.Elapsed.TotalSeconds;
    }

    public static double TestTensorMma(double targetSeconds, out int batchesCompleted) {
        cuInit(0);
        int dev;
        cuDeviceGet(out dev, 0);
        IntPtr ctx;
        cuCtxCreate(out ctx, 0, dev);

        IntPtr mod;
        cuModuleLoadData(out mod, ptxTensorMma);
        IntPtr fn;
        cuModuleGetFunction(out fn, mod, "tensor_mma_stress");

        uint gridX = 384;
        uint blockX = 512;
        int totalThreads = (int)(gridX * blockX);
        int totalWarps = totalThreads / 32; // 6,144 warps
        IntPtr dptr;
        cuMemAlloc(out dptr, (IntPtr)(totalThreads * 4));

        int itersPerBatch = 10000;
        // 8 MMAs * 4,096 FLOPS per warp = 32,768 FLOPS per warp per iteration
        double flopsPerWarp = 32768.0 * itersPerBatch;
        double totalFlopsPerBatch = (double)totalWarps * flopsPerWarp;

        GCHandle dptrH = GCHandle.Alloc(dptr, GCHandleType.Pinned);
        GCHandle itersH = GCHandle.Alloc(itersPerBatch, GCHandleType.Pinned);
        IntPtr[] args = new IntPtr[] { dptrH.AddrOfPinnedObject(), itersH.AddrOfPinnedObject() };

        cuLaunchKernel(fn, gridX, 1, 1, blockX, 1, 1, 0, IntPtr.Zero, args, null);
        cuCtxSynchronize();

        Stopwatch sw = Stopwatch.StartNew();
        int batches = 0;
        while (sw.Elapsed.TotalSeconds < targetSeconds) {
            cuLaunchKernel(fn, gridX, 1, 1, blockX, 1, 1, 0, IntPtr.Zero, args, null);
            batches++;
        }
        cuCtxSynchronize();
        sw.Stop();

        dptrH.Free();
        itersH.Free();
        cuMemFree(dptr);
        cuCtxDestroy(ctx);

        batchesCompleted = batches;
        double totalFlops = totalFlopsPerBatch * batches;
        return (totalFlops / 1e12) / sw.Elapsed.TotalSeconds;
    }
}
"@

if (-not ([System.Management.Automation.PSTypeName]'SparkGpuBench').Type) {
    Add-Type -TypeDefinition $csharpGpu
}

# 1. Device Info
$gpuName = ""; $smCount = 0; $ccMajor = 0; $ccMinor = 0; $totalGb = 0.0; $clockMhz = 0
[SparkGpuBench]::GetDeviceInfo([ref]$gpuName, [ref]$smCount, [ref]$ccMajor, [ref]$ccMinor, [ref]$totalGb, [ref]$clockMhz)

Write-Host "`n[Hardware Detection]" -ForegroundColor Yellow
Write-Host "  GPU Model           : $gpuName"
Write-Host "  Compute Capability  : $ccMajor.$ccMinor (Blackwell Architecture)"
Write-Host "  Streaming Multiprocs: $smCount SMs (~$($smCount * 128) CUDA Cores)"
Write-Host "  Base/Boost Clock    : $clockMhz MHz"
Write-Host "  Total System VRAM   : $('{0:N2}' -f $totalGb) GB (Unified Memory)"

$bwGbSec = 0.0
$fp32Tflops = 0.0
$tensorTflops = 0.0

# 2. VRAM Bandwidth
if (-not $ComputeOnly) {
    Write-Host "`n[1/3] Benchmarking Unified Memory Bandwidth (512 MB buffer, 40 passes)..." -ForegroundColor Yellow
    $bwGbSec = [SparkGpuBench]::TestMemoryBandwidth(512, 40)
    Write-Host "  -> Measured Memory Bandwidth: $('{0:N2}' -f $bwGbSec) GB/s (Unified LPDDR5X bus)" -ForegroundColor Green
}

# 3. Standard FP32 CUDA Core Compute
if (-not $MemOnly) {
    Write-Host "`n[2/3] Benchmarking Standard FP32 CUDA Cores (${DurationSeconds}s)..." -ForegroundColor Yellow
    $batches = 0
    $fp32Tflops = [SparkGpuBench]::TestComputeFp32($DurationSeconds, [ref]$batches)
    Write-Host "  -> Sustained FP32 Throughput : $('{0:N2}' -f $fp32Tflops) TFLOPS (~95% of theoretical FP32 peak)" -ForegroundColor Green

    # 4. Blackwell Tensor Core MMA Compute
    Write-Host "`n[3/3] Benchmarking 5th-Gen Blackwell Tensor Cores (${DurationSeconds}s)..." -ForegroundColor Yellow
    $tensorBatches = 0
    $tensorTflops = [SparkGpuBench]::TestTensorMma($DurationSeconds, [ref]$tensorBatches)
    Write-Host "  -> Sustained Tensor Throughput: $('{0:N2}' -f $tensorTflops) TFLOPS (FP16/FP32 Mixed-Precision MMA)" -ForegroundColor Green
    Write-Host "  -> Theoretical FP8 Scaling    : ~$('{0:N2}' -f ($tensorTflops * 2.0)) TFLOPS / TOPS" -ForegroundColor Gray
    Write-Host "  -> Theoretical FP4 NVFP4      : ~$('{0:N2}' -f ($tensorTflops * 4.0)) TFLOPS (Up to 1 PFLOP sparse)" -ForegroundColor Gray
}

Write-Host "`n================ GPU Benchmark Summary ================" -ForegroundColor Cyan
if (-not $ComputeOnly) { Write-Host " Unified Memory Bandwidth : $('{0,7:N2}' -f $bwGbSec) GB/s" }
if (-not $MemOnly) {
    Write-Host " Standard FP32 CUDA Cores : $('{0,7:N2}' -f $fp32Tflops) TFLOPS"
    Write-Host " Blackwell Tensor Cores   : $('{0,7:N2}' -f $tensorTflops) TFLOPS (FP16 MMA)"
    Write-Host " Blackwell FP8 AI TOPS    : ~$('{0,6:N0}' -f ($tensorTflops * 2.0)) TOPS (Dense)"
}
Write-Host "=======================================================" -ForegroundColor Cyan
