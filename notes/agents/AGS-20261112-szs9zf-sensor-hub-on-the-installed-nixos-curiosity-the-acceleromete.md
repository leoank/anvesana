---
id: AGS-20261112-szs9zf
type: agent_session
schema_version: 1
title: "Sensor hub on the installed NixOS (curiosity): the accelerometer hang, and the hub in general"
model: "claude-opus-5-5"
harness: "claude-code"
started: 2026-11-12T23:39+00:00
finished: null
created_entities: [EXP-20261113-0c42xp, RUN-20261113-0c42vk, RUN-20261113-0c43e2]
edited_entities: [PRJ-0001]
outcome: pending          # done | failed | aborted | pending
created: 2026-11-12
author: agent:claude
---

## Task

Ank now runs NixOS installed on bbaum-pc-7 (neusis host `curiosity`, anvesana's
`nixosModules.n1x` + `n1x-desktop`). Read the logs and continue on the sensor hub: the hang
on direct accelerometer reads (open in docs/n1x-linux.md) and the hub in general.

## What happened

- Journal of boot 7d8e8635 (the only one kept): hub probed (_RST evaluated, hidraw5).
  Accel HID-SENSOR-200073.36 (iio:device1) stuck in runtime-PM `resuming` since 3 s after
  boot (active_time = uptime, suspended_time 0); iio-sensor-proxy's main thread asleep
  (S), D-Bus clients get no sensor list; IRQ 232 frozen at 112.
- Side issue: Ank's sudo password failed on curiosity. The agenix secret decrypted fine;
  the hash in the secret differed from the password Ank uses on ghost001 (mutableUsers
  keeps ghost001's older shadow entry). Ank fixed it in neusis; comin applied it.
- Root stack (Ank ran it): iio-sensor-proxy in `msleep_interruptible` <-
  `_hid_sensor_power_state` <- `hid_sensor_runtime_resume` <- `rpm_resume` <-
  `buffer_postenable` <- write to buffer/enable. The sleep is `poll_value * 2` ms;
  `hid_sensor_read_poll_value()` returns -EINVAL on failure, which as unsigned is
  ~49.7 days. Earlier "hangs in rpm_resume" were other callers waiting behind it.
- Kprobe repro ([[RUN-20261113-0c42vk]]): poll read -> -22 because the hub reports a
  powered-off sensor's interval as 0xffffffff (and refuses to set one while off), then
  msleep_interruptible(4294967252). Mainline has the same code. Wrote kernel patch 0004
  (`poll_value > 0`).
- Streaming ([[RUN-20261113-0c43e2]]): the accelerometer streams on movement only
  (hysteresis 0.02); hysteresis 0, accepted while off, gives ~50 samples/s on a desk. Added a
  udev rule in `nixosModules.n1x`. The hub never answers GET_INPUT_REPORT; spi-hid no longer
  resets the hub when it goes unanswered. My 2026-11-11 diagnosis (GET_FEATURE vs
  GET_INPUT_REPORT) was wrong: that hang was this sleep.
- Decided without asking: the patch only skips non-positive poll values (no cap on large
  ones); the udev rule matches every accel_3d under spi-MSFW1111; kept GET_INPUT_REPORT
  (reverting to GET_FEATURE would parse feature bytes as input values).
- Not done: kernel and spi-hid not built or booted; nothing committed; `n1x-sensors` still
  uses raw reads; REV-20261031-gfr9da still open, so no review opened for this work.
- Proposed conclusion for [[EXP-20261113-0c42xp]]: H1 and H2 hold; confirm after booting the
  fixes (success criteria on the page).
