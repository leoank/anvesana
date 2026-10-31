---
id: PRJ-0001
type: project
schema_version: 1
title: "anvesana: node health benchmarks"
status: active            # active | paused | concluded | moved | archived
code: .               # code/<name> here, or a repository URL once it moves out
created: 2026-10-31
author: ank
tags: [benchmarks, fleet-health, nvidia-n1x, linux-bring-up, windows-on-arm]
---

## Introduction
anvesana runs the same GPU / CPU / memory / disk benchmark suite on every machine in the
fleet on a schedule (monthly), keeps every run, and flags nodes that are getting slower,
hotter or broken against a committed baseline. Off-the-shelf suites measure one thing
once. The fleet needs the same methodology, versioned, on Windows and Linux, ARM and x86,
with power and clocks recorded next to throughput, because the NVIDIA RTX Spark N1X is
power-capped and its numbers move with firmware.

Its second job is platform bring-up. The first N1X machine (`bbaum-pc-7`, an MSI Prestige
N16 Flip AI+) ships with Windows on ARM, and Linux support for the SoC is young.
`bench inventory` records what the hardware is and which driver runs each part, so Linux
can be ported against a reference and its progress measured as a gap list. The design is
`docs/architecture.md`; the machine's findings, including what worked and what failed, are
in `docs/n1x-bringup-log.md`.

## Progress
- [x] Benchmark suite, run records, baselines, health checks, fleet view and scheduled runs (phase 0, before this notebook)
- [x] Per-node dependencies: `bench setup` / `bench check` from one `uv.lock`
- [x] `bench inventory` on Windows: devices, drivers, resources, ACPI tables, SMBIOS, CPU registers ([ADR-0001, 0002](../docs/decisions/README.md))
- [x] Cross-OS `inventory compare` with GAP / MISSING verdicts and exit code (ADR-0003, 0006)
- [x] HID collections, ACPI-WMI blocks, ESRT, opt-in firmware copies (ADR-0005, 0007)
- [x] Display (EDID, modes, HDR, brightness, colour profiles), power (sleep states, overlay, powercfg) and vendor settings
- [x] BIOS and system product in every `run.json` (ADR-0010)
- [x] MSI power modes mapped to the EC shift-mode byte with the read-only admin probe (ADR-0008)
- [x] Keyboard RGB protocol decoded and verified on hardware; `scripts/msi-mystic-light.py` (ADR-0009)
- [x] Repo initialised as a yajna `project` notebook; architecture and decision records written
- [ ] First Linux boot of bbaum-pc-7: `sudo bench inventory collect` on real sysfs (phase 3)
- [ ] Gap list `compare bbaum-pc-7@windows bbaum-pc-7@linux`, SoC controllers first (phase 4)
- [ ] Benchmarks on Linux, including TensorRT (full) and CUTLASS; Linux baseline (phase 5)
- [ ] Power modes, keyboard RGB and backlight from Linux (phase 6)
- [ ] Linux userspace tool for the RGB controller over hidraw

## Open questions
- Does the Linux collector work on real sysfs? It has only been tested on a synthetic tree.
- Is writing the EC through `MSI_ACPI.Set_AP` safe with the `Get_AP` layout, and which bytes hold the battery charge limit?
- What does the `5B3CC38A-…` WMI event (notify 0xC0) carry: hotkeys, tablet mode, AC?
- Where does Linux get tablet mode? MSI Center sets `ConvertibleSlateMode` itself; the sensor hub's hinge angle is the likely source.
- Is the Nano Pen MPP 2.x or USI?
- Which component does each ESRT "Device Firmware" GUID update?
- Does Fn + F8 (keyboard backlight) work on Linux through the EC alone?
- Where does the RGB controller report brightness (`02 b1` returned only its echo)?

## Design
- One process per benchmark and a methodology `VERSION` per benchmark; health refuses to compare across versions.
- Inventory snapshots are separate from runs and stored next to them (ADR-0001).
- Inventory collection needs no admin on Windows (ADR-0002); anything needing admin or able to change hardware state is a separate, read-only or flash-safe script (ADR-0008, 0009).
- Devices are joined across OSes on ACPI path, then on a normalized `match_id` (ADR-0003).
- Records carry no keys, serials or user names in JSON (ADR-0004).

## Lessons
- Windows' USB ETW providers (USBXHCI, UCX, USBHUB3) do not log HID control-transfer payloads, even with `FullDataBusTrace`. The RGB protocol came from MSI's .NET code instead (ADR-0009).
- `GetSystemFirmwareTable('ACPI', 'SSDT')` returns only the first SSDT; the rest are under `HKLM\HARDWARE\ACPI`.
- A size cap alone does not separate firmware from GPU user-mode data (`nvoptix.bin` is 63 MiB); an exclusion list is needed (ADR-0005).
- MSI Center's UI strings list every MSI laptop's modes; this model offers only five (no Cooler Boost, Super Battery or fan options). Ask the person at the machine before trusting a UI string.
- `NvWmiBrightness` is registered by NVIDIA's Windows driver, not the ACPI tables, so Linux's `nvidia-wmi-ec-backlight` does not apply.
- RGB commands are accepted while the backlight is off but show nothing; check Fn + F8 before concluding a lighting test failed.
- A substring privacy filter leaked `OS_Product_Key`; match exact names (ADR-0004).
- yajna 0.18.1's Windows build wrote CRLF pages that its validator rejected; 0.19.0 (native ARM64) writes LF, so the manual conversion is gone and only `.gitattributes` remains (ADR-0011, superseded by ADR-0012).

## Experiments
One line per experiment after its link, what it asks and what came of it; `yajna validate`
rejects a bare link here. Newest last.
