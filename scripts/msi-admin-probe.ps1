<#
.SYNOPSIS
    Admin-only probes of MSI platform controls, for Linux bring-up (see docs/n1x-bringup-log.md §5).
.DESCRIPTION
    Read-only. Run from an elevated PowerShell on the MSI laptop; it guides you through each step:

      1. MSI_ACPI getters (Get_WMI, Get_EC, Get_Fan, ...): dump the raw 32-byte packages, together with
         MSI Center's own registry view of the current mode.
      2. Mode mapping: switch User Scenario / fan mode in MSI Center when prompted; each switch gets its
         own dump, so the bytes that change identify the EC fields behind each mode.
      3. Mystic Light: a USB ETW trace (USBXHCI / UCX / USBHUB3) while you change the keyboard lighting
         in MSI Center; converted to XML. It shows which reports go to 1462:1609 and in what order, but
         Windows' USB ETW providers do not log HID control-transfer payloads (see
         docs/n1x-bringup-log.md for the protocol, read from MSI's code instead).

    Nothing is written to the EC or WMI: only Get_* methods are called. Output goes to -OutDir.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\msi-admin-probe.ps1 -OutDir C:\temp\msi-probe
#>
param(
    [string]$OutDir = (Join-Path $HOME "anvesana-results\$env:COMPUTERNAME\admin-probe\$(Get-Date -Format yyyy-MM-dd_HHmmss)"),
    [switch]$SkipModes,
    [switch]$SkipUsb
)

$ErrorActionPreference = "Stop"
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this from an elevated (Administrator) PowerShell."
}
New-Item -ItemType Directory -Force $OutDir | Out-Null
Start-Transcript -Path (Join-Path $OutDir "transcript.txt") | Out-Null

$Getters = 'Get_WMI', 'Get_EC', 'Get_EC2', 'Get_AP', 'Get_Fan', 'Get_Thermal', 'Get_Temperature', 'Get_Power',
           'Get_Device', 'Get_Data', 'Get_MasterBattery', 'Get_Debug', 'Get_PE'
$ScenarioKey = 'HKLM:\SOFTWARE\WOW6432Node\MSI\MSI Center S\Component\Base Module'

function Get-MsiState([string]$Label) {
    $acpi = Get-WmiObject -Namespace root\wmi -Class MSI_ACPI | Select-Object -First 1
    $calls = [ordered]@{}
    foreach ($m in $Getters) {
        try {
            # In and out are both a Package_32 named Data; byte 0 of the input selects a sub-function
            # on some methods, so all-zero is the plain query.
            # Get_WMI / Get_EC / Get_EC2 take no input at all.
            $in = $acpi.GetMethodParameters($m)
            if ($in -and $in.Properties['Data']) {
                $pkg = ([wmiclass]'root\wmi:Package_32').CreateInstance()
                $pkg.Bytes = [byte[]]::new(32)
                $in.Data = $pkg
            } else { $in = $null }
            $out = $acpi.InvokeMethod($m, $in, $null)
            $calls[$m] = (($out.Data.Bytes | ForEach-Object { '{0:x2}' -f $_ }) -join ' ')
        } catch { $calls[$m] = "ERROR: $($_.Exception.Message.Trim())" }
    }
    $reg = [ordered]@{}
    foreach ($sub in 'User Scenario', 'GeneralSetting') {
        $p = Get-ItemProperty (Join-Path $ScenarioKey $sub) -ErrorAction SilentlyContinue
        if ($p) { $reg[$sub] = $p.PSObject.Properties | Where-Object Name -notlike 'PS*' |
                    ForEach-Object -Begin { $h = [ordered]@{} } -Process { $h[$_.Name] = $_.Value } -End { $h } }
    }
    $state = [ordered]@{ label = $Label; time = (Get-Date).ToString('o'); wmi = $calls; registry = $reg
                         power_overlay = (powercfg /getactivescheme) -join ' ' }
    $file = Join-Path $OutDir ("wmi_{0:D2}_{1}.json" -f $script:n, ($Label -replace '[^\w-]', '_'))
    $state | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 $file
    $script:n++
    Write-Host "  saved $file"
    $calls.GetEnumerator() | ForEach-Object { Write-Host ("  {0,-18} {1}" -f $_.Key, $_.Value) }
}

$script:n = 0
Write-Host "`n== 1. MSI_ACPI getters (current state)" -ForegroundColor Cyan
Get-MsiState "baseline"

if (-not $SkipModes) {
    Write-Host "`n== 2. Mode mapping" -ForegroundColor Cyan
    Write-Host "Open MSI Center S > Features > User Scenario. For each mode it offers (e.g. Super Battery,"
    Write-Host "Silent, Balanced, High/Extreme Performance, Smart Auto) and each fan option (Auto, Advanced,"
    Write-Host "Cooler Boost): select it, wait ~5 s, then type a short label here. Empty line to finish."
    while ($true) {
        $label = Read-Host "label of the mode you just selected"
        if (-not $label) { break }
        Get-MsiState $label
    }
}

if (-not $SkipUsb) {
    Write-Host "`n== 3. Mystic Light USB trace" -ForegroundColor Cyan
    $etl = Join-Path $OutDir "usbtrace.etl"
    logman create trace -n anv_usbtrace -o $etl -nb 128 640 -bs 128 -ow | Out-Null
    # PartialDataBusTrace logs only setup packets for HID control transfers; payloads need Full.
    foreach ($p in 'Microsoft-Windows-USB-USBXHCI', 'Microsoft-Windows-USB-UCX', 'Microsoft-Windows-USB-USBHUB3') {
        logman update trace -n anv_usbtrace -p $p "(Default,FullDataBusTrace)" | Out-Null
    }
    logman start -n anv_usbtrace | Out-Null
    Write-Host "Tracing. In MSI Center S > Mystic Light, in this order, pausing ~3 s after each:"
    Write-Host "  Off, Steady red (255,0,0), Steady green (0,255,0), Steady blue (0,0,255), Breath, Color Cycle"
    Read-Host "Press Enter when done" | Out-Null
    logman stop -n anv_usbtrace | Out-Null
    logman delete -n anv_usbtrace | Out-Null
    # logman numbers the file (usbtrace_000001.etl); -lr keeps events tracerpt's schema rejects.
    $etl = Get-ChildItem (Join-Path $OutDir "usbtrace*.etl") | Sort-Object LastWriteTime | Select-Object -Last 1
    tracerpt $etl.FullName -o (Join-Path $OutDir "usbtrace.xml") -of XML -lr -y | Out-Null
    Write-Host "  saved $($etl.Name) and usbtrace.xml"
}

Stop-Transcript | Out-Null
Write-Host "`nDone. Results in $OutDir" -ForegroundColor Green
