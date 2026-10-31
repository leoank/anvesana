# ADR-0012: Keep the notebook LF through `.gitattributes` alone; stop converting pages by hand

Status: accepted
Date: 2026-10-31
Supersedes: ADR-0011

## Context
ADR-0011 answered two problems: yajna 0.18.1's Windows build wrote CRLF pages that its own
validator rejected, and this machine's Git (`core.autocrlf=true`) checks text files out as
CRLF. It pinned `text eol=lf` in `.gitattributes` and added a manual step: convert each page
created on Windows with `sed -i 's/\r$//'`.

yajna 0.19.0, released 2026-10-31 with the upstream fix and installed here as the native
ARM64 Windows build, writes LF. In a scratch notebook, `init project`, `new agent` and `log`
produced no CRLF file, and `yajna validate` passes on this repo. The same release moved its
notebook registry out of the repo (`.local/state/yajna/repos.toml`) into the user's home.

`core.autocrlf=true` is unchanged, so the second problem remains.

Alternatives considered:
- **Drop the `.gitattributes` rule too.** Checkouts on this machine would turn the notebook
  back into CRLF; whether yajna 0.19.0 accepts CRLF it did not write was not tested, and the
  rule costs nothing.
- **Keep ADR-0011 as is.** Its conversion step is now dead weight that new contributors
  would still follow.

## Decision
Keep the `.gitattributes` rule from ADR-0011 unchanged. Drop the manual conversion step:
pages are created with yajna ≥ 0.19.0 and committed as written. Keep the `.local/` entry in
`.gitignore` for anyone still on 0.18.x.

## Consequences
- New pages need no post-processing on Windows.
- Contributors on Windows need yajna ≥ 0.19.0; an older build reintroduces CRLF pages, which
  `yajna validate` reports.
- The `.gitignore` entry for `.local/` can go once no one runs 0.18.x.
