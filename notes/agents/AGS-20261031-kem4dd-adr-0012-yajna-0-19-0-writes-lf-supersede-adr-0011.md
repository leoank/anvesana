---
id: AGS-20261031-kem4dd
type: agent_session
schema_version: 1
title: "ADR-0012: yajna 0.19.0 writes LF; supersede ADR-0011"
model: claude-opus-5-5
harness: claude-code
started: 2026-10-31T17:42+00:00
finished: 2026-10-31T17:43+00:00
created_entities: []
edited_entities: [PRJ-0001, REV-20261031-gfr9da]
outcome: done             # done | failed | aborted | pending
created: 2026-10-31
author: agent:claude
---

## Task

## What happened
Ank asked for an ADR recording that yajna 0.19.0 fixes the Windows CRLF bug, committed under
the open review [[REV-20261031-gfr9da]].

## What happened
- Earlier in the conversation: installed yajna 0.19.0 (native `aarch64-pc-windows-msvc`,
  checksum verified; 0.18.1 kept as `yajna-0.18.1-x86_64.exe`). In a scratch notebook,
  `init`, `new agent` and `log` wrote no CRLF and nothing under `.local/` in the repo.
- Wrote `docs/decisions/ADR-0012-keep-gitattributes-lf-drop-manual-conversion.md`: keep the
  `.gitattributes` rule (this machine still has `core.autocrlf=true`), drop the manual
  conversion. ADR-0011's status changed to "superseded by ADR-0012"; nothing else in it was
  edited. Index row, the architecture's notebook paragraph and the *Lessons* line on
  [[PRJ-0001]] updated.
- Decided without asking: keep the `.local/` line in `.gitignore` for anyone still on
  0.18.x; did not test whether 0.19.0 accepts CRLF pages it did not write.
- Committed as `2952c48`; `yajna review update` moved the review's head 3c9870e -> 2952c48 (round 3) and its summary names the commit.
