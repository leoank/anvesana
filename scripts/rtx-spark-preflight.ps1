<#
.SYNOPSIS
    Read-only safety check before the RTX Spark replication (docs/rtx-spark-replication.md).
.DESCRIPTION
    Run from an elevated PowerShell. Changes nothing. Reports what decides whether the later steps are
    safe, and writes it as JSON:

      - Secure Boot state, and BitLocker on C: (protection status and protector *types* only; no key
        material or protector IDs are read or written).
      - Whether a TPM protector exists: if it does, turning Secure Boot off for the NixOS USB triggers
        BitLocker recovery, so a recovery password must be saved off the machine first.
      - System Restore on C: (needed for rtx-spark-state.ps1 restore-point).
      - The NVPCF device (ACPI\NVDA0820), the hidden ACPI devices (SSPM NVDA8400, SVP0 NVDA3000,
        HFRP MTK00055), the GPU memory reservation, AC state, BIOS and driver versions, WSL.

    Ends with GO / NO-GO for each later step.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\rtx-spark-preflight.ps1
#>
param(
    [string]$OutDir = (Join-Path $HOME "anvesana-results\$($env:COMPUTERNAME.ToLower())\state")
)

$ErrorActionPreference = "Stop"
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this from an elevated (Administrator) PowerShell."
}
New-Item -ItemType Directory -Force $OutDir | Out-Null

function Try-Get([scriptblock]$Block) { try { & $Block } catch { "ERROR: $($_.Exception.Message.Trim())" } }

$r = [ordered]@{ collected = (Get-Date).ToString("s"); computer = $env:COMPUTERNAME.ToLower() }

$r.secure_boot = Try-Get { [bool](Confirm-SecureBootUEFI) }

$bl = Try-Get { Get-BitLockerVolume -MountPoint C: }
if ($bl -is [string]) { $r.bitlocker = $bl } else {
    $r.bitlocker = [ordered]@{
        protection_status = "$($bl.ProtectionStatus)"
        volume_status     = "$($bl.VolumeStatus)"
        encryption_method = "$($bl.EncryptionMethod)"
        protector_types   = @($bl.KeyProtector | ForEach-Object { "$($_.KeyProtectorType)" })
    }
}
$r.tpm = Try-Get { $t = Get-Tpm; [ordered]@{ present = $t.TpmPresent; ready = $t.TpmReady } }

$vss = Try-Get { (vssadmin list shadowstorage /for=C: | Out-String).Trim() }
$r.system_restore = [ordered]@{
    shadow_storage = $vss
    last_points    = @(Try-Get { Get-ComputerRestorePoint | Select-Object -Last 3 |
                        ForEach-Object { "$($_.ConvertToDateTime($_.CreationTime).ToString('s')) $($_.Description)" } })
}

$devices = Get-PnpDevice -ErrorAction SilentlyContinue |
    Where-Object { $_.InstanceId -match 'NVDA0820|NVDA8400|NVDA3000|MTK00055' }
$r.acpi_devices = @($devices | ForEach-Object {
    [ordered]@{ instance = $_.InstanceId; name = $_.FriendlyName; status = "$($_.Status)"; problem = "$($_.Problem)" } })
$npcfDriver = Get-CimInstance Win32_PnPSignedDriver -ErrorAction SilentlyContinue | Where-Object { $_.DeviceID -like 'ACPI\NVDA0820*' } | Select-Object -First 1
$r.npcf_driver = if ($npcfDriver) { "$($npcfDriver.InfName) $($npcfDriver.DriverVersion)" } else { $null }

$smi = Try-Get { (nvidia-smi --query-gpu=driver_version,memory.total,clocks.max.sm --format=csv,noheader | Select-Object -First 1).Trim() }
$cs = Get-CimInstance Win32_ComputerSystem
$bios = Get-CimInstance Win32_BIOS
$bat = Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue
$r.platform = [ordered]@{
    gpu_driver_memory_maxclock = $smi
    windows_ram_gib = [math]::Round($cs.TotalPhysicalMemory / 1GB, 1)
    bios = "$($bios.SMBIOSBIOSVersion)"
    model = "$($cs.Model)"
    battery_status = if ($bat) { $bat.BatteryStatus } else { $null }   # 2 = on AC
    battery_pct = if ($bat) { $bat.EstimatedChargeRemaining } else { $null }
}
$r.wsl = Try-Get { ((wsl.exe --status) -join "`n") -replace "`0", "" }

# ------------------------------------------------------------------ verdicts
$v = [ordered]@{}
$types = if ($r.bitlocker -is [string]) { @() } else { $r.bitlocker.protector_types }
$hasTpm = [bool]($types | Where-Object { $_ -like 'Tpm*' })
$hasRecovery = [bool]($types | Where-Object { $_ -eq 'RecoveryPassword' })
$on = ($r.bitlocker -isnot [string]) -and ($r.bitlocker.protection_status -eq 'On')
$v.secure_boot_change = if (-not $on) { "GO: BitLocker protection is off" }
    elseif ($hasTpm -and -not $hasRecovery) { "NO-GO: TPM protector and no recovery password; run rtx-spark-state.ps1 bitlocker-recovery-key and store the key off this machine" }
    elseif ($hasTpm) { "GO after: confirm the recovery password is stored off this machine, then rtx-spark-state.ps1 bitlocker-suspend right before entering firmware setup" }
    else { "GO: no TPM protector ($($types -join ', ')); Secure Boot changes do not trigger recovery" }
$v.restore_point = if ("$vss" -match 'Maximum Shadow Copy Storage') { "GO" } else { "NO-GO: System Protection looks off on C:; rtx-spark-state.ps1 restore-point offers to enable it" }
$v.npcf_disable = if ($r.acpi_devices | Where-Object { $_.instance -like 'ACPI\NVDA0820*' -and $_.status -eq 'OK' }) { "GO (after a restore point)" } else { "CHECK: NVPCF device not OK/present" }
$r.verdicts = $v

$file = Join-Path $OutDir "preflight_$(Get-Date -Format yyyy-MM-dd_HHmmss).json"
$r | ConvertTo-Json -Depth 6 | Out-File -Encoding utf8 $file
$r | ConvertTo-Json -Depth 6
"`nWritten: $file"
