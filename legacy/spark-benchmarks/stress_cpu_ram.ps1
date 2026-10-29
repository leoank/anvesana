param(
    [int]$DurationSeconds = 30,
    [int]$Threads = 0,
    [switch]$CpuOnly,
    [switch]$MemOnly
)

$ErrorActionPreference = 'Stop'

if ($Threads -le 0) {
    $Threads = (Get-CimInstance Win32_Processor).NumberOfLogicalProcessors
    if ($Threads -le 0) { $Threads = 20 }
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " NVIDIA RTX Spark - CPU & Memory Benchmark / Stress Test " -ForegroundColor Cyan
Write-Host " Threads: $Threads | Target Duration: ${DurationSeconds}s" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# Define high-performance C# benchmark engine
$csharpCode = @"
using System;
using System.Threading;
using System.Threading.Tasks;
using System.Diagnostics;

public class SparkBench {
    public static double RunCpuStress(int durationSeconds, int threadCount, out long totalOps) {
        Stopwatch sw = Stopwatch.StartNew();
        long opsCounter = 0;

        Parallel.For(0, threadCount, new ParallelOptions { MaxDegreeOfParallelism = threadCount }, threadId => {
            Stopwatch threadSw = Stopwatch.StartNew();
            long localOps = 0;
            double a = 1.000001;
            double b = 0.999999;
            double c = 1.5;

            while (threadSw.Elapsed.TotalSeconds < durationSeconds) {
                for (int i = 0; i < 20000; i++) {
                    a = Math.Sqrt(a * b + c) * Math.Sin(a);
                    b = Math.Cos(b * 1.0001) + a * 0.00001;
                }
                localOps += 20000;
            }
            Interlocked.Add(ref opsCounter, localOps);
        });

        sw.Stop();
        totalOps = opsCounter;
        return totalOps / sw.Elapsed.TotalSeconds;
    }

    public static double RunMemBandwidth(int durationSeconds, int threadCount, int bufferSizeMbPerThread, out long totalBytesMoved) {
        int elements = (bufferSizeMbPerThread * 1024 * 1024) / sizeof(long);
        long bytesCounter = 0;
        long bytesPerPass = (long)elements * sizeof(long) * 2; // Read + Write

        Parallel.For(0, threadCount, new ParallelOptions { MaxDegreeOfParallelism = threadCount }, threadId => {
            long[] a = new long[elements];
            long[] b = new long[elements];
            for (int i = 0; i < elements; i++) a[i] = i;

            Stopwatch threadSw = Stopwatch.StartNew();
            long localBytes = 0;

            while (threadSw.Elapsed.TotalSeconds < durationSeconds) {
                // 64-bit unrolled streaming copy
                for (int i = 0; i < elements; i += 8) {
                    b[i]   = a[i];
                    b[i+1] = a[i+1];
                    b[i+2] = a[i+2];
                    b[i+3] = a[i+3];
                    b[i+4] = a[i+4];
                    b[i+5] = a[i+5];
                    b[i+6] = a[i+6];
                    b[i+7] = a[i+7];
                }
                b[0]++;
                localBytes += bytesPerPass;
            }
            Interlocked.Add(ref bytesCounter, localBytes);
        });

        totalBytesMoved = bytesCounter;
        return (double)bytesCounter / (1024.0 * 1024.0 * 1024.0) / durationSeconds;
    }
}
"@

if (-not ([System.Management.Automation.PSTypeName]'SparkBench').Type) {
    Add-Type -TypeDefinition $csharpCode
}

# 1. CPU Stress
if (-not $MemOnly) {
    Write-Host "`n[1/2] Running Multi-threaded CPU Stress ($Threads threads, ${DurationSeconds}s)..." -ForegroundColor Yellow
    $cpuSw = [System.Diagnostics.Stopwatch]::StartNew()
    $totalOps = [long]0
    $opsSec = [SparkBench]::RunCpuStress($DurationSeconds, $Threads, [ref]$totalOps)
    $cpuSw.Stop()

    $mopsSec = [math]::Round($opsSec / 1e6, 2)
    Write-Host "  -> CPU Stress Completed in $([math]::Round($cpuSw.Elapsed.TotalSeconds, 2))s" -ForegroundColor Green
    Write-Host "  -> Total Operations: $('{0:N0}' -f $totalOps)" -ForegroundColor Green
    Write-Host "  -> Throughput Score: $mopsSec Million Math Ops/sec (MOps/s)" -ForegroundColor Green -NoNewline
    Write-Host " ($([math]::Round($mopsSec / $Threads, 2)) MOps/s per core)" -ForegroundColor Gray
}

# 2. Memory Stress
if (-not $CpuOnly) {
    Write-Host "`n[2/2] Running Multi-threaded Memory Bandwidth Stress ($Threads threads, ${DurationSeconds}s)..." -ForegroundColor Yellow
    $memSw = [System.Diagnostics.Stopwatch]::StartNew()
    $totalBytes = [long]0
    $gbSec = [SparkBench]::RunMemBandwidth($DurationSeconds, $Threads, 64, [ref]$totalBytes)
    $memSw.Stop()

    $totalGb = [math]::Round($totalBytes / 1GB, 2)
    Write-Host "  -> Memory Stress Completed in $([math]::Round($memSw.Elapsed.TotalSeconds, 2))s" -ForegroundColor Green
    Write-Host "  -> Total Data Streamed: $totalGb GB" -ForegroundColor Green
    Write-Host "  -> Memory Bandwidth: $([math]::Round($gbSec, 2)) GB/s" -ForegroundColor Green
}

Write-Host "`nAll tests completed successfully." -ForegroundColor Cyan
