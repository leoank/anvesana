<#
.SYNOPSIS
    Scheduled node-health run for Windows: install this node's dependencies, run its suite, health-check it.
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

$machineArgs = @()
if ($Machine) { $machineArgs = @("--machine", $Machine) }

# Core packages first (inexact: keep whatever extras are installed), then exactly
# the extras this node's profile needs, from the committed uv.lock.
uv sync --inexact --locked --quiet
uv run --no-sync anvesana setup @machineArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# Hardware / driver inventory: tracks driver and firmware changes between runs. Not fatal.
uv run --no-sync anvesana inventory collect @machineArgs
if ($LASTEXITCODE -ne 0) { Write-Warning "inventory collection failed; continuing with the benchmark run" }

$runArgs = @("run", "--no-sync", "anvesana", "run", "--health") + $machineArgs
if ($Tag) { $runArgs += @("--tag", $Tag) }
& uv @runArgs
exit $LASTEXITCODE
