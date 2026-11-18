---
id: PHS-20261118-eazdv0
type: phase
schema_version: 1
title: Phase 3 Linux inventory on hardware
project: PRJ-0001
status: done
since: null               # the commit it started at: yajna phase start
until: null               # the commit it finished at: yajna phase done
created: 2026-11-18
author: agent:claude
tags: []
---

## Goal

First Linux boot of the N1X and `sudo bench inventory collect` there. Checked by a collected snapshot, `compare <machine>@windows <machine>@linux` producing the gap list, and ACPI tables identical across OSes.

## Progress
One item per piece of work, ticked when it lands; add items as the plan grows and keep the
done ones. The project page's *Progress* lists this phase on one line.
- [x] First Linux boot of bbaum-pc-7: `sudo bench inventory collect` on real sysfs (phase 3); NixOS live, `osi` and `sspm` entries, 2026-11-07
- [x] First build of the NixOS live image (fill the open-modules hash; check the boot menu)

## Notes
Migrated from PRJ-0001's Progress by `yajna phase migrate`.
