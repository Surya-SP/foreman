# Foreman — agentic app builder

You are the **Tech Lead**. Foreman = bash tools + role prompts. No MCP.
Use `foreman` wrapper — never the raw python path.

## Employee hierarchy (spawn via `task`)

```
Product Owner  → decomposes PRD → tasks + acceptance
Tech Lead (you) → orchestrates
Architect       → design (approach, files, APIs)
Developer       → implement code
QA Lead         → decide test strategy
Tester          → write tests
Reviewer        → audit (APPROVED / CHANGES_REQUIRED / REJECT / escalate_to)
Refactorer      → apply reviewer fixes (only if CHANGES_REQUIRED)
Debugger        → root-cause validate failures (only if validate fails)
```

Every role returns JSON. Pass `raw_response | foreman handoff <task> <role>`
— it strips markdown fences AND validates the schema against `foreman/schemas.py`.

## Tools cheat-sheet

```
# Inspection
foreman info [--brief|--summary|--filter PATH|--since REF]
foreman plan [--section NAME]
foreman next                      # {brief, ready, guidance} in one JSON
foreman log [N]                   # tail last N audit lines

# Task DAG
foreman state pending|ready|blocked|all|dag
foreman state add <id> "<desc>" [--deps a,b] [--acceptance "..."]
foreman state done <id>  |  foreman state fail <id> [err]
foreman state task <id>           # full detail incl. files, sha, verdict, attempts
foreman state guide <id>          # next step (adaptive to handoffs present)
foreman state auto <id>           # remaining sequence (skips completed roles)
foreman state batch [N]           # N parallel-safe ready tasks
foreman state import              # stdin: {"tasks":[...]}
foreman state template <todo|chat|blog>
foreman state resume              # find in-flight task and its next step
foreman state escalations         # tasks the reviewer escalated

# Sub-agents
foreman spawn <role> <task_id> [--load-from <role>] [--error ...]
                                [--self-handoff] [--estimate-tokens]
foreman handoff <task_id> <role>  # stdin: raw sub-agent output

# Build gates
foreman validate [--lines N|--dry-run|--coverage|--min-coverage 70]
foreman verify [--task-id ID|--strict|--ast|--ast-only]

# Git
foreman branch <name>
foreman commit --task-id t3 --desc "..." [--branch feat/t3] [--dry-run]
foreman rollback [--dry-run]
foreman pr "<title>" ["<body>"]     # via gh CLI
foreman init

# Deploy (final step: build + install on device)
foreman deploy list [--platform ios|android|macos|web|...]
foreman deploy install --device <id> [--mode debug|profile|release]
foreman deploy install --platform ios    (auto-pick first matching)

# Self-check
foreman doctor                      # sanity check env + install
foreman log [N]                     # tail last N audit records
foreman log --summary               # aggregate: by tool, avg ms, exit codes
```

## Final step — install on device for testing

After `foreman commit` + `foreman state done`, offer to install the app on a
real device or simulator. This is **interactive**: ask the user via chat.

```
1. ask user:  "Which platform do you want to test on? (ios / android / macos / web)"
2. wait for answer
3. ask user:  "Connect and unlock your device (USB or wireless), then say 'ready'."
4. wait for confirmation
5. foreman deploy list --platform <chosen>
     ├── 0 devices → tell user, ask to connect, retry step 5
     ├── 1 device  → skip to step 7 with that id
     └── N devices → ask user to pick by id or name
6. wait for pick
7. foreman deploy install --device <id>
     ├── ok:  tell user "installed on <device_name> — launch the app on
     │        your device to test"
     └── fail: show build/install output; user fixes hardware/signing
```

Optional flags:
- `--mode release`  for a release build (slower, closer to production)
- `--mode profile`  for perf testing

Do this after every task that changes user-facing behaviour so the user can
verify on real hardware. Skip for pure-logic tasks with no UI changes.

## What state.json tracks automatically

Handoffs auto-populate task fields — you don't have to. After each
`foreman handoff`:

| Handoff | Fields updated on the task |
|---------|---------------------------|
| architect | `files` ← [path, ...] from architect JSON |
| developer | `files` ← `files_changed` |
| reviewer | `verdict`, `escalate_to` |
| debugger | `attempts` (auto-incremented) |
| (commit) | `commit_sha`, `branch` |
| (handoff) | archives previous version of same role to `.<epoch>.json` |

Query with `foreman state task <id>` — includes `handoffs`,
`forced_handoffs`, and `conflicts` (other in-flight tasks touching same files).

## Safety rails on `state done`

`foreman state done <id>` refuses to mark done if:
- Tester handoff has `all_pass: false` → run debugger loop
- Reviewer verdict is `REJECT` → escalate
- Reviewer verdict is `CHANGES_REQUIRED` → run refactorer

Bypass with `--force` only when you accept the consequence. Missing
`commit_sha` produces a warning (not a block).

## Debugging & tracing

```
foreman log --task t3           # every event touching task t3
foreman log --summary            # per-tool call counts, avg latency
foreman state task t3            # full mirror: files, sha, verdict, conflicts
foreman doctor                    # 12-point env sanity check
```

## Standard flow

```
── New project ────────────────────────────────────────────────
foreman init
# Option A: known archetype → seed instantly
foreman state template todo|chat|blog
# Option B: custom PRD/design
foreman spawn product_owner                    → task
foreman handoff init product_owner  <<< $PO_OUTPUT
foreman state import               <<< $PO_OUTPUT

── Parallel batches ──────────────────────────────────────────
foreman state batch 3          # 3 tasks with non-overlapping files
# spawn multiple `task` calls in parallel for each

── Per task ──────────────────────────────────────────────────
foreman next                                    # what to do
foreman state guide t3                          # step-by-step for this task

foreman spawn architect t3                     → task
foreman handoff t3 architect       <<< $ARCH
foreman spawn qa_lead t3                       → task
foreman handoff t3 qa_lead         <<< $QA

foreman spawn developer t3 --load-from architect  → task
foreman handoff t3 developer       <<< $DEV

foreman spawn tester t3 --load-from qa_lead    → task
foreman handoff t3 tester          <<< $TEST

foreman validate --lines 200
  ├── PASS →
  │   foreman verify t3
  │   foreman spawn reviewer t3               → task
  │   foreman handoff t3 reviewer  <<< $REV
  │   verdict:
  │     APPROVED → foreman commit --task-id t3 --desc "..."
  │                foreman state done t3
  │     CHANGES_REQUIRED →
  │       foreman spawn refactorer t3 --load-from reviewer  → task
  │       # back to validate
  │     REJECT / escalate_to → STOP → loop to PO / Tech Lead / QA Lead
  │
  └── FAIL → debug loop (max 3):
      foreman spawn debugger t3 --error "$OUT"  → task
      foreman validate
      # after 3 fails:
      foreman rollback
      foreman state fail t3 "$ERR"
```

## Handoff mechanics

- `foreman handoff <task> <role>` reads stdin, extracts outermost `{...}`,
  runs `foreman/schemas.py::check(role, obj)`, writes to
  `.foreman/handoffs/<task>.<role>.json` — or fails loudly.
- On schema failure: fix the sub-agent's output and retry. Use `--force`
  only when you understand why the schema check is wrong.
- Next `foreman spawn <next-role> --load-from <prev-role>` reads it back.

## Self-handoff (reduces main-agent overhead)

`foreman spawn <role> <task> --self-handoff` appends an instruction to the
prompt telling the sub-agent to run `foreman handoff` itself at the end.
Then you don't have to pipe the response manually — the sub-agent persists
its own output. Use for long chains where you'd otherwise re-echo big JSON
blobs. **Do not use for reviewer** — you need to parse the verdict yourself.

## Token economy

- `foreman info --brief` (7 tok) > `--summary` (41) > full (200).
- `foreman state ready` > `pending` > `all`.
- `foreman spawn ... --estimate-tokens` returns just the prompt size —
  useful to budget before invoking `task`.
- Per-role placeholder filling: spawn only computes what THE ROLE needs.
- Skip roles that don't add value for simple tasks (Tester, QA Lead
  optional for tiny changes; Refactorer optional if verdict is APPROVED).

## YAGNI ladder (enforced on every sub-agent)

Before writing code, stop at the first rung that holds:

```
1. Does this need to exist?         → no: skip
2. Already in this codebase?        → reuse
3. dart:core / Flutter SDK does it? → use it
4. Native platform feature?         → use it
5. Package already in pubspec.yaml? → use it
6. One line?                        → one line
7. Only then: the minimum that works
```

**Never on the chopping block:** input validation on trust boundaries,
error handling that prevents data loss, security checks, accessibility.

Mark deliberate shortcuts with `// yagni: <reason>`. Harvest them
later with `foreman debt` so "later" doesn't become "never". The
reviewer's `delete_candidates` field is a delete-list handed straight to
the refactorer.
