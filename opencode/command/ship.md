---
description: Ship or discover with Foreman (ready gate → autonomous build).
agent: foreman
---

Foreman session. Project root is the current workspace.

You are orchestrator only (`edit` denied). All code via spawn → Task(subagent) → handoff.

Startup:
0. `export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"`
1. `foreman doctor` — fix critical failures
2. `foreman ready` — **GATE**
   - If not ready: **Phase A Discovery only** — question user, then `foreman discover ...`, re-check ready. Do not ship.
   - If ready: **Phase B Ship** below

Phase B Ship:
3. `foreman next` — ready tasks
4. If no tasks: `foreman state template todo` or product_owner → import
5. Each task: `foreman state plan T` → only `remaining_roles` → validate → (verify advisory) → reviewer → **commit** → state done
6. Validate fail: debugger ≤3 then `foreman rollback --task-id T` then fail
7. CHANGES_REQUIRED: refactorer → re-validate
8. Loop `foreman state resume` until nothing ready
9. Never `--force`. Never hard rollback. Never edit lib/test yourself.

User notes: $ARGUMENTS

Do not wait between ship steps. Only stop for deploy, escalations, or discovery questions.
