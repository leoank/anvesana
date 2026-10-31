# ADR-0003: Match devices across operating systems by ACPI path, then by a normalized hardware id

Status: accepted
Date: 2026-10-30

## Context
The porting gap list joins a Windows snapshot to a Linux snapshot device by device. The two
OSes name devices differently:
- **Instance ids:** Windows uses `ACPI\NVDA0200\0`; Linux uses `NVDA0200:00`, a platform
  node `platform/NVDA0200:00`, and an I2C child.
- **Processors:** Windows names them by a marketing string, while the HID is `ACPI0007`.
- **USB root hubs:** Windows calls them `ROOT_HUB30`; Linux reports `1d6b:0003`.
- **ACPI paths:** Windows writes `\_SB.I2C0` and Linux `\_SB_.I2C0`.
- **Which node holds the driver:** on Linux the driver binds to the ACPI device's physical
  node, not the ACPI node itself.

The N1X has 7 identical I2C controllers, so a hardware id alone cannot pair them.

Alternatives considered:
- **Hardware id only.** It can't tell repeated controllers apart.
- **Bus position or resource addresses.** Linux hides `/proc/iomem` addresses from
  non-root users, and Windows numbering is arbitrary.

## Decision
Every device record has a cross-OS `match_id` (`acpi:<HID>`, `pci:<ven>:<dev>`,
`usb:<vid>:<pid>[:if<n>]`, `wmi:<GUID>`) and, where it has one, its ACPI namespace path.
`compare` pairs devices on the normalized ACPI path (segments with trailing `_` stripped),
then pairs the rest on `match_id` in id order. On Linux the ACPI device is the canonical
record and carries the driver of its first bound physical node. ACPI devices whose physical
node is on PCI or USB are listed once, from that bus. Devices with `_STA` absent and ACPI
pseudo-devices (`LNX*`, `device:*`) are skipped, as Windows does not enumerate them.
Identical rows are grouped (`n` column) unless `--expand` is given.

## Consequences
- Repeated controllers pair correctly; the gap list names the exact instance (`\_SB.I2C1`).
- Windows-only software devices (SWD, ROOT, volumes) are excluded from cross-OS
  comparison, as are external peripherals (`InLocalMachineContainer = false`).
- New naming differences (like the root hub) need a mapping in `windows.match_id`.
