"""Hardware and driver inventory: what is on the machine, and which driver runs each piece.

Benchmarks measure how fast a node is; an inventory records what it is made of. On a new
SoC that is moving from Windows to Linux, the Windows inventory is the reference for
bring-up: every device Windows drives, the ACPI node it comes from, its MMIO and IRQ
resources, the driver package and firmware files behind it. A Linux inventory of the same
machine, compared with it, is the porting gap list.

  firmware.py   OS-neutral parsing: ACPI table headers, SMBIOS, ARM64 CPU ID registers
  windows.py    PnP devices, driver services and packages, ACPI tables, SMBIOS, CPU registers
  linux.py      sysfs devices and bound drivers, modules, deferred probes, kernel log, ACPI tables
  snapshot.py   collect / store / resolve snapshots; the snapshot schema
  command.py    `bench inventory collect | list | show | compare`
"""
