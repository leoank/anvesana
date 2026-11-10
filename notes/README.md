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
- [x] First Linux boot of bbaum-pc-7: `sudo bench inventory collect` on real sysfs (phase 3); NixOS live, `osi` and `sspm` entries, 2026-11-07
- [ ] Gap list `compare bbaum-pc-7@windows bbaum-pc-7@linux`, SoC controllers first (phase 4)
- [ ] Benchmarks on Linux, including TensorRT (full) and CUTLASS; Linux baseline (phase 5)
- [ ] Power modes, keyboard RGB and backlight from Linux (phase 6)
- [ ] Linux userspace tool for the RGB controller over hidraw
- [x] Replication setup for the "RTX Spark is 3x slower on Linux" report: `bench llm` (pinned llama.cpp b12119, GPT-OSS 20B/120B), power-condition sweeps, NixOS live image, ACPI hidden-device tool, journaled Windows state changes (ADR-0013 to 0016; docs/rtx-spark-replication.md)
- [x] Windows baseline with NVPCF on and off, AC and battery ([[EXP-20261104-ssfqvw]])
- [x] WSL2 llama.cpp and vLLM 8-client runs; WSL as the Nix build host ([[EXP-20261104-ssfs86]])
- [x] First build of the NixOS live image (fill the open-modules hash; check the boot menu)
- [x] Native NixOS runs, stock ACPI ([[EXP-20261104-ssfv1c]]), then with SSPM exposed ([[EXP-20261104-ssfy1p]]); stock ACPI cannot boot (no USB without SSPM), so `osi` and `sspm` were run
- [ ] NPCF and hidden-device disassembly ([[EXP-20261104-ssfn9a]])
- [x] nvidia-drm display with the ProArt fixes, and N1X hardware support as `nixosModules.n1x` (ADR-0017)
- [ ] Installed NixOS as the daily driver on bbaum-pc-7: audio, keyboard backlight (Fn + F8), Wi-Fi, suspend; the ProArt audio and keyboard parts are ASUS-specific

## Open questions
- Does the Linux collector work on real sysfs? It has only been tested on a synthetic tree.
- Is writing the EC through `MSI_ACPI.Set_AP` safe with the `Get_AP` layout, and which bytes hold the battery charge limit?
- What does the `5B3CC38A-…` WMI event (notify 0xC0) carry: hotkeys, tablet mode, AC?
- Where does Linux get tablet mode? MSI Center sets `ConvertibleSlateMode` itself; the sensor hub's hinge angle is the likely source.
- Is the Nano Pen MPP 2.x or USI?
- Which component does each ESRT "Device Firmware" GUID update?
- Does Fn + F8 (keyboard backlight) work on Linux through the EC alone?
- Where does the RGB controller report brightness (`02 b1` returned only its echo)?
- Does Linux answer `_OSI("Windows 2022")` true, hiding SVP0, SSPM, HFRP, NH1X and NMAP? Is SSPM (NVDA8400) the non-Windows counterpart of NVPCF? (2026-11-07: yes, it hides them; SSPM is the SCMI endpoint for the SoC's USB/I2C/PCIe power, not a GPU power table.)
- BitLocker on C: is TPM+PIN with an existing recovery password (preflight 2026-11-05): a Secure Boot change would trigger recovery, so the key must be stored off the machine and BitLocker suspended first (ADR-0016). Is it already in the Microsoft account?
- Is the GPU memory reservation (96 GB) a firmware carve-out that Linux cannot reclaim? CUDA on Windows sees 110.5 GiB; the ProArt saw 116 GiB on Linux. (2026-11-07: on this MSI, yes: Linux sees 30.4 GB at 96 GB reserved, 120 GiB at 4 GB.)

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
- Without SSPM (NVDA8400) the NV-Kernels USB and I2C controllers do not probe: they are powered over SCMI through `power_wrap`, and SSPM is hidden from `_OSI("Windows 2022")`. A Linux image for this machine needs `acpi_osi="!Windows 2022"` or the SSPM DSDT override.
- Ventoy injects its own initramfs ahead of the ISO's, so an initrd ACPI override never reaches the kernel; boot override images from a stick written directly.
- ISO copies out of WSL through `/mnt/c` came out corrupted twice (same size, a few bytes changed); copy through `\\wsl.localhost` and check sha256 after every copy.
- On the live image, mount data drives with `x-systemd.automount`: N1X USB enumerates after power_wrap/SSPM, later than a 10 s device timeout.

## Experiments
One line per experiment after its link, what it asks and what came of it; `yajna validate`
rejects a bare link here. Newest last.
- [[EXP-20261104-ssfn9a]] Is NVPCF's power data really opaque, and which ACPI devices does the firmware hide from Linux? Five such devices found in the tables (SVP0, SSPM, HFRP, NH1X, NMAP); all hidden from Linux by default, confirmed on hardware. NPCF tables not disassembled yet.
- [[EXP-20261104-ssfqvw]] Windows baseline: GPT-OSS decode speed and GPU clock on AC and battery, with NVPCF on and off. 120B 63.5 tok/s on AC; disabling NPCF changes nothing.
- [[EXP-20261104-ssfs86]] Does WSL2 match native Windows for llama.cpp and for vLLM with 8 concurrent clients? Yes (within 3 % for 120B); vLLM 302 tok/s with 8 clients.
- [[EXP-20261104-ssfv1c]] Native NixOS with stock ACPI: is the GPU clock locked on AC only, and how much memory does Linux get? Stock ACPI does not boot; with SSPM exposed Linux decodes 7–12 % faster than Windows at 2.5 GHz, and gets only the non-reserved RAM.
- [[EXP-20261104-ssfy1p]] Does exposing the hidden SSPM (NVDA8400) device give Linux working GPU power management? SSPM is what powers USB/I2C on Linux; with it alone Linux runs at full speed.
- [[EXP-20261110-q6a1yn]] What does the host have to send SCP0 (NVDA8200) for the MSFW1111 sensor hub to start answering on SPI?
- [[EXP-20261110-rwymta]] Why does the sensor hub never interrupt on Linux: is the reset response's edge lost before spi-hid enables its IRQ?
