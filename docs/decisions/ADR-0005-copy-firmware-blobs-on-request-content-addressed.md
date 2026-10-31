# ADR-0005: Copy driver-package firmware only on request, stored once per content per machine

Status: accepted
Date: 2026-10-30

## Context
Linux needs the firmware the Windows drivers load:
- **GPU:** `gsp_ga10x.bin`, `ucodes_ga10x.bin`.
- **Audio DSPs:** three COSE-signed HiFi images.
- **MediaTek Wi-Fi and Bluetooth:** `mtkwlan.dat`, `mtkbt_v2.dat`.

The driver packages also hold 1.1 GB of other non-code files, mostly the GPU driver's
user-mode `.so` libraries and data files (CUDA fatbins, OptiX). The blobs are proprietary,
and scheduled runs collect an inventory every month.

Alternatives considered:
- **Never copy, only list with hashes.** Hashes identify a blob, but the blob is then only
  on the machine it came from.
- **Always copy into each snapshot.** About 100 MB per machine per month of identical files.
- **Copy every non-code file.** Over 1 GB of user-mode GPU data.
- **Select by size alone.** `nvoptix.bin` (63 MiB) slipped under the 64 MiB cap.

## Decision
`bench inventory collect --copy-firmware` copies files that look like firmware:
- suffix `.bin .dat .fw .img .elf .hex .mbn .ucode .sig`;
- at most 64 MiB;
- not on a short exclusion list of NVIDIA user-mode data: `nvcubins.bin`, `nvoptix.bin`,
  `nvdrsdb.bin`.

They go to `<store>/<machine>/inventory/firmware/<sha256[:16]>_<name>`, shared by all the
machine's snapshots, and each snapshot's package listing records the path. Every package
file up to 96 MiB is hashed, whether or not it is copied.

## Consequences
- A blob is stored once until a driver update changes it; the hash in each snapshot shows
  when it did.
- The store holds proprietary firmware and must stay internal.
- The exclusion list is vendor knowledge in code; another GPU driver may need entries.
