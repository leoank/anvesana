---
id: EXP-20261110-rwymta
type: experiment
schema_version: 1
title: "Why does the sensor hub never interrupt on Linux: is the reset response's edge lost before spi-hid enables its IRQ?"
project: PRJ-0001
status: active            # planned | active | paused | concluded | abandoned
outcome: null             # null | positive | negative | inconclusive | infra
influenced_by: [EXP-20261110-q6a1yn]
created: 2026-11-10
author: agent:claude
review: pending
protocols: []
materials: []
tags: [sensors, spi-hid, eint, accelerometer]
---

## Question

[[EXP-20261110-q6a1yn]] showed that the sensor hub needs nothing from the host's coprocessor
driver: on Windows it works with nvSCP.sys not loaded ([[RUN-20261110-rs3p36]]), and on Linux
the coprocessor's firmware, which carries the whole hub (spis-hid, hid_sensorhub), is running
([[RUN-20261110-rgc7bg]]). Yet on Linux spi-hid binds, calls `_RST`, and the hub's interrupt
(EINT 190, IRQ 232) never fires. Windows wires the same interrupt the same way (a GpioInt on
the GPIO controller NVDA9221, GIC 0x233; RUN-20261110-rs3p36's check). Where is the reset
response lost?

## Hypothesis and predictions

H1: the coprocessor answers `_RST` quickly with one falling edge, before spi-hid enables the
IRQ: spi-hid requests it with `IRQF_NO_AUTOEN` and calls `enable_irq()` only after
`deassert_reset` (`_RST`), so the EINT is still masked and the edge is lost. Windows' hidspi
connects its interrupt before resetting.

- If H1 is true: with the IRQ enabled before the reset (`spi_hid.irq_before_reset=1`), IRQ 232
  counts up, spi-hid handles the reset response, and the hub's HID device (and an IIO
  accelerometer) appears. In the normal order, the one-shot poll finds a valid reset response
  header (sync byte 0x5A) waiting.
- If the EINT status bit for 190 sets but IRQ 232 does not count, the EINT controller latches
  the edge and the problem is between it and the GIC (block 3's interrupt, or the mask).
- If neither order gives an interrupt and the poll reads only 0x00 or 0xFF, the hub is not
  answering on SPI at all after `_RST`, and the doorbell or SPI3 itself is next.

## Plan

1. Opt-in test parameters in our spi-hid copy (`nix/spi-hid/spi-hid-core.c`, marked
   `anvesana`, both off by default): `irq_before_reset` and `poll_after_reset_ms`.
2. `sudo n1x-hub-test` in the live image (`nix/n1x-hub-test.py`): re-probes the driver in
   both orders with a 1.5 s poll, samples EINT 190's bits in block 3 (status, mask,
   sensitivity, polarity, domain enable) every 20 ms for 3 s, and records IRQ 232 and the
   driver's log. Read-only apart from what the driver's probe does anyway.
3. Depending on the result: make the working order the default (and report it upstream to
   the spi-hid series), or follow the EINT/GIC path, or the doorbell.

Update 2026-11-10, after [[RUN-20261110-sd3esk]]: H1 is false (no response in either order,
EINT status never set). The doorbell was the problem: spi-hid-acpi's reset never evaluated
`_RST` at all (`device_reset()` on an `acpi_device`'s own struct device finds no ACPI handle;
details on the run). H2: with `_RST` really evaluated, the coprocessor resets the hub and
answers; prediction: "anvesana: _RST evaluated" in dmesg, IRQ 232 counts, the reset response
is handled, and the HID sensor collection with an accelerometer appears. Next run: the same
`n1x-hub-test` on an image with that fix.

## Success criteria

IRQ 232 counts up after a probe, spi-hid reads the hub's report descriptor, and
`hid-sensor-accel-3d` creates an IIO accelerometer.

## Runs
One line per run after its link, what was tried and what it showed; `yajna validate`
rejects a bare link here. Metric runs also land in results.tsv.
- [[RUN-20261110-sd3esk]] re-probe in both IRQ orders with a 1.5 s poll: no interrupt, EINT 190 status never set, polled headers invalid (00s, d8s); then found that `_RST` was never evaluated (device_reset on the acpi_device finds no handle)
- [[RUN-20261110-t3crtm]] with `_RST` evaluated the hub answers (IRQ 232 counts, valid headers), but its 2972-byte report descriptor fails the core's 2048-byte max_input_length check and the probe times out

## Conclusion
Written once, by a human, when status becomes `concluded`.
