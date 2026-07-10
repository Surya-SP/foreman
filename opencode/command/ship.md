---
description: Autonomously ship the Flutter app using the Foreman agent (task DAG + role sub-agents).
agent: foreman
---

Ship this project with Foreman. Work autonomously until the task DAG is empty or blocked.

Project root is the current workspace. Follow your system instructions exactly.

Startup checklist:
1. `foreman doctor` — fix critical failures first
2. `foreman next` — see brief + ready tasks
3. If no tasks: seed via `foreman state template todo` (or product_owner → import from PRD)
4. For each ready task: run the full pipeline (architect → qa_lead → developer → tester → validate → reviewer → commit → state done)
5. On validate fail: debugger ≤3 then rollback+fail
6. On CHANGES_REQUIRED: refactorer then re-validate
7. Loop with `foreman state resume` until nothing ready

User notes: $ARGUMENTS

Do not wait for me between steps. Report progress as you complete each task. Only stop for deploy choices, escalations, or missing PRD/design.
