# ADR-0015: Change ACPI only through per-boot RAM overrides; vendor tables never enter git

Status: accepted
Date: 2026-11-04

## Context
Five devices in bbaum-pc-7's DSDT/SSDT return `_STA` 0 when the OS answers
`_OSI("Windows 2022")`: SVP0, SSPM (NVDA8400), HFRP, NH1X and NMAP. Windows, and probably
Linux too, therefore never see them. The ProArt Arch build exposes SSPM with a DSDT override.

Testing whether exposing SSPM helps Linux power management means changing what the firmware
reports, on a laptop that must keep booting Windows.

Alternatives considered:
- **Flash patched tables.** Irreversible risk; rejected.
- **Only `acpi_osi="!Windows 2022"`.** It exposes all five devices and changes every other
  `_OSI("Windows 2022")` branch, so it can't isolate SSPM. It is kept as a separate boot entry.

## Decision
Overrides are initrd ACPI table upgrades that exist only in RAM for one boot. They are built
by `scripts/acpi-hidden-devices.py`, which:
- accepts only the exact `_STA` pattern;
- replaces the predicate with Zero plus Noops, so the table length is unchanged;
- bumps the OEM revision and fixes the checksum, so 20 bytes change in total.

Each variant is its own boot entry (`default`, `osi`, `sspm`). The patched tables contain
MSI's code, so they are written to `nix/local/` (gitignored) and passed to an `--impure` build.

## Consequences
- Rebooting into another entry undoes any ACPI variant.
- Whoever builds the image needs a dump of their own machine's tables (an inventory snapshot)
  to build the `sspm` entry.
