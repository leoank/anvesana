---
id: EXP-20261113-0c42xp
type: experiment
schema_version: 1
title: Why does the sensor hub's accelerometer hang in runtime resume, and why does iio-sensor-proxy get no first sample?
project: PRJ-0001
status: active            # planned | active | paused | concluded | abandoned
outcome: null             # null | positive | negative | inconclusive | infra
influenced_by: [EXP-20261110-rwymta]
created: 2026-11-13
author: agent:claude
review: pending
protocols: []
materials: []
tags: [sensors, spi-hid, iio, accelerometer, runtime-pm]
---

## Question

With the hub working ([[EXP-20261110-rwymta]]), the screen-side accelerometer
(HID-SENSOR-200073.36, iio:device1) hangs: on curiosity (installed NixOS, boot 7d8e8635,
2026-11-12) it sat in runtime-PM `resuming` from 3 s after boot, iio-sensor-proxy's main thread
slept in the kernel (D-Bus clients got no sensor list), and direct reads of `in_accel_*_raw`
waited behind it in `rpm_resume` (the 2026-11-11 n1x-sensors hang). Why, and once past that,
why does iio-sensor-proxy get no first sample?

## Hypothesis and predictions

H1: `_hid_sensor_power_state()` sleeps `msleep_interruptible(poll_value * 2)` with
`poll_value` from `hid_sensor_read_poll_value()`, which returns -EINVAL on a failed or negative
read; -22 * 2 as unsigned is ~49.7 days. If true, kprobes show `pollret ret=-22` followed by
`msleep_interruptible(4294967252)` when the hang happens; if false, a sane poll value and the
sleep is elsewhere.

H2 (after H1 held): the accelerometer reports only on change (hysteresis 0.02 g), so on a desk
iio-sensor-proxy waits 0.5 s in vain and falls back to raw reads, which need GET_INPUT_REPORT.
If true, it streams when moved and not when still, and hysteresis 0 makes it stream when still.

## Plan
1. Root stack of the stuck iio-sensor-proxy; kprobes on the poll read, feature get/set, power
   state and msleep_interruptible, plus the spi_hid trace events; reproduce.
2. Buffered capture still vs. tilting; then hysteresis 0 (written while the sensor is off, as
   a udev rule would).
3. Fixes: kernel patch for the sleep, udev rule for hysteresis, spi-hid not resetting the hub
   on an unanswered GET_INPUT_REPORT.

## Success criteria

After a boot with the fixes: no `resuming` hang, iio-sensor-proxy reports an orientation with
the laptop on a desk, no "Response timed out" in the kernel log.

## Runs
One line per run after its link, what was tried and what it showed; `yajna validate`
rejects a bare link here. Metric runs also land in results.tsv.
- [[RUN-20261113-0c42vk]] kprobes + spi_hid trace, hang reproduced: the hub's feature report carries interval 0xffffffff while the sensor is off, poll read -> -22, msleep_interruptible(4294967252); H1 holds
- [[RUN-20261113-0c43e2]] buffered capture: streams ~46/s when tilted, ~10/s held, ~0 on a desk; hysteresis 0 (accepted while off) gives ~50/s on a desk; H2 holds. GET_INPUT_REPORT never answered

## Conclusion
Written once, by a human, when status becomes `concluded`.
