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

    Secrets: the recovery password is shown on this console only. It is never written to the journal,
    the transcript or any file; store it off this machine (password manager, paper) before going on.
    npcf-disable refuses to run without a restore point made today.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\rtx-spark-state.ps1 npcf-disable
#>
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('status', 'restore-point', 'npcf-disable', 'npcf-enable', 'bitlocker-recovery-key', 'bitlocker-suspend')]
    [string]$Action,
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
    }
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
    'bitlocker-suspend' {
        Confirm-Step "suspend BitLocker on C: for one reboot (do this right before changing Secure Boot in firmware setup)" `
                     "Resume-BitLocker -MountPoint C: (resumes by itself after the next Windows boot)"
        Suspend-BitLocker -MountPoint C: -RebootCount 1 | Out-Null
        $after = Get-State; Write-Journal $Action $before $after "resumes after one reboot"
        $after | ConvertTo-Json -Depth 5
    }
}
