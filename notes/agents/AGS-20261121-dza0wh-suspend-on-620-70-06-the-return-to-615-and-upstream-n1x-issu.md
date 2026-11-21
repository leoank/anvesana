---
id: AGS-20261121-dza0wh
type: agent_session
schema_version: 1
title: Suspend on 620.70.06, the return to 615, and upstream N1X issues
model: claude-opus-5-5
harness: claude-code
started: 2026-11-21T12:43+00:00
finished: 2026-11-21T14:34+00:00
created_entities: [RUN-20261121-e9w72k]
edited_entities: [EXP-20261118-ejmvrd]
outcome: done             # done | failed | aborted | pending
created: 2026-11-21
author: agent:claude
---

## Task

Suspend bounced back to the lock screen on 620.70.06: find why, then (Ank's choice after
reading the upstream issues) go back to 615.78.08, prepare a read-only check of the SoC power
budget block and draft a comment for NVIDIA/open-gpu-kernel-modules#1521.

## What happened

The driver's PM notifier fails with 0x56: 620 lists GB20B/GB20C in
`gpuIsPowerManagementUnsupported`, 615 did not. A patch removing them (built for the booted
kernel, swapped in live) let the machine suspend, but it never resumed; the patch, its
`nix/n1x.nix` entry and the boot's log were lost with the reboot (tmpfs, not committed). Read
the open upstream issues on the N1X (#1521, #1458) and suspend/NVPCF ones (#1117, #1549).
`nix/n1x.nix` is back on 615.78.08 without nvidia-powerd (commit 163f389, module built for
the booted kernel, flake check passed). A root script copies the ACPI tables to look for the
0x1C238000 budget block before anything reads it; the #1521 draft waits for Ank. The work is
not under a new review: REV-20261120-g7hvet is still open, waiting for Ank.

Later (Ank: "follow your suggested next steps", then "you can post"): posted the findings to
#1521. The ACPI tables do not name the 0x1C238000 page; I judged a read-only `/dev/mem` read
safe because HP and ASUS owners read the same SoC page, and printed one sample first. Under
cuBLASLt PL1 stayed at 80 W; the GPU's share depends on the CPU's energy preference
([[RUN-20261121-e9w72k]]). I put the power profile back to balanced after the power-saver run.
The first bench attempt failed on a cut-off TensorRT download; the retry worked.

Then (Ank: "do both"): wrote n1x-gpu-boost, a daemon that sets EPP 255 while NVML reports the
GPU busy and the active TuneD profile's value when idle, skipping performance and power-saver;
I chose 60 %/3 s and 30 %/10 s thresholds and reading the profile from
`/etc/tuned/active_profile` (a profile switch to power-saver while boosted would otherwise look
like the boost). Tested by hand: same GPU share as power-saver. Drafted a #1521 follow-up in
`~/issue-1521-followup.md`, not posted yet.
