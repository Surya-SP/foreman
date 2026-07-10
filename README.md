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
OpenCode agent that drives the loop.

---

## Quick start (autonomous)

Prerequisites: **Python 3.11+**, Flutter SDK, [OpenCode](https://opencode.ai), git.

### 1. Install Foreman once (global)

```bash
git clone https://github.com/Surya-SP/foreman
cd foreman
./install.sh                          # once — all projects
export PATH="$HOME/.local/bin:$PATH"  # for interactive shells
```

`install.sh` also links `foreman` into `/opt/homebrew/bin` or `/usr/local/bin`
when those directories exist and are writable (helps OpenCode GUI shells that
do not load your zshrc).

**Restart OpenCode** after install so it reloads agents under
`~/.config/opencode/`.

### 2. Create a Flutter project first

Foreman does **not** create the Flutter app. You need a real project
(`pubspec.yaml`) before `foreman init` / `foreman run`.

```bash
# new app
flutter create my_app
cd my_app

# or an existing app
cd /path/to/your/flutter/project
```

### 3. Seed specs, then ship

```bash
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

foreman doctor                        # sanity-check install
foreman init                          # seeds tasks/prd.md + design.md if missing;
                                      # runs flutter pub get; git init if needed
# edit tasks/prd.md and tasks/design.md  ← your only real job

foreman run --template todo           # seed todo DAG + launch agent
# or, without a template (agent may seed via product_owner from your PRD):
# foreman run
```

**You do not re-install per project.** Global install puts the `foreman`
agent, role subagents, `/ship`, and skill in `~/.config/opencode/`, plus the
CLI on PATH. Each app only needs a Flutter root, `tasks/prd.md` +
`tasks/design.md`, and (auto-created) `.foreman/` runtime state.

### Same thing in the OpenCode TUI

```bash
cd /path/to/your/flutter/project
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
opencode --agent foreman
# Tab-select "foreman" if needed, then:
/ship
# or type: ship the app from the PRD
```

If bash reports `command not found: foreman` inside OpenCode, the shell PATH
is missing the install location. In that session run:

```bash
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
```

(The foreman agent is instructed to do this automatically.)

`foreman run` is a thin launcher for:

```bash
opencode run --agent foreman --auto --dir <project> --title foreman-ship \
  "Ship this project with Foreman…"
```

Flags: `--template todo|chat|blog`, `--message "…"`, `--model provider/model`,
`--dry-run`, `--no-auto` (skip OpenCode’s auto-approve).

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
| Write PRD + design | Seed task DAG (`state template` or product_owner → import) |
| `foreman run` or `/ship` | For each ready task: architect → qa_lead → developer → tester → validate → reviewer → commit → done |
| Pick deploy device (optional) | Debug loop (agent policy ≤3), refactorer on CHANGES_REQUIRED |
| Resolve escalations / model stalls | Resume from `.foreman/` after interrupt |

**Not autonomous by itself:** typing `foreman spawn` / `state auto` in your
shell. Those are low-level tools. `state auto <id>` **prints a plan**; it does
not call an LLM.

Autonomy depends on OpenCode + a capable model following the agent prompt.
There is no separate forever-running Python daemon. Weak or free models may
stop mid-loop; continue with another `/ship` or `foreman run`.

---

## Install details

```bash
./install.sh                 # recommended: once, global
./install.sh --global-only   # same, explicit
./install.sh /path/to/proj   # global + optional project-local .opencode links
```

Global (always):

```
~/.local/bin/foreman
# also, when writable:
#   /opt/homebrew/bin/foreman  or  /usr/local/bin/foreman
~/.config/opencode/agent/foreman.md + 8 role agents
~/.config/opencode/command/ship.md
~/.config/opencode/skill/foreman/SKILL.md
```

Per project:

```
project/tasks/prd.md, design.md     ← you write (init can seed skeletons)
project/.foreman/                   ← auto-created; do not commit
```

```bash
echo ".foreman/" >> .gitignore
```

`.foreman/` is **runtime state only** (task DAG, handoffs, audit log). It is
not part of the Foreman source tree and is gitignored there.

---

## Pipeline for one task

What the **foreman** agent is instructed to run (also what
`foreman state auto <task>` prints). `state guide <task>` is a shorter hint
and may skip optional roles (e.g. qa_lead / tester).

```
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

spawn architect  → Task(architect) → handoff   (prefer --self-handoff)
spawn qa_lead    → Task(qa_lead)   → handoff
spawn developer  → Task(developer) → handoff   (writes code)
spawn tester     → Task(tester)    → handoff
foreman validate
   ├── PASS → verify → spawn reviewer → handoff  (no self-handoff; Tech Lead reads verdict)
   │          APPROVED  → commit + state done
   │          CHANGES_REQUIRED → refactorer → re-validate
   │          REJECT → escalate / state fail
   └── FAIL → debugger (agent policy: ≤3) else rollback + state fail
```

Then `foreman state resume` / `state ready` for the next task until none remain.

---

## Command reference

```
Autonomous
  foreman run [--template todo|chat|blog] [--message "..."]
              [--model provider/model] [--dry-run] [--no-auto]

Inspection
  foreman info [--brief|--summary|--filter PATH|--since REF|--lines N]
  foreman plan [--section NAME|--lines N|--no-cache]
  foreman next
  foreman doctor
  foreman debt [--path lib/]
  foreman log [N|--summary|--task <id>]

Task DAG  (.foreman/tasks.json)
  foreman state pending|ready|blocked|all|dag|reset
  foreman state add <id> "<desc>" [--deps a,b] [--acceptance "..."]
  foreman state import                       # stdin: {"tasks":[...]} or [...]
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
  foreman spawn <role> [task_id] [--load-from <role>] [--error ...]
                                 [--self-handoff] [--estimate-tokens]
      # roles: product_owner architect qa_lead developer tester
      #        reviewer refactorer debugger
      # product_owner may omit task_id; spawn only prints a prompt
  foreman handoff <task_id> <role>           # stdin: raw output

Build gates
  foreman validate [--lines N|--dry-run|--coverage|--min-coverage PCT]
                   # pub get → dart fix → format → analyze → test
                   # default --min-coverage is 0 (only enforced if set)
  foreman verify   [--task-id ID|--files ...|--strict|--ast|--ast-only]

Git
  foreman init
  foreman branch <name>
  foreman commit --task-id t3 --desc "..." [--branch feat/t3] [--dry-run]
  foreman rollback [--dry-run]
  foreman pr "<title>" ["<body>"]            # requires gh CLI

Deploy
  foreman deploy list [--platform ios|android|macos|web|linux|windows]
  foreman deploy install --device <id> [--mode debug|profile|release]
  foreman deploy install --platform ios      # first matching device
```

`foreman help` prints the live command list.

---

## Manual / low-level use

If you are not using `foreman run`, an OpenCode session with the **foreman**
agent (or any agent following the skill) must still:

1. Ensure PATH includes the CLI (see above)
2. `foreman spawn <role> …` → JSON with `prompt`
3. OpenCode **Task** tool with the matching role agent + that prompt
4. `foreman handoff <task> <role>` with the JSON (or use `--self-handoff`)

Example seed from an archetype:

```bash
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
cd /path/to/flutter/app
foreman init
foreman state template todo
foreman state resume          # e.g. scaffold
foreman state guide scaffold  # next commands (advice only)
# …or just: foreman run
```

Custom PRD path:

```bash
foreman spawn product_owner --self-handoff
# Task agent=product_owner with spawn.prompt
# then import tasks:
#   cat .foreman/handoffs/<id>.product_owner.json | foreman state import
# or pipe the JSON:  printf '%s\n' "$PO_JSON" | foreman state import
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
Reviewer verdicts expected by the agent: `APPROVED` · `CHANGES_REQUIRED` ·
`REJECT`.

OpenCode agent files live in `opencode/agent/`; spawn prompt templates in
`prompts/roles/` (developer uses `implementer.txt`).

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

Also: `log.jsonl` (audit), `handoffs/*.json`, optional `.plan_cache.json`.

---

## Safety rails

`foreman state done <id>` refuses if:

- Tester handoff exists and `all_pass` is `false`
- Reviewer handoff exists and verdict is `REJECT` or `CHANGES_REQUIRED`

Missing `commit_sha` → warning only. Bypass with
`foreman state done <id> --force`.

`foreman handoff` refuses schema-invalid JSON unless `--force`, which is
appended to `.foreman/handoffs/.forced.jsonl` and warned by `state guide`.

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

Then:

```bash
flutter create welcome_card && cd welcome_card
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
foreman init
# paste/edit tasks/prd.md + tasks/design.md
foreman run --template todo
# or let product_owner decompose the PRD:
# foreman run
```

---

## Resume after interrupt

```bash
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
foreman state resume
foreman state task <id>      # handoffs, verdict, attempts
foreman log --task <id>
foreman run                  # agent continues from missing handoffs
# or in TUI: opencode --agent foreman → /ship
```

---

## Testing Foreman itself

From the foreman source repo:

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
Foreman never runs `flutter create` for you. `init` errors if `pubspec.yaml`
is missing.

**Q: Where do PRD and design go?**  
`tasks/prd.md` and `tasks/design.md` (seeded by `foreman init` if absent).

**Q: `command not found: foreman` in OpenCode?**  
OpenCode’s bash often omits `~/.local/bin`. Run
`export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"`,
or re-run `./install.sh` (links into Homebrew/local bin when possible), then
restart OpenCode.

**Q: Why did `foreman state auto` do nothing?**  
It only prints the remaining command sequence. Use `foreman run` or `/ship`.

**Q: Why did `foreman spawn product_owner` only print a prompt?**  
Spawn fills a role prompt. The OpenCode Task tool (or foreman agent) runs the
LLM. Then `state import` loads `tasks[]` into the DAG.

**Q: Why not MCP?**  
Bash + JSON is simpler and debuggable. Works with any agent that has bash.

**Q: Can this run without a human?**  
Mostly: `foreman run` / `/ship` with `--auto`. You still need a working
OpenCode model/provider. The agent may stop for deploy device choice,
escalations, missing PRD/design, or model limits — resume with another
`/ship` or `foreman run`.

**Q: Sub-agent returns garbage?**  
`handoff` rejects invalid schema. Fix and retry, or `--force` (logged to
`.forced.jsonl`).

**Q: Task fails repeatedly?**  
Agent policy is debugger ≤3, then `rollback` + `state fail` and move on.
That limit is in agent instructions, not hard-enforced by the CLI.

**Q: Non-Flutter?**  
`project_info` detects flutter / python / node / rust / go. Role prompts,
templates, and `validate` are Flutter-oriented. Extend templates and
`validator.py` for other stacks.

**Q: Is `.foreman/` needed in the Foreman git repo?**  
No. It is per-app runtime state only; gitignored; safe to delete.

---

## License

MIT.
