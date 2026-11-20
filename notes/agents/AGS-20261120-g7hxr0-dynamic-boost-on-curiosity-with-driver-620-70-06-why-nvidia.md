---
id: AGS-20261120-g7hxr0
type: agent_session
schema_version: 1
title: "Dynamic Boost on curiosity with driver 620.70.06: why nvidia-powerd still quits, fix what the driver gets wrong"
model: claude-opus-5-5
harness: claude-code
started: 2026-11-20T14:46+00:00
finished: 2026-11-20T15:07+00:00
created_entities: [RUN-20261120-g7hznd, REV-20261120-g7hvet]
edited_entities: [EXP-20261118-ejmvrd]
outcome: done             # done | failed | aborted | pending
created: 2026-11-20
author: agent:claude
---

## Task

## What happened
Ank booted curiosity with driver 620.70.06 (anvesana 356ae30) and asked to check the new
image. Goal: get nvidia-powerd (Dynamic Boost) running so the GPU can reach Windows' ~61 W.

## What happened

- The display, 620.70.06 and `n1x-tablet-mode.service` (started at boot by itself) work.
  nvidia-powerd still quit.
- Traced the failure into the open driver: NVPCF 3.x reads get a quarter of the caller's
  buffer, too small for NPCF's 2,176-byte init table. Wrote
  `nix/patches/nvidia-open-nvpcf3x-read-size.patch`, built it from neusis for the booted kernel
  (anvesana overridden to this checkout, neusis untouched) and had Ank swap the modules in
  without a reboot. My first swap script forgot nvidia-drm's two DRM helper modules and the
  display went dark; a second script fixed it. Committed the patch (260cb0e) after
  `nix flake check --no-build`.
- With the patch every RM control succeeds and powerd completes the whole NVPCF 3.x exchange,
  then quits without a logged reason. Decoded the RM controls and NVPCF data under gdb, then
  promoted powerd's suppressed log levels: still silent. Agreed with Ank to stop at that point
  rather than trace powerd's control flow by hand. Recorded in [[RUN-20261120-g7hznd]] under
  [[EXP-20261118-ejmvrd]], reviewed in [[REV-20261120-g7hvet]].
- Decided without asking: kept the NVPCF dumps out of git (vendor data, like the ACPI tables
  of [[RUN-20261118-hb8wfr]]).
- After the first write-up, Ank asked for more. A backtrace showed `main()` quits when no worker
  runs; powerd's INFO lines need a verbosity above 3 that `main()` sets to 2. Forced from gdb,
  powerd reports NVPCF 3.x fully accepted and then no worker created, without a reason.
  Recommended moving to MSI's own interface instead; its WMI methods turned out to be an opaque
  pass-through to MSI's FF-A service, so proposed a write-free test (MSI Center's mode, then a
  reboot into Linux) rather than guessing payloads.
