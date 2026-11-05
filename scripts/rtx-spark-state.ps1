<#
.SYNOPSIS
    Journaled, confirm-each-step Windows state changes for the RTX Spark replication.
.DESCRIPTION
    Run from an elevated PowerShell, one action at a time. Every action prints what it will change,
    waits for you to type YES, records the state before and after in journal.jsonl, and has an undo:

      status                    read-only: NVPCF device, BitLocker protector types, last restore points
      restore-point             System Restore point on C: (offers to turn System Protection on if off)
      npcf-disable              disable ACPI\NVDA0820\NPCF (NVIDIA Platform Controllers and Framework)
      npcf-enable               undo of npcf-disable
      bitlocker-recovery-key    add a BitLocker recovery-password protector to C: and show it once
      bitlocker-suspend         suspend BitLocker for exactly one reboot (before a Secure Boot change)
      msi-mode <name>           switch the MSI Center User Scenario (ECO-Silent, Balanced, Performance,
                                Performance Boost, AI Engine) by writing the registry value MSI Center's
                                UI writes; MSI's own SYSTEM service then sets the EC, NVPCF and the
                                Windows power mode. No EC or WMI write is made by this script.

    Secrets: the recovery password is shown on this console only. It is never written to the journal,
    the transcript or any file; store it off this machine (password manager, paper) before going on.
    npcf-disable refuses to run without a restore point made today.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\rtx-spark-state.ps1 npcf-disable
#>
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('status', 'restore-point', 'npcf-disable', 'npcf-enable', 'bitlocker-recovery-key', 'bitlocker-suspend', 'msi-mode')]
    [string]$Action,
    [Parameter(Position = 1)]
    [ValidateSet('ECO-Silent', 'Balanced', 'Performance', 'Performance Boost', 'AI Engine')]
    [string]$Mode,
    [switch]$Yes,   # msi-mode only: the UAC prompt was the confirmation (used by sweeps)
    [string]$OutDir = (Join-Path $HOME "anvesana-results\$($env:COMPUTERNAME.ToLower())\state")
)

$ErrorActionPreference = "Stop"
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this from an elevated (Administrator) PowerShell."
}
New-Item -ItemType Directory -Force $OutDir | Out-Null
$Journal = Join-Path $OutDir "journal.jsonl"
$Npcf = 'ACPI\NVDA0820\NPCF'

function Get-State {
    $d = Get-PnpDevice -InstanceId $Npcf -ErrorAction SilentlyContinue
    $bl = Get-BitLockerVolume -MountPoint C: -ErrorAction SilentlyContinue
    [ordered]@{
        npcf            = if ($d) { "$($d.Status) (problem $($d.Problem))" } else { 'absent' }
        bitlocker       = if ($bl) { "$($bl.ProtectionStatus)" } else { 'unknown' }
        protector_types = if ($bl) { @($bl.KeyProtector | ForEach-Object { "$($_.KeyProtectorType)" }) } else { @() }
        last_restore    = (Get-ComputerRestorePoint -ErrorAction SilentlyContinue | Select-Object -Last 1 |
                           ForEach-Object { "$($_.ConvertToDateTime($_.CreationTime).ToString('s')) $($_.Description)" })
        on_ac           = ((Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue).BatteryStatus -eq 2)
        msi             = Get-MsiScenario
    }
}

# MSI Center S User Scenario (docs/n1x-bringup-log.md, 2026-11-05): the UI writes Mode (and Boost),
# MSI_Center_S_Server.exe watches the key and applies EC shift mode, NVPCF level and Windows power mode.
$MsiKey = 'HKLM:\SOFTWARE\WOW6432Node\MSI\MSI Center S\Component\Base Module\User Scenario'
$MsiModes = @{
    'ECO-Silent'        = @{ Mode = 3; Boost = 0; Shift = 3 }
    'Balanced'          = @{ Mode = 2; Boost = 0; Shift = 2 }
    'Performance'       = @{ Mode = 1; Boost = 0; Shift = 0 }
    'Performance Boost' = @{ Mode = 1; Boost = 1; Shift = 5 }
    'AI Engine'         = @{ Mode = 5; Boost = 0; Shift = 2 }
}

function Get-MsiScenario {
    $p = Get-ItemProperty $MsiKey -ErrorAction SilentlyContinue
    if ($p) { "Mode $($p.Mode) Boost $($p.Boost) ShiftMode $($p.ShiftMode)" } else { 'absent' }
}

function Wait-MsiShift([int]$Shift, [int]$TimeoutS = 20) {
    $t0 = Get-Date
    while (((Get-Date) - $t0).TotalSeconds -lt $TimeoutS) {
        if ((Get-ItemProperty $MsiKey).ShiftMode -eq $Shift) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Write-Journal($Action, $Before, $After, $Note) {
    [ordered]@{ time = (Get-Date).ToString("s"); action = $Action; before = $Before; after = $After; note = $Note } |
        ConvertTo-Json -Compress -Depth 5 | Out-File -Append -Encoding utf8 $Journal
}

function Confirm-Step([string]$What, [string]$Undo) {
    Write-Host "`nAbout to: $What" -ForegroundColor Yellow
    Write-Host "Undo:     $Undo"
    if ((Read-Host "Type YES to continue") -cne 'YES') { Write-Host "Cancelled; nothing changed."; exit 2 }
}

$before = Get-State
switch ($Action) {
    'status' {
        $before | ConvertTo-Json -Depth 5
        Write-Host "`nJournal: $Journal"
    }
    'restore-point' {
        $vss = (vssadmin list shadowstorage /for=C: | Out-String)
        if ($vss -notmatch 'Maximum Shadow Copy Storage') {
            Confirm-Step "turn on System Protection for C: (needed for restore points)" `
                         "Disable-ComputerRestore -Drive C:\ (deletes the restore points)"
            Enable-ComputerRestore -Drive "C:\"
        }
        Confirm-Step "create a System Restore point 'anvesana: before RTX Spark replication step'" `
                     "none needed; restore from it with rstrui.exe"
        # Windows skips a new point if one was made in the last 24 h unless this is 0 for the call.
        $key = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\SystemRestore'
        $old = (Get-ItemProperty $key -Name SystemRestorePointCreationFrequency -ErrorAction SilentlyContinue).SystemRestorePointCreationFrequency
        Set-ItemProperty $key -Name SystemRestorePointCreationFrequency -Value 0 -Type DWord
        try { Checkpoint-Computer -Description "anvesana: before RTX Spark replication step" -RestorePointType MODIFY_SETTINGS }
        finally {
            if ($null -eq $old) { Remove-ItemProperty $key -Name SystemRestorePointCreationFrequency }
            else { Set-ItemProperty $key -Name SystemRestorePointCreationFrequency -Value $old -Type DWord }
        }
        $after = Get-State; Write-Journal $Action $before $after ""
        $after | ConvertTo-Json -Depth 5
    }
    'npcf-disable' {
        $today = Get-ComputerRestorePoint -ErrorAction SilentlyContinue |
            Where-Object { $_.ConvertToDateTime($_.CreationTime).Date -eq (Get-Date).Date }
        if (-not $today) { throw "No restore point made today: run 'rtx-spark-state.ps1 restore-point' first." }
        Confirm-Step "disable $Npcf (NVIDIA Platform Controllers and Framework); a reboot may be asked for" `
                     "rtx-spark-state.ps1 npcf-enable (then reboot)"
        Disable-PnpDevice -InstanceId $Npcf -Confirm:$false
        $after = Get-State; Write-Journal $Action $before $after "benchmark, then npcf-enable"
        $after | ConvertTo-Json -Depth 5
        Write-Host "`nIf Status is not 'Error'/'Unknown' (disabled) yet, reboot before benchmarking."
    }
    'npcf-enable' {
        Confirm-Step "enable $Npcf again" "rtx-spark-state.ps1 npcf-disable"
        Enable-PnpDevice -InstanceId $Npcf -Confirm:$false
        $after = Get-State; Write-Journal $Action $before $after ""
        $after | ConvertTo-Json -Depth 5
        Write-Host "`nReboot so the driver re-applies its power tables, then run 'status'."
    }
    'bitlocker-recovery-key' {
        # Show the existing recovery password if C: has one (device encryption usually does);
        # add one only if it has none.
        $kp = (Get-BitLockerVolume -MountPoint C:).KeyProtector | Where-Object KeyProtectorType -eq 'RecoveryPassword' |
            Select-Object -First 1
        if ($kp) {
            Confirm-Step "show C:'s existing BitLocker recovery key on this console (nothing is changed)" "none needed"
            $note = "existing recovery password shown (key not recorded)"
        } else {
            Confirm-Step "add a recovery-password protector to C: (your pre-boot password keeps working unchanged)" `
                         "Remove-BitLockerKeyProtector -MountPoint C: -KeyProtectorId <id shown below>"
            $vol = Add-BitLockerKeyProtector -MountPoint C: -RecoveryPasswordProtector -WarningAction SilentlyContinue
            $kp = $vol.KeyProtector | Where-Object KeyProtectorType -eq 'RecoveryPassword' | Select-Object -Last 1
            $note = "recovery-password protector added (key not recorded)"
        }
        Write-Host "`n======================== BITLOCKER RECOVERY KEY ========================" -ForegroundColor Red
        Write-Host "  Protector ID : $($kp.KeyProtectorId)"
        Write-Host "  Recovery key : $($kp.RecoveryPassword)" -ForegroundColor Red
        Write-Host "=========================================================================" -ForegroundColor Red
        Write-Host "Store it off this machine now. It is not saved anywhere by this script."
        Write-Host "The recovery screen shows a key ID; check it matches the first 8 characters of the Protector ID."
        $after = Get-State; Write-Journal $Action $before $after $note
        [void](Read-Host "Press Enter once the key is stored")
        Clear-Host
    }
    'msi-mode' {
        if (-not $Mode) { throw "msi-mode needs a mode: $($MsiModes.Keys -join ', ')" }
        if (-not (Test-Path $MsiKey)) { throw "MSI Center S User Scenario key not found: $MsiKey" }
        $want = $MsiModes[$Mode]
        $cur = Get-ItemProperty $MsiKey
        if ($cur.Mode -eq $want.Mode -and [int]$cur.Boost -eq $want.Boost -and $cur.ShiftMode -eq $want.Shift) {
            Write-Host "Already $Mode ($(Get-MsiScenario)); nothing changed."
            exit 0
        }
        if (-not $Yes) {
            Confirm-Step "switch MSI Center to $Mode by writing User Scenario Mode=$($want.Mode) Boost=$($want.Boost)" `
                         "rtx-spark-state.ps1 msi-mode '<previous mode>' (before: $(Get-MsiScenario))"
        }
        # MSI's watcher acts on a change of Mode: Performance <-> Boost keeps Mode 1, so step
        # through Balanced first (the UI forces the same re-apply with a ChangeBoost message).
        if ($cur.Mode -eq $want.Mode) {
            Set-ItemProperty $MsiKey -Name Mode -Value 2 -Type DWord
            if (-not (Wait-MsiShift 2)) { throw "MSI did not apply the intermediate Balanced step" }
            Start-Sleep -Seconds 2
        }
        Set-ItemProperty $MsiKey -Name Boost -Value $want.Boost -Type DWord
        Set-ItemProperty $MsiKey -Name Mode -Value $want.Mode -Type DWord
        $ok = Wait-MsiShift $want.Shift
        $after = Get-State
        Write-Journal $Action $before $after "$Mode requested; ShiftMode $(if ($ok) { 'confirmed' } else { 'NOT confirmed' })"
        $after | ConvertTo-Json -Depth 5
        if (-not $ok) { Write-Host "MSI did not report ShiftMode $($want.Shift) within 20 s." -ForegroundColor Red; exit 1 }
    }
    'bitlocker-suspend' {
        Confirm-Step "suspend BitLocker on C: for one reboot (do this right before changing Secure Boot in firmware setup)" `
                     "Resume-BitLocker -MountPoint C: (resumes by itself after the next Windows boot)"
        Suspend-BitLocker -MountPoint C: -RebootCount 1 | Out-Null
        $after = Get-State; Write-Journal $Action $before $after "resumes after one reboot"
        $after | ConvertTo-Json -Depth 5
    }
}
