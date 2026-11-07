---
id: AGS-20261105-0rne5w
type: agent_session
schema_version: 1
title: Restore point and model downloads to the data drive
model: claude-opus-5-5
harness: claude-code
started: 2026-11-05T00:42+00:00
finished: 2026-11-07T17:16+00:00
created_entities: []
edited_entities: [EXP-20261104-ssfqvw, EXP-20261104-ssfs86, EXP-20261104-ssfv1c, EXP-20261104-ssfy1p, EXP-20261104-ssfn9a, PRJ-0001]
outcome: done             # done | failed | aborted | pending
created: 2026-11-05
author: agent:claude
---

## Task

Ank stored the BitLocker recovery key and asked for the restore point, plus the model
downloads to the data drive (D:, label "MSI") in parallel.

## What happened
- D: is a 117 GiB exFAT USB flash disk (MBR), empty apart from System Volume Information.
  The models go to `D:\models`, one after the other (about 20 MB/s, the stick's write speed).
- `rtx-spark-state.ps1 restore-point` ran elevated: System Protection was enabled on C:, and
  the point "anvesana: before RTX Spark replication step" was created at 2026-11-05 00:40:06.
- The journal shows Ank's own `bitlocker-recovery-key` run at 00:34; the key was not recorded.
- The drive's label is "MSI", while the live image mounts by label `SPARKDATA`; asked Ank
  rather than relabelling the drive.
- Relabelled D: to `SPARKDATA`. Both models downloaded and sha256-verified (20B 11.3 GiB, 120B 59.0 GiB).
- Fixed `bench llm` for b12119's renamed flags (`-fa on`, `-lm none|mmap`); the first AC attempt
  failed before measuring anything and is saved as a partial run.
- The sampler now keeps only GPU-busy samples, so model loading no longer dilutes power and
  clock. `scripts/llm-telemetry.py` recomputes earlier runs from `telemetry.csv`.
- Ank asked to capture the power profiles. Runs now record the MSI scenario and Energy Saver; the
  registry `EnergySaverState` was not an on/off flag, so the state comes from `GetSystemPowerStatus`.
  The first AC run turned out to be in ECO-Silent.
- LLM sweep, GPT-OSS-20B decode, NVPCF on, Energy Saver off:
  - Battery: ECO 78.1, Balanced 80.3, Perf 81.1, Boost 82.5 tok/s, at 21–25 W and 1.9–2.2 GHz.
  - AC: ECO 76.2, Balanced 80.6, Perf 85.1, Boost 78.4 tok/s, at 25–45 W and 2.1–2.4 GHz.
  - Decode is memory-bound, so the mode barely moves it; Windows never comes near 780 MHz.
- Previous baseline (2026-10-29, AC, Best performance): compute kernels drew 61–76 W at 2.5 GHz,
  so the README's 47 W cap was wrong and is corrected.
- MSI Center code read by a subagent: a mode switch is `Set_Data(0xD2)` plus NVPCF keys
  3234/3235 = 60/80/100/120, applied by MSI's SYSTEM service when the registry `Mode` changes.
  Ank chose registry switching through MSI's service (ADR-0018, amends ADR-0008).
- `rtx-spark-state.ps1 msi-mode` was verified on the first use: we wrote `Mode` only, and MSI set
  ShiftMode 3→2 and the Windows overlay itself.
- Compute sweep started (gpu, tensor, cublaslt, tensorrt_rtx).
  - ECO-Silent on AC: cuBLASLt is held to about 25 W / 1.2 GHz, half the baseline throughput.
    `tensor` drew 36–43 W; memory bandwidth was unchanged.
  - Balanced on AC was running when Ank went to sleep. Performance and Boost wait on a UAC prompt;
    the battery compute runs (four modes) come after.
- Uncommitted: llm.py fixes, `llm-mode-check.py`, `llm-telemetry.py`, the `--benchmarks` option,
  the environment power fields, `msi-mode`, ADR-0018, and the README/profile 47 W fix.
- Balanced on AC, compute: cuBLASLt fp16 60.9 TFLOPS at 35 W / 1.5 GHz; tensor.nvfp4_sparse 856
  TFLOPS at 46 W. The cap rises with the mode (ECO about 25 W, Balanced about 35 W, baseline about 61 W).
- The Performance switch's UAC prompt was cancelled (timed out with nobody there). The mode check
  then refused to run under the wrong label, so nothing ran mislabelled. Fixed the driver
  (`scratchpad/sweep-compute.ps1`) so a cancelled prompt stops it straight away. The machine is
  left in Balanced on AC. Remaining: Performance and Boost on AC, then four modes on battery.

**2026-11-05 evening, AC compute sweep finished** (Performance and Performance Boost via `msi-mode`, both ShiftMode-confirmed):

| MSI mode (AC) | cuBLASLt fp16 | cuBLASLt nvfp4 | tensor.nvfp4_sparse | mem copy |
|---|---|---|---|---|
| ECO-Silent | 41 TFLOPS, 24 W, 1.21 GHz | 185, 25 W | 757, 36 W | 251 GB/s |
| Balanced | 61, 35 W, 1.54 GHz | 245, 36 W | 856, 46 W | 244 GB/s |
| Performance | 82, 57 W, 1.94 GHz | 328, 59 W | 965, 71 W | 252 GB/s |
| Performance Boost | 85, 61 W, 1.96 GHz | 324, 62 W | 975, 76 W | 252 GB/s |
| 2026-10-29 baseline | 86, 61 W, 1.97 GHz | 331, 61 W | 973, 76 W | 252 GB/s |

The GPU power budget follows the MSI mode (NVPCF level 60/80/100/120): GEMMs scale about 2x from ECO to Boost, and register-only kernels change less because they already run near 2.5 GHz. The 2026-10-29 baseline was taken in Performance Boost or something equivalent. Battery runs are waiting: battery 35 %, minimum 50 %.

**2026-11-06, battery compute sweep finished** (battery 100 % -> 59 % at the last start; every switch ShiftMode-confirmed):

| MSI mode (battery) | cuBLASLt fp16 | cuBLASLt nvfp4 | tensor.nvfp4_sparse | mem copy |
|---|---|---|---|---|
| ECO-Silent | 46 TFLOPS, 25 W, 1.14 GHz | 199, 26 W | 839, 35 W | 253 GB/s |
| Balanced | 59, 32 W, 1.32 GHz | 233, 33 W | 904, 45 W | 252 GB/s |
| Performance | 54, 31 W, 1.23 GHz | 214, 29 W | 917, 49 W | 252 GB/s |
| Performance Boost | 53, 30 W, 1.21 GHz | 203, 28 W | 901, 46 W | 252 GB/s |

On battery, GEMM power is capped at about 30–35 W in every mode except ECO, so Performance and Boost gain nothing over Balanced; on AC they reach 57–61 W. The ECO battery run came out slightly above the ECO AC run (46 vs 41 TFLOPS), probably because of temperature or ordering; this is not resolved. Decode is memory-bound, which is why the earlier LLM sweep was flat across modes.

**2026-11-06 to 2026-11-07, the remaining replication runs** (details in the experiment pages'
*Results* and the daily logs):
- 120B on Windows (Boost): 63.5 tok/s on AC, 61.1 on battery. WSL matched Windows; vLLM in WSL
  needed fixed memory flags and served 302 tok/s to 8 clients.
- NVPCF disabled, live and across a reboot: no change in clock or tok/s (C4 not reproduced).
- The NixOS live image was built in WSL (Nix 2.31, nixos-26.05). The first boots failed without
  USB or keyboard: SSPM is hidden from Linux, and NV-Kernels powers USB and I2C through it. The
  on-screen diagnostics found that, and then that Ventoy hid the `sspm` override. `osi` booted
  from Ventoy; `sspm` booted from a stick written directly.
- Linux sees only the non-reserved RAM: 120B ran out of memory at the 96 GB reservation and hung
  the machine. Ank lowered the reservation to 4 GB; then NixOS `osi` and `sspm` both decoded 120B
  at 65.6–65.7 tok/s on AC (Windows at 4 GB: 58.5) and 63.4–63.5 on battery (Windows: 57.2).
- Committed runs: `data/curated_runs/` (user names scrubbed, inventories with ACPI tables kept out).

**Proposed conclusions, for Ank to accept, edit or reject** (not written into the pages):
- [[EXP-20261104-ssfqvw]]: negative for H1. NVPCF does not set the clocks llama.cpp sees on this
  machine; disabling it changes nothing. Windows 120B decode 63.5 tok/s on AC matches the article.
- [[EXP-20261104-ssfs86]]: positive. WSL matches Windows within a few percent.
- [[EXP-20261104-ssfv1c]]: H1 negative, H2 positive. No AC clock lock; Linux is 7–12 % faster than
  Windows on decode. The reservation is a carve-out Linux cannot use, so 120B needs it lowered.
  The stock-ACPI condition cannot be run because Linux cannot boot without SSPM.
- [[EXP-20261104-ssfy1p]]: SSPM is required for Linux to boot, not for GPU clocks; with it
  exposed alone, Linux runs at full speed.
- [[EXP-20261104-ssfn9a]]: H2 positive; H1 still open (NPCF not disassembled), so keep it active.
- For the article: on bbaum-pc-7 none of C1, C2 or C4 reproduces; C5 and C6 do. The article's
  13.9 tok/s fits a Linux boot that saw only the non-reserved RAM or ran partly off the GPU, but
  that is a guess, not something measured here.

Left on the machine: GPU reservation 4 GB, Secure Boot off, BitLocker resumed (it resumes on
the next Windows boot). The boot stick now holds ISO a98d9973 written directly (Ventoy is gone).
