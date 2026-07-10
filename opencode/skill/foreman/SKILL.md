---
name: foreman
description: Use when shipping a Flutter app from tasks/prd.md and tasks/design.md with the Foreman task DAG, or when the user says foreman, ship the app, or run the multi-agent build pipeline.
---

# Foreman skill (Tech Lead reference)

You are driving the **Foreman** pipeline. Prefer the **foreman** primary agent when available (Tab to switch, or `/ship`). Use the `foreman` CLI — never raw python tool paths.

## One-line model

```
seed tasks → for each ready task → spawn role → Task(subagent) → handoff → validate → review → commit → done → next
```

`foreman state auto <id>` **prints** that sequence; it does **not** execute it. You execute it.

## Seed

Must already be inside a Flutter project (`pubspec.yaml`). If not:
`flutter create my_app && cd my_app` first.

```bash
foreman init
foreman state template todo          # OR product_owner path below
# custom:
foreman spawn product_owner --self-handoff
# Task → agent product_owner → then:
foreman state import                 # stdin: {"tasks":[...]}
```

## One task

```bash
foreman state resume                 # → task id
foreman spawn architect T --self-handoff     # Task agent=architect
foreman spawn qa_lead T --self-handoff       # Task agent=qa_lead
foreman spawn developer T --load-from architect --self-handoff
foreman spawn tester T --load-from qa_lead --self-handoff
foreman validate --lines 200
# PASS:
foreman verify --task-id T
foreman spawn reviewer T                     # Task agent=reviewer, NO self-handoff
printf '%s\n' "$REV" | foreman handoff T reviewer
# APPROVED → commit + state done
# CHANGES_REQUIRED → refactorer → re-validate
# FAIL validate → debugger ≤3 → else rollback + state fail
```

## Safety

- `state done` blocks on tester all_pass=false, REJECT, CHANGES_REQUIRED
- handoff refuses invalid schema (fix or --force with audit)
- `foreman log --task T` for debugging

## YAGNI ladder

Need? → reuse? → SDK? → native? → pubspec? → one line? → minimum.

Never cut: validation on trust boundaries, data-loss errors, security, a11y.
