---
id: AGS-20261104-ssfka4
type: agent_session
schema_version: 1
title: Set up replication of the RTX Spark Linux slowdown claims
model: claude-opus-5-5
harness: claude-code
started: 2026-11-04T23:28+00:00
finished: 2026-11-04T23:32+00:00
created_entities: [EXP-20261104-ssfn9a, EXP-20261104-ssfqvw, EXP-20261104-ssfs86, EXP-20261104-ssfv1c, EXP-20261104-ssfy1p]
edited_entities: [PRJ-0001]
outcome: done             # done | failed | aborted | pending
created: 2026-11-04
author: agent:claude
---

## Task

Ank asked to read the HN thread on "RTX Spark encrypted firmware slows inference to 35% on
Linux", its source (MindStudio) and a ProArt P16 Arch report (josie.lol), build the setup
to replicate the claims, and ask the technical questions first.

## What happened
- Read the three pages and the ProArt build repo (pfeifferj/archlinuxarm-proart-p16 @ 3484cc0).
  Extracted claims C1–C7 into docs/rtx-spark-replication.md.
- Asked four rounds of questions. The author chose: llama.cpp pinned; GPT-OSS 120B + 20B;
  NixOS live USB with the tools baked in, built in WSL Ubuntu 24.04 + Nix; models on a second
  USB; all four Windows tests allowed, with "nothing that can break this setup"; restore points,
  a state journal with undo, and asking before each change; NV-Kernels 7.0.0-1022; driver
  615.78.08; stock ACPI first, then SSPM; a read-only BitLocker check, then a recovery key.
- Found in our own tables: five devices hidden from "Windows 2022", SSPM among them, with
  bytes matching the ProArt's. That became [[EXP-20261104-ssfn9a]] and [[EXP-20261104-ssfy1p]].
- Built: `bench llm`, `--set` on `bench run`, the `on_ac` telemetry column, the fetch,
  conditions, concurrency, ACPI and WSL scripts, the preflight and state scripts, the flake
  and `nix/`, ADR-0013 to 0016, and five experiments.
- Checked: `bench check` READY with llm; the Windows llama.cpp build fetched (sha256 ok) and
  sees CUDA0 with 113,136 MiB; the ACPI tool's patch is 20 bytes with a valid checksum; both
  .ps1 parse; the monitor writes `on_ac`.
- Not checked: the Nix image (no Nix here yet), model downloads (12 + 63 GB, left for the
  author's go), and anything needing elevation.
- Decided without asking:
  - The console stays on simpledrm, without the ProArt nvidia-drm patches.
  - Added an extra `osi` boot entry (`acpi_osi="!Windows 2022"`).
  - The SPARKDATA drive is exFAT so Windows, WSL and NixOS share one model copy.
  - The power-profiles-daemon fork is left out of the first image.
  - `openSha256` is a fake hash until the first build.
- No review opened: REV-20261031-gfr9da is still awaiting the author, as agreed.
