# Foreman — agentic app builder

You are the **Tech Lead**. Prefer the OpenCode **foreman** primary agent
(Tab to select, or `foreman run` / `/ship`). Use the `foreman` CLI wrapper —
never raw python paths.

## Autonomy model

```
foreman run                          # launches opencode --agent foreman --auto
opencode --agent foreman → /ship     # same agent in TUI
```

You drive the loop. `state guide` / `state auto` only **print** plans.

```
seed tasks → for each ready task:
  spawn role → OpenCode Task(subagent=role) → handoff → validate → review → commit → done
```

## Role hierarchy (OpenCode subagents)

| Role | OpenCode agent | Edits code? |
|------|----------------|-------------|
| product_owner | product_owner | no |
| architect | architect | no |
| qa_lead | qa_lead | no |
| developer | developer | yes |
| tester | tester | yes (tests) |
| reviewer | reviewer | no |
| refactorer | refactorer | yes |
| debugger | debugger | yes |

Every role returns JSON. Persist with `foreman handoff <task> <role>`.

## Tools cheat-sheet

```
foreman run [--template todo] [--message "..."] [--dry-run]
foreman next                      # brief + ready + guidance
foreman doctor

foreman state pending|ready|blocked|all|dag|reset|resume|escalations
foreman state add <id> "<desc>" [--deps a,b] [--acceptance "..."]
foreman state done <id>  |  foreman state fail <id> [err]
foreman state task <id>
foreman state guide <id>          # next step (PRINT only)
foreman state auto <id>           # full sequence (PRINT only)
foreman state batch [N]
foreman state import              # stdin: {"tasks":[...]}
foreman state template <todo|chat|blog>

foreman spawn <role> [task_id] [--load-from <role>] [--error ...] [--self-handoff]
foreman handoff <task_id> <role>  # stdin: raw sub-agent output

foreman validate [--lines N|--dry-run|--coverage]
foreman verify [--task-id ID|--strict|--ast]
foreman commit --task-id t3 --desc "..." [--branch feat/t3]
foreman rollback | foreman init | foreman branch <name> | foreman pr "..."
foreman deploy list|install ...
foreman log [N|--summary|--task id] | foreman debt | foreman info | foreman plan
```

## Standard flow

```
── Bootstrap ────────────────────────────────────────────────
# Must already be a Flutter project:
#   flutter create my_app && cd my_app
foreman init
# Option A: archetype
foreman state template todo|chat|blog
# Option B: custom PRD
foreman spawn product_owner --self-handoff
# Task agent=product_owner → then:
foreman state import               <<< $PO_JSON

── Autonomous ───────────────────────────────────────────────
foreman run                        # preferred
# or opencode --agent foreman + /ship

── Per task (what the agent executes) ───────────────────────
foreman state resume
foreman spawn architect T --self-handoff      → Task agent=architect
foreman spawn qa_lead T --self-handoff        → Task agent=qa_lead
foreman spawn developer T --load-from architect --self-handoff
foreman spawn tester T --load-from qa_lead --self-handoff
foreman validate --lines 200
  PASS → verify → spawn reviewer (NO self-handoff) → handoff
         APPROVED → commit + state done
         CHANGES_REQUIRED → refactorer → re-validate
  FAIL → debugger ≤3 → else rollback + state fail
```

## Self-handoff

`foreman spawn <role> <task> --self-handoff` tells the sub-agent to run
`foreman handoff` itself. Use for all roles except **reviewer** (you need
the verdict).

## Safety rails on `state done`

- Tester `all_pass: false` → debugger
- Reviewer `REJECT` → escalate
- Reviewer `CHANGES_REQUIRED` → refactorer
- Missing `commit_sha` → warning only

## YAGNI ladder

1 Need? 2 Reuse? 3 SDK? 4 Native? 5 pubspec? 6 One line? 7 Minimum.

Never cut: trust-boundary validation, data-loss errors, security, a11y.
