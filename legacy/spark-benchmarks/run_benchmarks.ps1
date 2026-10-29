param(
    [int]$DurationSeconds = 30,
    [string]$Timestamp = ""
)

$ErrorActionPreference = 'SilentlyContinue'

if (-not $Timestamp) {
    $Timestamp = (Get-Date).ToString("yyyyMMdd_HHmmss")
}

$dir = Join-Path $env:USERPROFILE "benchmarks"
Set-Location $dir
$metricFile = "$dir\metrics_windows_${Timestamp}.csv"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " NVIDIA RTX Spark - Windows Benchmark Orchestrator       " -ForegroundColor Cyan
Write-Host " Duration: ${DurationSeconds}s | Telemetry: $metricFile  " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Start background telemetry monitor
Write-Host "`n[1/6] Launching background telemetry logger..." -ForegroundColor Yellow
$monitorJob = Start-Job -ScriptBlock {
    param($outFile, $workDir)
    Set-Location $workDir
    & powershell.exe -ExecutionPolicy Bypass -File .\monitor_system.ps1 -OutputFile $outFile -IntervalMs 1000
} -ArgumentList $metricFile, $dir

# 2. Baseline
Write-Host "[2/6] Recording 5s baseline (idle)..." -ForegroundColor Gray
Start-Sleep -Seconds 5

# 3. CPU & Memory Stress
Write-Host "[3/6] Executing CPU & Memory stress test (${DurationSeconds}s)..." -ForegroundColor Yellow
& powershell.exe -ExecutionPolicy Bypass -File .\stress_cpu_ram.ps1 -DurationSeconds $DurationSeconds

# 4. Blackwell GPU Compute Benchmark
Write-Host "`n[4/6] Executing Blackwell GPU Benchmark (${DurationSeconds}s)..." -ForegroundColor Yellow
& powershell.exe -ExecutionPolicy Bypass -File .\stress_gpu.ps1 -DurationSeconds $DurationSeconds

# 5. NVMe Disk Benchmark
Write-Host "`n[5/6] Executing NVMe Storage benchmark..." -ForegroundColor Yellow
& powershell.exe -ExecutionPolicy Bypass -File .\stress_disk.ps1

# 6. Cooldown
Write-Host "`n[6/6] Recording 5s cooldown (thermal descent)..." -ForegroundColor Gray
Start-Sleep -Seconds 5

# Stop telemetry job
Stop-Job $monitorJob
Remove-Job $monitorJob -Force
Write-Host "`nBenchmark run complete! Results written to $metricFile" -ForegroundColor Green
