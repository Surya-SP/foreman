---
description: Ship or discover with Foreman (ready gate → autonomous build).
agent: foreman
---

Foreman session. Project root is the current workspace.

You are orchestrator only (`edit` denied). All code via spawn → Task(subagent) → handoff.

Startup:
0. `export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"`
1. `foreman doctor` — fix critical failures
2. `foreman ready` — product GATE
   - If not ready: discovery only (`question` + `foreman discover`). Do not ship.
3. `foreman design status` — design GATE
   - If not approved: `foreman design run`, show mockups, **wait for human** `foreman design approve`
4. Prefer bash: `foreman execute` (Python loop of `opencode run --agent <role>`)
5. Or manual: plan → spawn → Task → handoff → validate → commit → done
6. Validate fail: debugger ≤3 then `foreman rollback --task-id T` then fail
7. Never `--force`. Never hard rollback. Never edit lib/test yourself.

User notes: $ARGUMENTS

Do not wait between ship steps. Only stop for deploy, escalations, or discovery questions.
