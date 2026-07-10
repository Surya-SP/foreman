# Foreman

*Write one PRD. Write one design doc. Ship the app.*

---

Foreman is an **OpenCode primary agent** plus a durable task CLI. You supply
two markdown files. The foreman agent runs a team of specialised sub-agents
through a task graph — decomposition, design, code, tests, review, commit —
until every task is done.

```
┌─────────────────────────────────────────────────────────┐
│  OpenCode primary agent: foreman                        │
│    ├─ product_owner / architect / qa_lead (subagents)   │
│    ├─ developer / tester / refactorer / debugger        │
│    └─ reviewer                                          │
│                                                         │
│  CLI: foreman spawn · handoff · state · validate · …    │
│  State: .foreman/tasks.json + handoffs/                 │
└─────────────────────────────────────────────────────────┘
```

**No hand-written tickets. No MCP server.** Bash tools + role prompts + an
OpenCode agent that actually runs the loop.

---

## Quick start (autonomous)

Prerequisites: Python 3.11+, Flutter SDK, [OpenCode](https://opencode.ai), git.

### 1. Install Foreman once (global)

```bash
git clone https://github.com/Surya-SP/foreman
cd foreman
./install.sh                          # once — all projects
export PATH="$HOME/.local/bin:$PATH"
```

### 2. Create a Flutter project first

Foreman does **not** create the Flutter app. You must have a real project
(with `pubspec.yaml`) before `foreman init` / `foreman run`.

```bash
# new app
flutter create my_app
cd my_app

# or an existing app
cd /path/to/your/flutter/project
```

### 3. Seed specs, then ship

```bash
foreman doctor                        # sanity-check install
foreman init                          # seeds tasks/prd.md + design.md (+ git/pub get)
# edit tasks/prd.md and tasks/design.md  ← your only real job

foreman run --template todo           # autonomous ship (archetype DAG)
# or, without a template (product_owner decomposes your PRD):
# foreman run
```

**You do not re-install per project.** Global install puts the `foreman`
agent + `/ship` in `~/.config/opencode/`. Each project only needs a Flutter
app root, `tasks/prd.md` + `tasks/design.md`, and (auto-created) `.foreman/`
state.

### Same thing in the OpenCode TUI

```bash
cd /path/to/your/flutter/project
opencode --agent foreman
# Tab-select "foreman" if needed, then:
/ship
# or type: ship the app from the PRD
```

`foreman run` is a thin launcher for:

```bash
opencode run --agent foreman --auto --dir <project> "Ship this project…"
```

---

## What you write

```
your-project/
└── tasks/
    ├── prd.md         ← what to build
    └── design.md      ← how it looks
```

Everything else is derived by sub-agents. Concrete `design.md` (widget names,
hex colours, spacing) = fewer round-trips.

---

## What "autonomous" means

| You do | Foreman agent does |
|--------|--------------------|
| Write PRD + design | Seed task DAG (template or product_owner) |
| `foreman run` or `/ship` | For each ready task: architect → qa_lead → developer → tester → validate → reviewer → commit → done |
| Pick deploy device (optional) | Debug loop ≤3, refactorer on CHANGES_REQUIRED |
| Resolve escalations | Resume from `.foreman/` after interrupt |

**Not autonomous by itself:** typing `foreman spawn` / `state auto` in your
shell. Those are low-level tools. `state auto` **prints a plan**; it does not
call an LLM.

---

## Install details

```bash
./install.sh                 # recommended: once, for every project
./install.sh /path/to/proj   # optional: also link agents into that project
```

Global (always):

```
~/.local/bin/foreman
~/.config/opencode/agent/foreman.md + role agents
~/.config/opencode/command/ship.md
~/.config/opencode/skill/foreman/
```

Per project (automatic / manual):

```
project/tasks/prd.md, design.md     ← you write these
project/.foreman/                   ← created on first foreman command
```

```bash
echo ".foreman/" >> .gitignore
```

---

## Pipeline for one task

What the **foreman** agent is instructed to run (also what
`foreman state auto <task>` prints). `state guide` is a shorter
hint and may skip optional roles.

```
spawn architect  → Task(architect) → handoff
spawn qa_lead    → Task(qa_lead)   → handoff
spawn developer  → Task(developer) → handoff   (writes code)
spawn tester     → Task(tester)    → handoff
foreman validate
   ├── PASS → verify → spawn reviewer → handoff
   │          APPROVED  → commit + state done
   │          CHANGES_REQUIRED → refactorer → re-validate
   │          REJECT → escalate / fail
   └── FAIL → debugger (agent policy: ≤3 attempts) else rollback + state fail
```

The agent keeps looping ready tasks until the DAG is empty or blocked.
There is no separate Python “run forever” daemon — autonomy is the
OpenCode agent following that loop via the CLI tools.

---

## Command reference

```
Autonomous
  foreman run [--template todo|chat|blog] [--message "..."]
              [--model provider/model] [--dry-run] [--no-auto]

Inspection
  foreman info [--brief|--summary|--filter PATH|--since REF]
  foreman plan [--section NAME]
  foreman next
  foreman doctor
  foreman debt [--path lib/]
  foreman log [N|--summary|--task <id>]

Task DAG  (.foreman/tasks.json)
  foreman state pending|ready|blocked|all|dag|reset
  foreman state add <id> "<desc>" [--deps a,b] [--acceptance "..."]
  foreman state import                       # bulk from stdin
  foreman state template <todo|chat|blog>
  foreman state done <id> [--force]
  foreman state fail <id> [error]
  foreman state task <id>
  foreman state guide <id>                   # next step (PRINT only)
  foreman state auto  <id>                   # full sequence (PRINT only)
  foreman state batch [N]
  foreman state resume
  foreman state escalations

Sub-agents (used by the foreman agent)
  foreman spawn <role> <task_id> [--load-from <role>] [--error ...]
                                 [--self-handoff] [--estimate-tokens]
  foreman handoff <task_id> <role>           # stdin: raw output

Build gates
  foreman validate [--lines N|--dry-run|--coverage|--min-coverage PCT]
                   # validate = pub get → dart fix → format → analyze → test
  foreman verify   [--task-id ID|--strict|--ast|--ast-only]

Git
  foreman init
  foreman branch <name>
  foreman commit --task-id t3 --desc "..." [--branch feat/t3] [--dry-run]
  foreman rollback [--dry-run]
  foreman pr "<title>" ["<body>"]

Deploy
  foreman deploy list [--platform ios|android|macos|web|linux|windows]
  foreman deploy install --device <id> [--mode debug|profile|release]
```

`foreman help` prints the live command list (same surface area).

---

## Manual / low-level use

If you are not using `foreman run`, an OpenCode session with the foreman
agent (or any agent following the skill) must still:

1. `foreman spawn <role> …` → get `prompt`
2. Invoke OpenCode **Task** with the matching role agent + that prompt
3. `foreman handoff <task> <role>` with the JSON (or use `--self-handoff`)

Example seed from an archetype:

```bash
foreman init
foreman state template todo
foreman state resume          # → scaffold
foreman state guide scaffold  # next commands
# …or just: foreman run
```

---

## The team

| Role | Does | Schema-required keys |
|------|------|----------------------|
| **product_owner** | Reads PRD + design → tasks | `role`, `tasks` |
| **architect** | Approach for one task | `role`, `approach`, `files` |
| **qa_lead** | Test strategy | `role`, `test_strategy` |
| **developer** | Writes code | `role`, `files_changed` |
| **tester** | Writes/runs tests | `role`, `test_files`, `all_pass` |
| **reviewer** | Audits diff | `role`, `findings`, `verdict` |
| **refactorer** | Applies review fixes | `role`, `fixes_applied` |
| **debugger** | Fixes validate failures | `role`, `root_cause`, `fix` |

Extra keys (e.g. `decisions`, `escalate_to`, `coverage_target`) are allowed.
Reviewer verdicts: `APPROVED` · `CHANGES_REQUIRED` · `REJECT`.

---

## Auto-tracked state

Handoffs mirror into `.foreman/tasks.json`:

| Handoff | Fields |
|---------|--------|
| architect | `files` |
| developer | `files` ← `files_changed` |
| reviewer | `verdict`, `escalate_to` |
| debugger | `attempts`++ |
| commit | `commit_sha`, `branch` |

---

## Safety rails

`foreman state done <id>` refuses if:

- Tester handoff exists and `all_pass: false`
- Reviewer handoff exists and verdict is `REJECT` or `CHANGES_REQUIRED`

Missing `commit_sha` → warning only. Bypass checks with
`foreman state done <id> --force` (normal audit log entry only).

`foreman handoff` refuses schema-invalid JSON unless `--force`, which is
recorded in `.foreman/handoffs/.forced.jsonl` and surfaced by `state guide`.

---

## YAGNI ladder

```
1. Does this need to exist?          → no: skip
2. Already in this codebase?         → reuse
3. dart:core / Flutter SDK does it?  → use it
4. Native platform feature?          → use it
5. Package already in pubspec.yaml?  → use it
6. One line?                         → one line
7. Only then: the minimum that works
```

**Never cut:** input validation on trust boundaries, error handling that
prevents data loss, security checks, accessibility.

Mark shortcuts with `// yagni: <reason>`. Harvest with `foreman debt`.

---

## End-to-end example

`tasks/prd.md`:

```markdown
# Welcome Card — PRD

## Goal
A single-page Flutter app that greets the user with a calm welcome screen.

## Core Features
- Centred card with icon, headline, subtitle
- Primary button "Say hi" → snackbar with rotating greeting
- Adaptive light/dark theme

## Constraints
- Flutter SDK only, no routing, no backend
```

Then (inside an existing Flutter app):

```bash
# flutter create welcome_card && cd welcome_card   # if starting fresh
foreman init
# paste/edit prd + design
foreman run --template todo
# or let product_owner decompose the PRD:
foreman run
```

---

## Resume after interrupt

```bash
foreman state resume
foreman state task <id>      # handoffs, verdict, attempts
foreman log --task <id>
foreman run                  # agent continues from missing handoffs
```

---

## Testing Foreman itself

```bash
python3 tests/test_tools.py
python3 tests/test_tools.py --verbose
```

---

## Project layout

```
bin/foreman
install.sh
opencode/
  agent/foreman.md           # primary OpenCode agent
  agent/{roles}.md           # 8 role subagents
  command/ship.md            # /ship
  skill/foreman/SKILL.md
skills/foreman.md            # legacy skill text
prompts/roles/               # spawn prompt templates
templates/                   # todo · chat · blog
foreman/tools/               # CLI tools (state, spawn, handoff, run, …)
tests/test_tools.py
```

---

## FAQ

**Q: Do I create the Flutter project or does Foreman?**  
You create it: `flutter create my_app && cd my_app`, then `foreman init`.
Foreman never runs `flutter create` for you.

**Q: Where do PRD and design go?**  
`tasks/prd.md` and `tasks/design.md` (seeded by `foreman init`).

**Q: Why did `foreman state auto` do nothing?**  
It only prints the remaining command sequence. Use `foreman run`.

**Q: Why did `foreman spawn product_owner` only print a prompt?**  
Spawn fills a role prompt. The OpenCode Task tool (or foreman agent) runs
the LLM. Handoff + `state import` load the tasks.

**Q: Why not MCP?**  
Bash + JSON is simpler and debuggable. Works with any agent that has bash.

**Q: Can this run without a human?**  
Mostly: `foreman run` / `/ship` uses `opencode run --auto`. You still need
a working OpenCode model/provider, and the agent may stop for deploy
device choice, escalations, or missing PRD/design. Autonomy is the agent
loop, not a separate forever-running service.

**Q: Sub-agent returns garbage?**  
`handoff` rejects invalid schema. Fix and retry, or `--force` (logged to
`.forced.jsonl`).

**Q: Task fails repeatedly?**  
Agent policy is debugger ≤3, then `rollback` + `state fail` and move on.
That limit is in the agent instructions, not hard-enforced by the CLI.

**Q: Non-Flutter?**  
`project_info` detects other stacks; prompts/templates are Flutter-flavoured.
Extend templates and `validator.py`.

---

## License

MIT.
