# ADR-0018: Switch MSI power modes by writing the registry value MSI Center's UI writes, letting its service apply them

Status: accepted
Date: 2026-11-05
Amends: ADR-0008 (which allowed only reads of vendor interfaces)

## Context
The Windows sweep for the RTX Spark replication runs every MSI User Scenario on AC and on
battery. Switching by hand takes about 16 clicks per sweep, so the author asked for scripted
switching. ADR-0008 forbids calling `MSI_ACPI` setters. A static read of MSI Center S
(docs/n1x-bringup-log.md, 2026-11-05) showed what selecting a mode does:
- **The UI** only writes `HKLM\...\User Scenario\Mode` (plus `Boost`).
- **The service:** `MSI_Center_S_Server.exe`, running as SYSTEM, watches the key and applies the mode:
  - EC shift mode: `Set_Data(0xD2, …)`;
  - silent, Cooler Boost and backlight bits;
  - NVPCF keys 3234 and 3235 (60 / 80 / 100 / 120);
  - the Windows power-mode overlay.
- **Persistence:** no BIOS or UEFI write is reachable from this path.

Alternatives considered (the author chose the registry write):
- **Keep switching by hand.** Safe, but slow, and every switch needs the author at the machine.
- **Reproduce the EC and NVPCF writes ourselves.** This bypasses MSI's cached state, can collide
  with its read-modify-write of EC bytes, and risks a partial NVPCF change.

## Decision
`scripts/rtx-spark-state.ps1 msi-mode <name>` writes `Mode` and `Boost` exactly as the UI does.
Performance ↔ Performance Boost keeps `Mode` 1, so the script steps through Balanced first. It
then waits for MSI to report the expected `ShiftMode` and journals the state before and after.

The script itself makes no EC, WMI or NVAPI call. It needs elevation; for sweeps, the UAC prompt
for each switch is the confirmation (`-Yes`). ADR-0008 still holds for everything else.

## Consequences
- Each mode is applied by MSI's own code, the same way the UI applies it.
- That MSI's watcher reacts to a writer other than its UI was inferred from the code; the
  script's `ShiftMode` check verifies it on every switch.
- An MSI Center update that changes the key or the watcher breaks the script. The `ShiftMode`
  check then fails loudly instead of running under the wrong label.
