---
id: AGS-20261117-sx5phr
type: agent_session
schema_version: 1
title: "Tablet-mode bridge for curiosity: SW_TABLET_MODE and a lid accelerometer from the sensor hub's two accelerometers"
model: claude-opus-5-5
harness: claude-code
started: 2026-11-17T23:35+00:00
finished: null
created_entities: []
edited_entities: [EXP-20261117-sm6c0e]
outcome: pending          # done | failed | aborted | pending
created: 2026-11-17
author: agent:claude
---

## Task

Build the tablet-mode bridge planned in [[EXP-20261117-sm6c0e]]: Ank chose option A (the bridge
reads both accelerometers and hands the lid's samples to iio-sensor-proxy as a uinput
accelerometer) and the thresholds (on above 200 degrees, off below 160).

## What happened

`nix/n1x-tablet-mode.py` (system service in `nix/n1x-desktop.nix`, with a udev rule hiding the
hub's IIO accelerometers from iio-sensor-proxy). Decided without asking: Python without
dependencies (raw uinput ioctls, checked against the kernel's numbers); the lid accelerometer at
10 Hz; 1 s hold before switching; no decision while the lid reads outside 0.85-1.15 g or the
hinge is near vertical; below 15 degrees with the lid switch open counts as folded back (360+).
iio-sensor-proxy's input-accel driver polls EVIOCGABS every 700 ms at 1/256 g per unit, which
fixes the uinput scale. `nix flake check` passes and the unit builds; not yet run on the
hardware: `/tmp/claude-1000/n1x-tablet-test.sh` (root) tries it on the live system.
