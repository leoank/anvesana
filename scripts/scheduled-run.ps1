<#
.SYNOPSIS
    Scheduled node-health run for Windows: sync dependencies, run the suite, health-check it.
.DESCRIPTION
    Exit code 0 = healthy, 1 = a benchmark failed or regressed beyond tolerance.
    Register monthly (first Sunday 03:00) with:

      schtasks /Create /TN "anvesana-monthly" /SC MONTHLY /MO FIRST /D SUN /ST 03:00 /RL HIGHEST `
        /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\path\to\anvesana\scripts\scheduled-run.ps1"

    Set ANVESANA_RESULTS_DIR (machine-wide) to the shared results store first.
#>
param([string]$Machine = "", [string]$Tag = "")

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

uv sync --extra tensorrt --extra cutlass --quiet
$cmdArgs = @("run", "bench", "run", "--health")
if ($Machine) { $cmdArgs += @("--machine", $Machine) }
if ($Tag) { $cmdArgs += @("--tag", $Tag) }
& uv @cmdArgs
exit $LASTEXITCODE
