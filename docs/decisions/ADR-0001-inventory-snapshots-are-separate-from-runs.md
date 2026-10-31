# ADR-0001: Inventory snapshots are a record of their own, stored next to a machine's runs

Status: accepted
Date: 2026-10-30

## Context
Porting Linux to the NVIDIA N1X needs a full map of the hardware and of the drivers Windows
uses for it: every device, its ACPI node, resources, driver package and firmware. That is a
different kind of record from a benchmark run: it is large (raw ACPI tables, EDIDs, INFs,
HID descriptors), changes rarely, and is useful on its own, before any benchmark can run
on Linux.

Alternatives considered:
- **Extend `run.json`'s `environment`.** Every run would carry megabytes of tables, and a
  run would be needed to get an inventory, but bring-up happens before benchmarks work.
- **A separate tool or repository.** It would duplicate the machine profiles, the results
  store and the run-reference syntax, and the fleet would have two schedules.
- **A one-off script for this machine.** It wouldn't help the next SoC, and a Windows
  inventory needs a Linux one to compare against.

## Decision
`bench inventory collect | list | show | compare` writes snapshots to
`$ANVESANA_RESULTS_DIR/<machine>/inventory/<machine>_<date>_<os>/` (`inventory.json` plus raw
files), with the same machine ids and a reference syntax modelled on runs
(`<machine>@windows`, `@-1`, `@<date>`). The schema is `inventory.json` schema version 1,
documented in `src/anvesana/inventory/snapshot.py`. The scheduled-run scripts collect an
inventory before each benchmark run; a failed collection does not stop the run.

## Consequences
- Snapshots exist on nodes with no profile yet (the machine id falls back to the hostname).
- Driver and firmware drift between monthly runs is visible with `inventory compare` on one OS.
- Run records stay small; the link between a run and a snapshot is only the machine and date.
- A second schema to keep stable alongside `run.json`.
