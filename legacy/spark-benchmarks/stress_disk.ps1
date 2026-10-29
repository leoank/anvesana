<#
.SYNOPSIS
    NVMe Storage Benchmark for Windows on ARM (bypasses Windows filesystem cache).
.DESCRIPTION
    Measures Sequential Read/Write throughput and Random 4K Read/Write IOPS & latency
    using unbuffered FileStream operations (FileOptions.WriteThrough).
#>
param(
    [string]$TestPath = (Join-Path $env:USERPROFILE "disk_bench_temp.dat"),
    [int]$SeqSizeMB = 1024,
    [int]$RandOps = 5000
)

$ErrorActionPreference = 'Stop'

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " NVIDIA RTX Spark - NVMe Storage Benchmark (Samsung 2TB)  " -ForegroundColor Cyan
Write-Host " Target File: $TestPath" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$csharpDisk = @"
using System;
using System.IO;
using System.Diagnostics;

public class DiskBench {
    public static double TestSeqWrite(string path, int totalMb, int blockMb) {
        int bufferSize = blockMb * 1024 * 1024;
        byte[] buffer = new byte[bufferSize];
        for (int i = 0; i < bufferSize; i += 4096) buffer[i] = 0xAA;
        int blocks = totalMb / blockMb;

        Stopwatch sw = Stopwatch.StartNew();
        using (FileStream fs = new FileStream(path, FileMode.Create, FileAccess.Write, FileShare.None, 4096, FileOptions.WriteThrough)) {
            for (int b = 0; b < blocks; b++) {
                fs.Write(buffer, 0, bufferSize);
            }
            fs.Flush(true);
        }
        sw.Stop();
        return (double)totalMb / sw.Elapsed.TotalSeconds;
    }

    public static double TestSeqRead(string path, int totalMb, int blockMb) {
        int bufferSize = blockMb * 1024 * 1024;
        byte[] buffer = new byte[bufferSize];
        int blocks = totalMb / blockMb;

        Stopwatch sw = Stopwatch.StartNew();
        using (FileStream fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.None, 4096, FileOptions.SequentialScan)) {
            for (int b = 0; b < blocks; b++) {
                fs.Read(buffer, 0, bufferSize);
            }
        }
        sw.Stop();
        return (double)totalMb / sw.Elapsed.TotalSeconds;
    }

    public static void TestRandom4K(string path, int numOps, out double writeIops, out double writeLatencyMs, out double readIops, out double readLatencyMs) {
        byte[] block4k = new byte[4096];
        for (int i = 0; i < 4096; i++) block4k[i] = 0x55;
        
        long fileSize = new FileInfo(path).Length;
        long maxOffsetBlocks = (fileSize / 4096) - 1;
        Random rnd = new Random(42);

        long[] offsets = new long[numOps];
        for (int i = 0; i < numOps; i++) {
            offsets[i] = (long)(rnd.NextDouble() * maxOffsetBlocks) * 4096;
        }

        // Random 4K Writes
        Stopwatch swWrite = Stopwatch.StartNew();
        using (FileStream fs = new FileStream(path, FileMode.Open, FileAccess.Write, FileShare.None, 4096, FileOptions.WriteThrough)) {
            for (int i = 0; i < numOps; i++) {
                fs.Position = offsets[i];
                fs.Write(block4k, 0, 4096);
            }
            fs.Flush(true);
        }
        swWrite.Stop();
        writeIops = numOps / swWrite.Elapsed.TotalSeconds;
        writeLatencyMs = (swWrite.Elapsed.TotalSeconds * 1000.0) / numOps;

        // Random 4K Reads
        Stopwatch swRead = Stopwatch.StartNew();
        using (FileStream fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.None, 4096, FileOptions.RandomAccess)) {
            for (int i = 0; i < numOps; i++) {
                fs.Position = offsets[i];
                fs.Read(block4k, 0, 4096);
            }
        }
        swRead.Stop();
        readIops = numOps / swRead.Elapsed.TotalSeconds;
        readLatencyMs = (swRead.Elapsed.TotalSeconds * 1000.0) / numOps;
    }
}
"@

if (-not ([System.Management.Automation.PSTypeName]'DiskBench').Type) {
    Add-Type -TypeDefinition $csharpDisk
}

try {
    # 1. Sequential Write
    Write-Host "`n[1/4] Sequential Write ($SeqSizeMB MB, unbuffered direct I/O)..." -ForegroundColor Yellow
    $seqWriteMbSec = [DiskBench]::TestSeqWrite($TestPath, $SeqSizeMB, 4)
    Write-Host "  -> Sequential Write: $([math]::Round($seqWriteMbSec, 2)) MB/s" -ForegroundColor Green

    # 2. Sequential Read
    Write-Host "`n[2/4] Sequential Read ($SeqSizeMB MB)..." -ForegroundColor Yellow
    $seqReadMbSec = [DiskBench]::TestSeqRead($TestPath, $SeqSizeMB, 4)
    Write-Host "  -> Sequential Read : $([math]::Round($seqReadMbSec, 2)) MB/s" -ForegroundColor Green

    # 3 & 4. Random 4K
    Write-Host "`n[3/4] Random 4KB Write & [4/4] Random 4KB Read ($RandOps ops)..." -ForegroundColor Yellow
    $writeIops = 0.0; $writeLat = 0.0; $readIops = 0.0; $readLat = 0.0
    [DiskBench]::TestRandom4K($TestPath, $RandOps, [ref]$writeIops, [ref]$writeLat, [ref]$readIops, [ref]$readLat)
    
    Write-Host "  -> Random 4K Write : $([math]::Round($writeIops, 0)) IOPS (Latency: $([math]::Round($writeLat, 3)) ms)" -ForegroundColor Green
    Write-Host "  -> Random 4K Read  : $([math]::Round($readIops, 0)) IOPS (Latency: $([math]::Round($readLat, 3)) ms)" -ForegroundColor Green

    Write-Host "`n================ Disk Benchmark Summary ================" -ForegroundColor Cyan
    Write-Host " Sequential Write : $('{0,7:F2}' -f $seqWriteMbSec) MB/s"
    Write-Host " Sequential Read  : $('{0,7:F2}' -f $seqReadMbSec) MB/s"
    Write-Host " Random 4K Write  : $('{0,7:F0}' -f $writeIops) IOPS  (Avg: $([math]::Round($writeLat, 2)) ms)"
    Write-Host " Random 4K Read   : $('{0,7:F0}' -f $readIops) IOPS  (Avg: $([math]::Round($readLat, 2)) ms)"
    Write-Host "=========================================================" -ForegroundColor Cyan
}
finally {
    if (Test-Path $TestPath) {
        Remove-Item -Path $TestPath -Force -ErrorAction SilentlyContinue
    }
}
