---
id: PHS-20261118-eazdd9
type: phase
schema_version: 1
title: RTX Spark replication
project: PRJ-0001
status: active
since: null               # the commit it started at: yajna phase start
until: null               # the commit it finished at: yajna phase done
created: 2026-11-18
author: agent:claude
tags: []
---

## Goal

Replicate the "RTX Spark is 3x slower on Linux" report (claims C1-C7, docs/rtx-spark-replication.md) on bbaum-pc-7: Windows, WSL2 and native NixOS under the same power conditions, and what the firmware hides from Linux.

## Progress
One item per piece of work, ticked when it lands; add items as the plan grows and keep the
done ones. The project page's *Progress* lists this phase on one line.
- [x] Replication setup for the "RTX Spark is 3x slower on Linux" report: `bench llm` (pinned llama.cpp b12119, GPT-OSS 20B/120B), power-condition sweeps, NixOS live image, ACPI hidden-device tool, journaled Windows state changes (ADR-0013 to 0016; docs/rtx-spark-replication.md)
- [x] Windows baseline with NVPCF on and off, AC and battery ([[EXP-20261104-ssfqvw]])
- [x] WSL2 llama.cpp and vLLM 8-client runs; WSL as the Nix build host ([[EXP-20261104-ssfs86]])
- [x] Native NixOS runs, stock ACPI ([[EXP-20261104-ssfv1c]]), then with SSPM exposed ([[EXP-20261104-ssfy1p]]); stock ACPI cannot boot (no USB without SSPM), so `osi` and `sspm` were run
- [ ] NPCF and hidden-device disassembly ([[EXP-20261104-ssfn9a]])

## Notes
Migrated from PRJ-0001's Progress by `yajna phase migrate`.
