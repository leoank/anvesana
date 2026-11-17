---
id: EXP-20261117-sm6c0e
type: experiment
schema_version: 1
title: "Where can Linux get the hinge angle and tablet mode on curiosity: the sensor hub's custom sensors or its two accelerometers?"
project: PRJ-0001
status: active            # planned | active | paused | concluded | abandoned
outcome: null             # null | positive | negative | inconclusive | infra
influenced_by: [EXP-20261113-0c42xp]
created: 2026-11-17
author: agent:claude
review: pending
protocols: []
materials: []
tags: [sensors, hinge, tablet-mode, accelerometer, iio]
---

## Question

Curiosity is a convertible (laptop, flat, tent, tablet) but Linux has no tablet-mode switch:
`/proc/bus/input/devices` shows `SW_LID` (Lid Switch) and jack switches only, no
`SW_TABLET_MODE`, so GNOME never enters tablet mode. MSI Center sets `ConvertibleSlateMode`
itself on Windows. Where can Linux get the hinge angle: from the sensor hub's custom sensors
(HID-SENSOR-2000e1.40 with six s16 values, .41 with one), or from its two accelerometers
(200073.36 and 200073.39)?

## Hypothesis and predictions
H1: one of the custom values is the hinge angle. If true, it changes with the posture and
tracks the angle; if false, none does.

H2: the two accelerometers sit one in the lid, one in the base, with the hinge along a common
axis. If true, the angle between their gravity vectors in the plane across the hinge gives the
hinge angle in every posture except with the hinge vertical.

## Plan
1. `n1x-sensors` posture walk (laptop ~110°, flat, tent, tablet), 8 s each, recording both
   accelerometers and both custom sensors.
2. If H2 holds: a small daemon reads both accelerometers and exposes `SW_TABLET_MODE` through
   uinput (on above a threshold angle, off below it, with hysteresis), in `nix/`.

## Success criteria

A value that tracks the hinge angle within ~10° in all four postures, and GNOME entering and
leaving tablet mode as the screen folds back and returns.

## Runs
One line per run after its link, what was tried and what it showed; `yajna validate`
rejects a bare link here. Metric runs also land in results.tsv.
- [[RUN-20261117-sm7bfn]] posture walk: the custom sensors do not change (.40 stays 0,113,0,0,0,0; .41 sends nothing), H1 false; the lid and base accelerometers give 114/178/309/361° for laptop/flat/tent/tablet, H2 holds; the base one reads 4 g

## Conclusion
Written once, by a human, when status becomes `concluded`.
