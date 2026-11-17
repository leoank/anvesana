---
id: AGS-20261117-smx2zb
type: agent_session
schema_version: 1
title: "Sensor hub on the new curiosity ISO: check the experiment's success criteria and find the hinge angle"
model: claude-opus-5-5
harness: claude-code
started: 2026-11-17T23:21+00:00
finished: 2026-11-17T23:27+00:00
created_entities: [RUN-20261117-smx27c, EXP-20261117-sm6c0e, RUN-20261117-sm7bfn]
edited_entities: [EXP-20261113-0c42xp]
outcome: done             # done | failed | aborted | pending
created: 2026-11-17
author: agent:claude
---

## Task

Ank rebooted curiosity into the curiosity-live ISO built 2026-11-13 with the sensor hub fixes:
check the success criteria of [[EXP-20261113-0c42xp]] and continue the sensor work (the hinge
angle among the custom sensors).

## What happened

Notebooks (anvesana, neusis) had nothing on the sensors after 2026-11-13. At 13:58 the
criteria held on the first boot of the ISO; I wrote the run, a session page and a log line
but did not commit, and the 19:39 reboot took them (the checkout is on the tmpfs root). Redone
on this boot as [[RUN-20261117-smx27c]] with this page; my 23:20 log line, written before I
noticed, linked the lost session page and I pointed it at this one.

`sudo` needs a password here, so Ank ran the `n1x-sensors` posture walk. No custom value is the
hinge angle; the lid and base accelerometers give it within ~5°, which answers the README's
question on tablet mode: opened [[EXP-20261117-sm6c0e]] (active, review pending), recorded
the walk as [[RUN-20261117-sm7bfn]] with `hinge.py` and the 5 KB summary beside it, updated
the sensor hub section of `docs/n1x-linux.md`. The tablet-mode daemon is planned in that
experiment, not started: Ank decides.

Ank concluded [[EXP-20261113-0c42xp]] positive; I wrote the conclusion at Ank's word and left `review: pending` for Ank's sign-off. H1
held (a ~49.7-day power-on sleep on a failed poll read) and H2 held (on-change reports leave
iio-sensor-proxy without a first sample on a desk); patch 0004, the spi-hid change and the
hysteresis rule together give a working accelerometer and orientation on curiosity.
