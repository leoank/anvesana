# ADR-0006: `inventory compare` reports verdicts and exits non-zero while bring-up gaps remain

Status: accepted
Date: 2026-10-30

## Context
Bring-up progress should be trackable the same way node health is: from a scheduled job,
by exit code, and in a Markdown report. A Windows-to-Linux comparison and a monthly
same-OS comparison ask different questions: what is not working yet, and what changed.

Alternatives considered:
- **A plain diff of the two device lists.** Too noisy: driver names always differ across
  OSes.
- **A percentage score.** It hides which device is the problem.

## Decision
Each matched pair gets one verdict:
- **GAP:** driven on A, present but unbound or deferred on B.
- **MISSING:** driven on A, not enumerated on B.
- **PROBLEM:** B reports a problem or a deferred probe.
- **CHANGED:** same OS, with a different driver, filters or version.
- **NEW, EXTRA, OK:** driven only on B, present only on B, fine on both.

Rows sort by verdict, with NVIDIA SoC blocks (`acpi:NVDA*`) first. Cross-OS, the report
also lists the ACPI-WMI blocks with the Linux driver bound to each, and the HID devices.
The firmware table checks that both OSes got byte-identical ACPI tables and the same BIOS.
`compare` exits 1 while any GAP, MISSING or PROBLEM remains; `--markdown` writes the report.

## Consequences
- A cron job on the first Linux boot can track bring-up until it exits 0.
- Devices Windows drives without a function driver (fans, lid, thermal zones) show as `-`
  rather than GAP.
- WMI blocks without a Linux driver do not affect the exit code.
