---
id: AGS-20261110-q69ze3
type: agent_session
schema_version: 1
title: "Accelerometer on Linux: the SCP0 sensor coprocessor mailbox"
model: "claude-opus-5-5"
harness: "claude-code"
started: 2026-11-10T21:06+00:00
finished: null
created_entities: [EXP-20261110-q6a1yn, RUN-20261110-rgc7bg, RUN-20261110-rs3p36, EXP-20261110-rwymta]
edited_entities: []
outcome: pending          # done | failed | aborted | pending
created: 2026-11-10
author: agent:claude
---

## Task

Ank, 2026-11-10, after the suspend and audio fixes were confirmed on the laptop (boot
c542daee): "Let's start the accel work". The sensor hub binds on Linux but never interrupts;
the lead from the last session is SCP0 (NVDA8200) and its Windows driver nvSCP.sys.

## What happened

- Checked boot c542daee first (standby-notify entry): LPS0 13 calls, 0 failed with
  `nvidia_ffa_ec.oem_msi_ec=1`; the DSP volume hand-over and resume recovery worked; slowest
  devices per suspend/resume cycle are the two RT1320 amps (~0.5 s each on resume), the GPU
  (~0.39 s) and the NVMe (~0.34 s on suspend).
- Opened [[EXP-20261110-q6a1yn]]. Read-only on Windows (no admin): the hub runs on inbox
  hidspi.sys; nvSCP.sys 2.17.0.0's INF gives two mailboxes' register offsets; radare2 on the
  driver gives its start sequence (calibration blob from UEFI variable `SCPCaliResult` into
  SRAM +0x71000 and command 0x0023FFFF; `NvSCPVar_0..9` as command 0x0011FFFF), the variable
  GUIDs, and the order in which it maps SCP0's memory resources. Details are on the experiment.
- Decided without asking: the first Linux step is read-only and opt-in, a `sudo n1x-scp-peek`
  command (`nix/n1x-scp-peek.py`) in the live image that reads the UEFI variables, the mailbox
  status registers and SCP0's SRAM twice, and saves them to SPARKDATA. Anything that writes to
  the coprocessor waits for Ank's go-ahead.
- [[RUN-20261110-rgc7bg]] (Ank ran `sudo n1x-scp-peek`): nvSCP's UEFI variables are absent; SCP0
  runs MediaTek FreeRTOS firmware that carries the whole sensor hub; mailboxes idle.
- [[RUN-20261110-rs3p36]] (Ank, on Windows): the nvSCP device cannot be disabled, so its service
  was set to Start=4; after a reboot the hub and rotation still work. Proposed conclusion for
  [[EXP-20261110-q6a1yn]], for Ank to sign: the host sends SCP0 nothing the hub needs.
- Opened [[EXP-20261110-rwymta]]: spi-hid enables its IRQ only after `_RST`, so a fast
  single-edge reset response is lost. Added opt-in `irq_before_reset` and
  `poll_after_reset_ms` parameters to our spi-hid copy and `sudo n1x-hub-test`, which
  re-probes both ways while sampling EINT 190's registers (read-only). Built into the image
  (log 16); Ank asked to build, write the stick, and reboot to test.
