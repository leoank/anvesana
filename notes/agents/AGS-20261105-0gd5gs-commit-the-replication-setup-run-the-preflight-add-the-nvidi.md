---
id: AGS-20261105-0gd5gs
type: agent_session
schema_version: 1
title: Commit the replication setup, run the preflight, add the NVIDIA display patches
model: claude-opus-5-5
harness: claude-code
started: 2026-11-05T00:28+00:00
finished: 2026-11-05T00:28+00:00
created_entities: []
edited_entities: [PRJ-0001]
outcome: done             # done | failed | aborted | pending
created: 2026-11-05
author: agent:claude
---

## Task

Ank asked to commit the replication setup and run the preflight, then asked mid-way
whether the ProArt display patches are much work, since NixOS is to become the daily
driver on this machine.

## What happened
- Committed the setup as `99c1a44` on `exp/nvpcf-throttle`.
- Ran `scripts/rtx-spark-preflight.ps1` elevated, with Ank accepting the UAC prompt.
  - Secure Boot is on; BitLocker on C: has `TpmPin` and `RecoveryPassword` protectors.
  - So a recovery key exists, but Ank has no copy; a Secure Boot change would trigger recovery.
  - System Protection is off, so there are no restore points yet; NPCF is OK; BIOS G2621NMS.10B.
- Fixed two script issues the run showed:
  - The preflight's NVPCF driver query returned null (WQL escaping); it now reads `oem84.inf 32.0.16.1679`.
  - `bitlocker-recovery-key` now shows the existing recovery password instead of adding a second one.
- Display patches: two small patches to NVIDIA's open modules, applied through nixpkgs' `patchesOpen`.
  - Moved the hardware support into `nix/n1x.nix`, exported as `nixosModules.n1x`, for an installed system later.
  - Added a `simpledrm` fallback boot entry and ADR-0017, which amends ADR-0014's display choice.
- Not checked: nothing built (still no Nix here); the patches are untested on the MSI panel.
