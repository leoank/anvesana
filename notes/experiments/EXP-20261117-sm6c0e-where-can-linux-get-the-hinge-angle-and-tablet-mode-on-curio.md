---
id: EXP-20261117-sm6c0e
type: experiment
schema_version: 1
title: "Where can Linux get the hinge angle and tablet mode on curiosity: the sensor hub's custom sensors or its two accelerometers?"
project: PRJ-0001
status: concluded            # planned | active | paused | concluded | abandoned
outcome: positive             # null | positive | negative | inconclusive | infra
influenced_by: [EXP-20261113-0c42xp]
created: 2026-11-17
author: agent:claude
review: approved
approval: {by: ank, on: 2026-11-18}
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
- [[RUN-20261117-t6mxjd]] first try of n1x-tablet-mode: tablet mode on at 314, off at 101, screen rotates, touchpad off; keyboard stayed on (I2C keyboard not tagged internal); lid switch stayed open
- [[RUN-20261118-020fpn]] with the libinput quirk tagging the I2C keyboard internal: tablet mode on at 284, off at 103, keyboard and touchpad off in tablet mode, screen rotates

## Conclusion
Positive. H1 is false: the custom sensors are not the hinge angle. 2000e1.40 sends [0, 113, 0, 0, 0, 0] in every posture and 2000e1.41
sends nothing ([[RUN-20261117-sm7bfn]]). H2 holds: 200073.36 is in the lid and 200073.39 in the base, the hinge runs along x, and (180 +
atan2(lid_y, lid_z) - atan2(base_y, base_z)) mod 360 gave 114, 178, 309 and 361 degrees for laptop, flat, tent and tablet. The base
sensor reads 4 g; its descriptor misstates its unit, which does not affect the angle. The lid switch stays open at 360 degrees, so it
tells closed from folded back. n1x-tablet-mode turns that angle into SW_TABLET_MODE, on above 200 degrees and off below 160, and passes
the lid's samples to iio-sensor-proxy. With a libinput quirk that tags the I2C keyboard as internal, tablet mode turns off the keyboard
and touchpad and the screen rotates ([[RUN-20261117-t6mxjd]], [[RUN-20261118-020fpn]]). Both success criteria hold, in a hand-run try on
the live system. Not yet checked: the service from a rebuilt image, and suspend/resume.
