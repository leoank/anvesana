<#
.SYNOPSIS
    Real-time telemetry logger for NVIDIA RTX Spark (Blackwell + 20-core ARM64 CPU) on Windows.
.DESCRIPTION
    Logs CPU utilization, SoC temperature, RAM, GPU utilization, VRAM, GPU temperature,
    GPU power draw (Watts), GPU graphics clock, and NPU metrics to CSV every 1s.
#>
param(
    [string]$OutputFile = "metrics_windows.csv",
    [int]$IntervalMs = 1000,
    [int]$DurationSeconds = 0
)

$ErrorActionPreference = 'SilentlyContinue'

$headers = "timestamp_iso,elapsed_sec,cpu_util_pct,soc_temp_c,ram_used_gb,ram_total_gb,ram_pct,gpu_util_pct,gpu_mem_used_mb,gpu_mem_total_mb,gpu_temp_c,gpu_power_w,gpu_clock_mhz,npu_temp_c,npu_power_w"
Set-Content -Path $OutputFile -Value $headers -Encoding ascii

Write-Host "Telemetry Monitor Started -> Output: $OutputFile" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop logging..." -ForegroundColor Gray

$sw = [System.Diagnostics.Stopwatch]::StartNew()
$sampleCount = 0
$peakCpuTemp = 0.0
$peakGpuTemp = 0.0
$peakGpuPower = 0.0
$totalGpuPower = 0.0

try {
    while ($true) {
        if ($DurationSeconds -gt 0 -and $sw.Elapsed.TotalSeconds -ge $DurationSeconds) {
            break
        }

        $now = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss.fff")
        $elapsed = [math]::Round($sw.Elapsed.TotalSeconds, 2)

        # 1. CPU
        $cpu = (Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor -Filter "Name='_Total'").PercentProcessorTime
        if ($null -eq $cpu) { $cpu = 0 }

        # 2. SoC Temp (ACPI Thermal Zone)
        $tz = Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature | Where-Object { $_.InstanceName -like '*TSOC*' } | Select-Object -First 1
        $socTemp = if ($tz) { [math]::Round(($tz.CurrentTemperature - 2732)/10.0, 1) } else { 0.0 }
        if ($socTemp -gt $peakCpuTemp) { $peakCpuTemp = $socTemp }

        # 3. RAM
        $os = Get-CimInstance Win32_OperatingSystem
        $ramTotal = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
        $ramFree = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
        $ramUsed = [math]::Round($ramTotal - $ramFree, 2)
        $ramPct = [math]::Round(($ramUsed / $ramTotal) * 100, 1)

        # 4. GPU 0 (Blackwell RTX)
        $gpuRaw = nvidia-smi -i 0 --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,clocks.current.graphics --format=csv,noheader,nounits 2>$null
        $gpuParts = if ($gpuRaw) { $gpuRaw.Split(',') | ForEach-Object { $_.Trim() } } else { @(0,0,0,0,0,0) }
        $gpuUtil = $gpuParts[0]
        $gpuMemUsed = $gpuParts[1]
        $gpuMemTotal = $gpuParts[2]
        $gpuTemp = [double]$gpuParts[3]
        $gpuPower = [double]$gpuParts[4]
        $gpuClock = $gpuParts[5]

        if ($gpuTemp -gt $peakGpuTemp) { $peakGpuTemp = $gpuTemp }
        if ($gpuPower -gt $peakGpuPower) { $peakGpuPower = $gpuPower }
        $totalGpuPower += $gpuPower
        $sampleCount++

        # 5. GPU 1 (NPU)
        $npuRaw = nvidia-smi -i 1 --query-gpu=temperature.gpu,power.draw --format=csv,noheader,nounits 2>$null
        $npuParts = if ($npuRaw) { $npuRaw.Split(',') | ForEach-Object { $_.Trim() } } else { @(0,0) }
        $npuTemp = $npuParts[0]
        $npuPower = $npuParts[1]

        # Append row
        $row = "$now,$elapsed,$cpu,$socTemp,$ramUsed,$ramTotal,$ramPct,$gpuUtil,$gpuMemUsed,$gpuMemTotal,$gpuTemp,$gpuPower,$gpuClock,$npuTemp,$npuPower"
        Add-Content -Path $OutputFile -Value $row -Encoding ascii

        # Live terminal output
        Write-Host -NoNewline ("`r[{0,5}s] CPU: {1,3}% ({2}C) | RAM: {3}/{4}GB | GPU: {5,3}% ({6}C, {7,5}W, {8}MHz) | NPU: {9}C" -f `
            [math]::Round($elapsed), $cpu, $socTemp, $ramUsed, $ramTotal, $gpuUtil, $gpuTemp, $gpuPower, $gpuClock, $npuTemp)

        Start-Sleep -Milliseconds $IntervalMs
    }
}
finally {
    $sw.Stop()
    $avgGpuPower = if ($sampleCount -gt 0) { [math]::Round($totalGpuPower / $sampleCount, 2) } else { 0 }
    Write-Host "`n`n================ Telemetry Summary ================" -ForegroundColor Cyan
    Write-Host " Total Samples     : $sampleCount ($([math]::Round($sw.Elapsed.TotalSeconds, 1))s)"
    Write-Host " Peak SoC / CPU Temp: ${peakCpuTemp} C"
    Write-Host " Peak GPU Temp     : ${peakGpuTemp} C"
    Write-Host " Peak GPU Power    : ${peakGpuPower} W"
    Write-Host " Avg GPU Power     : ${avgGpuPower} W"
    Write-Host " CSV Log Saved to  : $OutputFile" -ForegroundColor Green
    Write-Host "===================================================" -ForegroundColor Cyan
}
