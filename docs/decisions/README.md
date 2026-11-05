# Decisions

One architecture decision record per file, `ADR-0001-short-title.md`, numbered in order
and never renumbered. A decision that changes an earlier one supersedes it; both stay.

| ADR | Decision | Status |
|-----|----------|--------|
| [0001](ADR-0001-inventory-snapshots-are-separate-from-runs.md) | Inventory snapshots are a record of their own, stored next to a machine's runs | accepted |
| [0002](ADR-0002-collect-windows-inventory-without-admin.md) | Collect the Windows inventory without administrator rights | accepted |
| [0003](ADR-0003-match-devices-by-acpi-path-then-hardware-id.md) | Match devices across OSes by ACPI path, then by a normalized hardware id | accepted |
| [0004](ADR-0004-raw-firmware-in-linux-tool-formats-without-identifiers.md) | Keep raw firmware in formats Linux tools read; leave out keys and serial numbers | accepted |
| [0005](ADR-0005-copy-firmware-blobs-on-request-content-addressed.md) | Copy driver-package firmware only on request, stored once per content per machine | accepted |
| [0006](ADR-0006-compare-exits-non-zero-while-gaps-remain.md) | `inventory compare` reports verdicts and exits non-zero while bring-up gaps remain | accepted |
| [0007](ADR-0007-hid-as-parsed-collections-in-one-schema.md) | Record HID devices as parsed top-level collections in one schema for both OSes | accepted |
| [0008](ADR-0008-probe-vendor-firmware-read-only-from-a-separate-script.md) | Probe vendor firmware interfaces read-only, from a separate elevated script | accepted |
| [0009](ADR-0009-mystic-light-protocol-from-vendor-code-never-write-flash.md) | Take the keyboard RGB protocol from the vendor's code; never write the controller's flash | accepted |
| [0010](ADR-0010-record-bios-and-system-in-every-run.md) | Record BIOS and system identity in every run's environment | accepted |
| [0011](ADR-0011-keep-notebook-files-lf.md) | Keep the notebook's files LF in git and in checkouts | superseded by 0012 |
| [0012](ADR-0012-keep-gitattributes-lf-drop-manual-conversion.md) | Keep the notebook LF through `.gitattributes` alone; stop converting pages by hand (yajna ≥ 0.19.0) | accepted |
| [0013](ADR-0013-llm-inference-with-one-pinned-llama-cpp-build.md) | Measure LLM inference with one pinned llama.cpp build, the same binary in WSL and on native Linux | accepted |
| [0014](ADR-0014-native-linux-from-a-nixos-live-usb.md) | Run native-Linux tests from a NixOS live USB with NVIDIA's N1X kernel and driver 615.78.08 | accepted |
| [0015](ADR-0015-acpi-changes-only-as-per-boot-ram-overrides.md) | Change ACPI only through per-boot RAM overrides; vendor tables never enter git | accepted |
| [0016](ADR-0016-journaled-windows-state-changes-with-bitlocker-gate.md) | Make Windows state changes through a journaled, confirm-each script gated on BitLocker recovery and a restore point | accepted |

Decisions that predate this notebook (one process per benchmark, per-benchmark `VERSION`,
committed baselines, per-node extras from one `uv.lock`) are described in the top-level
`README.md` and in `architecture.md`; they were made before decision records were kept.

Each record:

```markdown
# ADR-0001: <the decision, as a sentence>

Status: proposed | accepted | superseded by ADR-xxxx
Date: YYYY-MM-DD

## Context
What forced the decision, and the alternatives considered.

## Decision
What was chosen.

## Consequences
What follows, good and bad.
```
