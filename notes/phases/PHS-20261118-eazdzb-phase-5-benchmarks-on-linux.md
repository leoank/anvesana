---
id: PHS-20261118-eazdzb
type: phase
schema_version: 1
title: Phase 5 Benchmarks on Linux
project: PRJ-0001
status: active
since: null               # the commit it started at: yajna phase start
until: null               # the commit it finished at: yajna phase done
created: 2026-11-18
author: agent:claude
tags: []
---

## Goal

The same suite on Linux, including the Linux-only TensorRT and CUTLASS. Checked by a promoted Linux baseline and `bench compare <machine>@baseline:windows <machine>@baseline:linux`.

## Progress
One item per piece of work, ticked when it lands; add items as the plan grows and keep the
done ones. The project page's *Progress* lists this phase on one line.
- [ ] Benchmarks on Linux, including TensorRT (full) and CUTLASS; Linux baseline (phase 5)
- [x] First Linux suite run compared with the Windows baseline ([[EXP-20261118-ejmvrd]])
- [x] Full TensorRT and CUTLASS running on NixOS ([[RUN-20261118-g2tm8p]])
- [x] Why the CPU is slower on Linux: glibc sin/cos and OpenBLAS paced by the A725s ([[RUN-20261118-g2z7h4]])
- [ ] cuBLASLt's power budget on Linux (~51 W against ~61 W on Windows): the MSI mode from Linux, phase 6
- [ ] CPU benchmark on a hybrid CPU: GEMM per core type, and cpu.math's dependence on the C library

## Notes
Migrated from PRJ-0001's Progress by `yajna phase migrate`.
