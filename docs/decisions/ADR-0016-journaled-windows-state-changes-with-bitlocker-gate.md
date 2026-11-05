# ADR-0016: Make Windows state changes through a journaled, confirm-each script gated on BitLocker recovery and a restore point

Status: accepted
Date: 2026-11-04

## Context
The replication changes Windows state:
- disabling the NVPCF device;
- changing the GPU memory reservation;
- installing WSL;
- turning Secure Boot off for the live USB.

The author asked that nothing break the setup and that every change be asked first.

C: is BitLocker-encrypted with a pre-boot password and no saved recovery key. If a TPM
protector is also present, a Secure Boot change triggers recovery, and without a key the disk
would be unrecoverable.

## Decision
- **A read-only check first.** `scripts/rtx-spark-preflight.ps1` reports Secure Boot,
  BitLocker protector types (never key material), restore-point support and the devices, with
  GO / NO-GO per step.
- **One script for every change.** `scripts/rtx-spark-state.ps1` takes one action per call:
  `restore-point`, `npcf-disable` / `npcf-enable`, `bitlocker-recovery-key`, `bitlocker-suspend`.
  - Each action prints the change and its undo, needs a typed `YES`, and journals the state
    before and after.
  - The recovery key is shown once on the console and written nowhere.
  - `npcf-disable` needs a restore point from the same day.
- **The Secure Boot order.** Store a recovery key off the machine, then suspend BitLocker for
  one reboot, then change Secure Boot.

## Consequences
- Each change has a recorded before/after state and a named undo. The journal sits in the
  results store next to the runs it explains.
- The author has to be at the machine for every elevated step.
