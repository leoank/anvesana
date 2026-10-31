---
id: REV-20261031-gfr9da
type: review
schema_version: 1
title: Architecture, project page and ADRs from the inventory and bring-up work
project: null
target:
  kind: range               # branch | range | page | run | experiment | phase
  ref: HEAD..HEAD
base: 62d79e8451969b747e686f65306a2c6e8cc4c45b
head: 2952c482d7815bd91cc219fb7a2edfb779123483
rounds: [62d79e8451969b747e686f65306a2c6e8cc4c45b, 3c9870eccad4af954299cca00a624709f23426ee]
paths: []
about: [PRJ-0001]
status: open              # open | changes_requested | approved | merged | closed
created: 2026-10-31
author: agent:claude
---

## Summary
Documents the work so far on [[PRJ-0001]]:
- `docs/architecture.md`: goals and constraints, data model, components, stack, phases 0–6, open questions.
- `docs/decisions/ADR-0001`…`ADR-0011` and their index: the inventory design, collection without admin, cross-OS device matching, firmware formats and privacy, opt-in firmware copies, compare verdicts, HID schema, read-only vendor probing, the RGB protocol without flash writes, BIOS in runs, LF notebook files.
- `notes/README.md`: introduction, *Progress* (done and planned phases), open questions, design, lessons.
- Also in the tree, from `yajna init` on 2026-10-31: `yajna.toml`, `notes/` scaffold, `.claude/skills/yajna/SKILL.md`, `.gitattributes`.

Committed on branch `docs/yajna-architecture` as `bc2b91c` (yajna init, `.gitattributes`,
`.gitignore`) and `3c9870e` (architecture, ADRs, project page, session, log). Decisions for the author to check: the eleven ADRs are recorded as `accepted` (made during the work on 2026-10-30/31; ADR-0005 and ADR-0009 follow the author's explicit choices); phases 3–6 are a proposed plan.

Round 3 (`2952c48`): ADR-0012 supersedes ADR-0011 now that yajna 0.19.0 writes LF on
Windows: the `.gitattributes` rule stays, the manual conversion goes. `9cfad2c` in this
range is only the review page's own update.

## Threads
