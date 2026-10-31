# ADR-0002: Collect the Windows inventory without administrator rights

Status: accepted
Date: 2026-10-30

## Context
Fleet nodes run the scheduled suite elevated, but developers run `bench inventory` by hand,
often unelevated. The first probes showed that almost everything needed for bring-up is
readable by a normal user:
- PnP properties and signed-driver data (CIM, `Get-PnpDeviceProperty`);
- ACPI tables (`GetSystemFirmwareTable`, with SSDTs from `HKLM\HARDWARE\ACPI`);
- raw SMBIOS;
- per-core CPU ID registers (`HKLM\HARDWARE\DESCRIPTION\System\CentralProcessor`);
- HID caps from a zero-access handle;
- the ESRT;
- display paths (CCD API);
- `powercfg`.

The exceptions are `Get-WindowsDriver -Online` and the vendor WMI class `MSI_ACPI`.

Alternatives considered:
- **Require admin.** Simpler code paths, but most users would never run it.
- **Native SetupAPI for everything.** Faster than PowerShell's per-device property calls
  (about 30 s of the about 50 s collection) but much more ctypes code to maintain.
- **`driverquery` / `pnputil` text output.** Locale-dependent and incomplete.

## Decision
One PowerShell pass (two CIM queries plus `Get-PnpDeviceProperty` for the keys CIM lacks)
returns JSON. Everything else uses ctypes or `winreg` from Python. Admin-only data is
collected by a separate script (ADR-0008), not by `bench inventory`. Each snapshot records
`privileged: true|false` and a `notes` list of what it could not read.

## Consequences
- Anyone can produce a complete bring-up reference on a Windows machine.
- Collection takes about 50 s, dominated by the property sweep.
- HID collections held by the sensor stack (the SPI sensor hub, the camera's presence
  sensor) are not readable this way; Linux's raw descriptors fill that gap.
