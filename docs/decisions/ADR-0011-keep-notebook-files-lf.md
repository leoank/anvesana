# ADR-0011: Keep the notebook's files LF in git and in checkouts

Status: superseded by ADR-0012
Date: 2026-10-31

## Context
This repo became a `project`-shaped yajna notebook on 2026-10-31, initialised on the
Windows machine with yajna 0.18.1 (x86-64 build, under emulation on ARM64). Two problems
combined:
- **The Windows build writes CRLF.** Pages created by `init`, `new` and `log` use CRLF line
  endings, and its validator rejects CRLF frontmatter ("the frontmatter does not parse").
  The bug has been reported upstream.
- **Git converts back to CRLF.** This machine's Git has `core.autocrlf=true`, so it would
  check LF files out as CRLF again after a clone or branch switch.

Alternatives considered:
- **Change `core.autocrlf` on this machine.** It doesn't travel with the repo.
- **Wait for the upstream fix.** The notebook is unusable on Windows until then.

## Decision
`.gitattributes` pins `text eol=lf` for `yajna.toml`, `notes/**`, `docs/architecture.md`,
`docs/decisions/**` and `.claude/skills/**`. Until yajna is fixed, each page created on
Windows is converted after creation (`sed -i 's/\r$//' <file>`).

## Consequences
- Checkouts on any OS give LF notebook files, and `yajna validate` passes.
- New pages created on Windows are invalid until converted; the conversion step goes away
  with the upstream fix, and this record should then be marked superseded or amended.
