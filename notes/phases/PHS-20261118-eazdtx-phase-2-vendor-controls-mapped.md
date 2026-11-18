---
id: PHS-20261118-eazdtx
type: phase
schema_version: 1
title: Phase 2 Vendor controls mapped
project: PRJ-0001
status: done
since: null               # the commit it started at: yajna phase start
until: null               # the commit it finished at: yajna phase done
created: 2026-11-18
author: agent:claude
tags: []
---

## Goal

MSI power modes, EC firmware and the keyboard RGB protocol, mapped on Windows. Checked by the admin probe (13 getters, 5 modes mapped to `Get_AP` byte 3) and RGB steady, zones and effects confirmed on hardware.

## Progress
One item per piece of work, ticked when it lands; add items as the plan grows and keep the
done ones. The project page's *Progress* lists this phase on one line.
- [x] MSI power modes mapped to the EC shift-mode byte with the read-only admin probe (ADR-0008)
- [x] Keyboard RGB protocol decoded and verified on hardware; `scripts/msi-mystic-light.py` (ADR-0009)

## Notes
Migrated from PRJ-0001's Progress by `yajna phase migrate`.
