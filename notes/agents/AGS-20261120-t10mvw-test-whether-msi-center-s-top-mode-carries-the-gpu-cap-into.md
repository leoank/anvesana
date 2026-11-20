---
id: AGS-20261120-t10mvw
type: agent_session
schema_version: 1
title: Test whether MSI Center's top mode carries the GPU cap into Linux
model: claude-opus-5-5
harness: claude-code
started: 2026-11-20T23:41+00:00
finished: 2026-11-20T23:41+00:00
created_entities: [RUN-20261120-stydn9]
edited_entities: [EXP-20261118-ejmvrd]
outcome: done             # done | failed | aborted | pending
created: 2026-11-20
author: agent:claude
---

## Task

Ank set MSI Center's top performance mode on Windows and rebooted into Linux: run cuBLASLt
and see whether the GPU passes the ~51 W cap (the write-free test from [[RUN-20261120-g7hznd]]).

## What happened

Ran cuBLASLt alone with the bench's telemetry and `nvidia-smi` sampling clock event reasons
([[RUN-20261120-stydn9]]): 52.1 W average, SW power cap active through the load, no change.
The page was created with a wrong script path at first (named before the ID existed); I moved
the stub to the run's own folder. Under [[REV-20261120-g7hvet]]; not committed (not asked).
