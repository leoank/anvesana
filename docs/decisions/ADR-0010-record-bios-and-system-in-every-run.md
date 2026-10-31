# ADR-0010: Record BIOS and system identity in every run's environment

Status: accepted
Date: 2026-10-30

## Context
Benchmark results move with firmware as much as with drivers. The N1X's power limits,
clocks and CPU/GPU memory split are set by the BIOS, the EC and NVIDIA's platform tables.
`run.json` recorded the NVIDIA driver and libraries, but not the firmware.

Alternatives considered:
- **Rely on the inventory snapshot.** It is collected separately (ADR-0001), so a run
  could not be checked on its own.
- **Record the full SMBIOS summary in every run.** More than `health` and `compare` need.

## Decision
`environment.capture()` adds `bios` ("vendor version (date)") and `system_product`. On
Windows they come from `HKLM\HARDWARE\DESCRIPTION\System\BIOS`, on Linux from
`/sys/class/dmi/id`, so neither needs admin. `bench show` and `bench compare` display both.

## Consequences
- A regression that lines up with a BIOS update is visible in `compare` without the
  inventory.
- Runs recorded before this change have no `bios` field; comparisons show `-`.
- No schema version bump: the fields are additive.
