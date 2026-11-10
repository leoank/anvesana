---
id: EXP-20261110-q6a1yn
type: experiment
schema_version: 1
title: What does the host have to send SCP0 (NVDA8200) for the MSFW1111 sensor hub to start answering on SPI?
project: PRJ-0001
status: active            # planned | active | paused | concluded | abandoned
outcome: null             # null | positive | negative | inconclusive | infra
influenced_by: []
created: 2026-11-10
author: agent:claude
review: pending
protocols: []
materials: []
tags: [sensors, scp, accelerometer]
---

## Question

On Linux the sensor hub (`\_SB.SENH`, MSFW1111, HID over SPI on `\_SB.SPI3`) binds with
spi-hid and its interrupt (EINT 190, IRQ 232) is wired up, but it never raises an interrupt,
so no accelerometer or ambient light sensor appears (boots 2026-11-09/10, see
`nix/spi-hid/README.md`). The hub is served by the SoC's sensor coprocessor `\_SB.SCP0`
(NVDA8200), which on Windows has its own driver, nvSCP.sys, and no Linux driver. What does
nvSCP.sys send to SCP0 that Linux does not?

What is known so far (2026-11-10, from the DSDT, the Windows registry and nvSCP.sys 2.17.0.0
read with radare2; no admin rights needed, nothing written):

- Windows runs the hub with Microsoft's inbox `hidspi.sys`, the same protocol as Linux's
  spi-hid; nothing NVIDIA-specific is in the hub's own driver stack.
- `SENH._RST` writes 1 to 0x1AB20008 (`SETI`); `CLRI` is 0x1AB2000C. Both are in SCP0's third
  memory resource, so the hub's reset is a doorbell into SCP0. Linux's spi-hid does call `_RST`.
- nvSCP's INF sets two mailboxes, Mbox0 and Mbox1, each In status/set 0x100, In clear 0x108,
  Out status/set 0x104, Out clear 0x10C, and `EnableHtCmd`=0. SCP0's `_CRS` resources, in the
  order nvSCP maps them: 0 0x10001000 (4 KB), 1 0x1A800000 (512 KB, SRAM), 2 0x1AB20000,
  3 0x1AAA0000, 4 0x1AAB0000 (4 KB each; 3 and 4 are most likely Mbox0 and Mbox1).
- At start (`fcn.140001300`) nvSCP:
  1. reads UEFI variable `SCPCaliResult` {da86db63-0b44-45a4-ad9a-254393010385} (accepted
     sizes 0xFF8, 0x1FF8, 0x2FF8, 0x3FF8), writes 0xFFFFFFFF, the size, then the data to SRAM
     offset 0x71000 (0x1A871000), and sends mailbox command 0x0023FFFF, payload {0xFFFFFFFF, size};
  2. reads UEFI variables `NvSCPVar_0` to `NvSCPVar_9` (at most 64 bytes each; GUIDs in the
     table below) and sends each as command 0x0011FFFF, length 0x48, payload {index, size,
     data[64]};
  3. separately, a `ManufactureMode` setting is sent by `fcn.140005d90`.
  Messages go through `DMF_Mailbox_SendEnqueue` in 0x104-byte buffers, retried up to 5 times
  1 ms apart. The register-level send sequence (which mailbox, where the bytes go, which
  doorbell) is not worked out yet.
- nvSCP only reads firmware variables (it imports `ExGetFirmwareEnvironmentVariable`, not the
  Set call).

| index | name | GUID |
|---|---|---|
| 0 | NvSCPVar_0 | 39e6129f-9146-47fc-a1c1-198aea0e3830 |
| 1 | NvSCPVar_1 | a827d506-835a-4f4e-b773-a2ea7588dc6e |
| 2 | NvSCPVar_2 | eb700aec-f4be-4029-852c-d4e17c0b2322 |
| 3 | NvSCPVar_3 | 81338e63-d2ca-495b-9815-7251e309c44c |
| 4 | NvSCPVar_4 | ea478c40-8608-4cc5-a0ed-bf23d7502548 |
| 5 | NvSCPVar_5 | 469d2efa-3f30-4d33-a6db-43fee9a38756 |
| 6 | NvSCPVar_6 | 6d2137a0-03d7-46c8-87ef-5c0bd22e088b |
| 7 | NvSCPVar_7 | 3203478b-ec2e-4c09-9f54-baf1fabc2102 |
| 8 | NvSCPVar_8 | 7a75ecfa-5892-4e1c-b817-a0946573819d |
| 9 | NvSCPVar_9 | d8eb2f8f-d5f9-4436-a1d2-d333f3c1ea09 |
| - | SCPCaliResult | da86db63-0b44-45a4-ad9a-254393010385 |

## Hypothesis and predictions

H1: SCP0's firmware is running on Linux but does not start the sensor hub (or does not answer
the `_RST` doorbell) until the host has sent the calibration blob and the NvSCPVar settings
over the mailbox, as nvSCP does at start.

- If H1 is true: on Linux, SCP0's SRAM changes between two reads a few seconds apart (it is
  running), its mailbox status shows nothing from the host, and replaying nvSCP's start
  sequence followed by a hub reset makes IRQ 232 count up and spi-hid read a report descriptor.
- If SCP0 is not running at all on Linux (SRAM static, or reads fault), H1 is false and the
  question becomes who starts it (UEFI, SSPM over SCMI, or nvSCP itself).
- If the replay is done and the hub still stays silent, the start sequence is not enough
  (something else, such as `EnableHtCmd` or a message from SCP0 that the host must answer).

## Plan

1. Read-only look from Linux (opt-in command in the live image, not run automatically):
   which of the 11 UEFI variables exist and their sizes; the mailbox registers in resources 3
   and 4 (0x100-0x10C); the first words of resources 0 and 2; two dumps of the 512 KB SRAM a
   few seconds apart, and the text strings in it (nvSCP has a logger timer, so SCP0 probably
   keeps a log there). Results to SPARKDATA.
2. Finish reading nvSCP's mailbox module: the register writes for a send (`fcn.140021268`
   and the WDF calls under it) and a receive (`fcn.140021a68`), and what SCP0 sends back.
3. Only with the author's go-ahead, since it writes to the coprocessor (volatile SRAM and
   mailbox registers; no flash, no EC): a small Linux module or `/dev/mem` tool that replays
   step 1 and 2 of the start sequence, then resets the hub (rebind spi-hid) and watches IRQ 232.
4. If that works, a proper Linux driver for NVDA8200 that does it at boot and resume.

Update 2026-11-10, after [[RUN-20261110-rgc7bg]] and [[RUN-20261110-rs3p36]]: the answer to the
question looks like "nothing". The UEFI variables are absent, and Windows' hub works with
nvSCP.sys not loaded at all. Steps 2 to 4 are dropped. The difference is on the host side of
the hub, which is the next experiment's question: does EINT 190 latch in the EINT controller
(block 3) when the hub is reset, and does spi-hid get anything if it reads the input report
header without waiting for the interrupt?

## Success criteria

IRQ 232 (EINT 190) counts up after the hub reset, spi-hid reads the hub's report descriptor,
and `hid-sensor-accel-3d` creates an IIO accelerometer whose readings follow the laptop's
orientation.

## Runs
One line per run after its link, what was tried and what it showed; `yajna validate`
rejects a bare link here. Metric runs also land in results.tsv.
- [[RUN-20261110-rgc7bg]] read-only probe from Linux: the UEFI variables nvSCP sends are absent; SCP0 firmware (FreeRTOS, spis-hid, hid_sensorhub, lsm6dsv/lis2dw12/bmm350/tcs3430) is running at a 1 kHz tick; mailboxes idle
- [[RUN-20261110-rs3p36]] Windows with nvSCP.sys kept from loading (service Start=4, device disabled after reboot): the SPI HID hub, both sensor collections and the orientation sensor still work and the screen still rotates, so H1 is false

## Conclusion
Written once, by a human, when status becomes `concluded`.
