# Re-creates RUN-20261110-rs3p36 for EXP-20261110-q6a1yn: does the sensor hub work on Windows
# without nvSCP.sys? Run on bbaum-pc-7 under Windows, in an elevated PowerShell. Hand-recorded
# bench run: step 2 (the reboot and the rotation check) is done by a person.
#
#   powershell -ExecutionPolicy Bypass -File notes\runs\RUN-20261110-rs3p36\run.ps1 -Step off|check|on

param([Parameter(Mandatory)][ValidateSet('off', 'check', 'on')][string]$Step)
$svc = 'HKLM:\SYSTEM\CurrentControlSet\Services\nvSCP'

switch ($Step) {
    # 1. The device cannot be disabled (Disable-PnpDevice: "Not supported", no Disable in
    #    Device Manager), so stop its driver from loading instead; then reboot.
    'off' { Set-ItemProperty $svc -Name Start -Value 4; 'nvSCP Start=4; reboot now' }
    # 2. After the reboot: nvSCP not loaded, and the hub and its sensors still enumerate.
    #    By hand: tablet mode, turn the laptop, see whether the screen rotates.
    'check' {
        "nvSCP Start = $((Get-ItemProperty $svc).Start)"
        Get-CimInstance Win32_SystemDriver -Filter "Name='nvSCP'" | Select-Object Name, State, StartMode
        Get-PnpDevice -InstanceId 'ACPI\NVDA8200\0', 'ACPI\MSFW1111\3' | Select-Object Status, Problem, FriendlyName
        Get-PnpDevice -Class Sensor -PresentOnly | Select-Object Status, FriendlyName
        "last boot: $((Get-CimInstance Win32_OperatingSystem).LastBootUpTime)"
    }
    # 3. Put it back (the INF's value, demand start); reboot.
    'on' { Set-ItemProperty $svc -Name Start -Value 3; 'nvSCP Start=3; reboot to load it again' }
}
