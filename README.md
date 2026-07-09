# Foreman

*Write one PRD. Write one design doc. Ship the app.*

---

Foreman is what stands between your OpenCode LLM and a working Flutter
app. You supply two markdown files. It runs a team of specialised
sub-agents through a durable task graph — decomposition, design, code,
tests, review, commit, install — until every task in the graph is done.

**No hand-written tickets. No manual "and now do the next thing." No MCP,
no server, no state machine.** Just bash tools + role prompts + a skill.

---

## Before / after

Ask a raw agent to build the app in your `prd.md` and `design.md`.

Without Foreman, in one turn it tries to write everything at once, loses
half the context, skips tests, ignores the design, and quietly gives up
somewhere near screen four.

With Foreman:

```
$ foreman state resume
{"task": "auth_screen", "category": "ready"}

$ foreman state auto auth_screen
  step 1  foreman spawn architect auth_screen         → task
  step 2  foreman handoff  auth_screen architect      → stdin
  step 3  foreman spawn developer auth_screen …       → task
  step 4  foreman handoff  auth_screen developer      → stdin
  step 5  foreman validate --lines 40
  step 6  foreman spawn reviewer auth_screen          → task
          verdict APPROVED  → commit + state done
                CHANGES_REQUIRED → spawn refactorer
                REJECT       → escalate

$ foreman validate
✓ flutter pub get
✓ dart fix --apply
✓ dart format
✓ flutter analyze         No issues found!
✓ flutter test            All tests passed!

$ foreman commit --task-id auth_screen --desc "email + password login"
$ foreman state done auth_screen
$ foreman state resume
{"task": "profile_screen", "category": "ready"}
```

Every commit is one task. Every sub-agent output is a JSON block validated
against a schema. Every step is logged. Everything is auditable and
resumable.

---

## Install

Prerequisites: Python 3.11+, Flutter SDK, OpenCode, git.
Optional: dart (for `verify --ast`), gh (for `foreman pr`).

```bash
git clone https://github.com/anomalyco/foreman
cd foreman
./install.sh /path/to/your/flutter/project
```

The installer creates two symlinks. Nothing else is copied into your project.

```
your-project/.opencode/skills/foreman.md → foreman/skills/foreman.md
~/.local/bin/foreman                       → foreman/bin/foreman
```

Runtime state lives in `.foreman/` (hidden, per-project, lazy-created).

```bash
export PATH="$HOME/.local/bin:$PATH"   # if not already
foreman doctor                          # sanity-check the install
echo ".foreman/" >> .gitignore          # keep runtime state out of git
```

---

## Your job: write two files

```
your-project/
└── tasks/
    ├── prd.md         ← what to build (features, users, flows, constraints)
    └── design.md      ← how it looks (colours, typography, widgets, spacing)
```

That's it. Everything downstream is derived from these two files by
sub-agents.

Run `foreman init` first to seed empty skeletons — or write them yourself
by hand. The more concrete your `design.md` (exact widget names, hex
colours, spacing units), the fewer round-trips you'll need.

See [End-to-end example](#end-to-end-example) below for a worked pair.

---

## Quick start

**From scratch with your own PRD:**

```bash
cd /path/to/your/flutter/project

foreman init                          # seed prd.md + design.md skeletons
# ... fill them in ...

foreman spawn product_owner            # returns a filled prompt
# → invoke the LLM's `task` tool with the prompt
# → pipe the returned JSON through `foreman handoff init product_owner`
# → then: foreman state import       # bulk-add every task from the PO

foreman state resume                   # next ready task
```

**From an archetype (todo, chat, blog):**

```bash
foreman init
foreman state template todo            # seeds a pre-planned 7-task DAG
foreman state resume
```

Either way, from here the LLM follows `foreman state guide <task>` for one
step at a time, or `foreman state auto <task>` for the whole remaining
sequence.

---

## The team

Eight roles. Each has one job and one JSON output schema.

| Role | Does | Output includes |
|------|------|-----------------|
| **product_owner** | Reads PRD + design, decomposes into tasks | `tasks[]` |
| **architect** | Designs the approach for one task | `approach`, `files[]`, `key_apis`, `edge_cases`, `test_plan` |
| **qa_lead** | Picks the test strategy | `test_strategy`, `coverage_target` |
| **developer** | Writes the code | `files_changed`, `decisions`, `blockers` |
| **tester** | Writes and runs tests | `test_files`, `all_pass` |
| **reviewer** | Audits the diff | `findings[]`, `delete_candidates[]`, `verdict`, `escalate_to` |
| **refactorer** | Applies the reviewer's findings | `fixes_applied[]`, `disputes[]` |
| **debugger** | Root-causes a validate failure | `root_cause`, `fix`, `files_changed` |

Reviewer verdicts: `APPROVED` · `CHANGES_REQUIRED` · `REJECT`.
Escalation targets: `product_owner`, `tech_lead`, `qa_lead`, or `null`.

---

## The pipeline for one task

```
foreman state guide <task>            ← what to do next
   │
   ▼
spawn architect  → task → handoff     ← design
spawn developer  → task → handoff     ← code
foreman validate                      ← pub get · analyze · test
   │
   ├── PASS →  spawn reviewer         ← audit
   │          verdict:
   │            APPROVED  → commit + state done
   │            CHANGES_REQUIRED → spawn refactorer, back to validate
   │            REJECT / escalate_to → stop, loop to PO / tech_lead
   │
   └── FAIL →  spawn debugger  (retry ≤3)
              still failing? rollback + state fail
```

Optional final step (interactive; ask the user which platform):

```
foreman deploy list                     ← see connected devices
foreman deploy install --device <id>    ← build + install
```

---

## Command reference

```
Inspection
  foreman info [--brief|--summary|--filter PATH|--since REF]
  foreman plan [--section NAME]
  foreman next
  foreman doctor
  foreman debt [--path lib/]
  foreman log [N|--summary|--task <id>]

Task DAG (persistent in .foreman/tasks.json)
  foreman state pending|ready|blocked|all|dag|reset
  foreman state add <id> "<desc>" [--deps a,b] [--acceptance "..."]
  foreman state import                       # bulk from stdin
  foreman state template <todo|chat|blog>
  foreman state done <id> [--force]
  foreman state fail <id> [error]
  foreman state task <id>
  foreman state guide <id>                   # next single step
  foreman state auto  <id>                   # remaining full sequence
  foreman state batch [N]                    # N parallel-safe tasks
  foreman state resume                       # find in-flight task
  foreman state escalations

Sub-agents
  foreman spawn <role> <task_id> [--load-from <role>] [--error ...]
                                 [--self-handoff] [--estimate-tokens]
  foreman handoff <task_id> <role>           # stdin: raw sub-agent output

Build gates
  foreman validate [--lines N|--dry-run|--coverage|--min-coverage 70]
  foreman verify   [--task-id ID|--strict|--ast|--ast-only]

Git
  foreman init
  foreman branch <name>
  foreman commit --task-id t3 --desc "..." [--branch feat/t3] [--dry-run]
  foreman rollback [--dry-run]
  foreman pr "<title>" ["<body>"]            # via gh CLI

Deploy
  foreman deploy list [--platform ios|android|macos|web|linux|windows]
  foreman deploy install --device <id> [--mode debug|profile|release]
```

Run `foreman help` for the same list on the terminal.

---

## Auto-tracked state

Handoffs auto-mirror data into `.foreman/tasks.json`. The LLM never
re-echoes what's already recorded.

| Handoff role | Fields written back to task |
|--------------|------------------------------|
| `architect` | `files` ← `[f.path for f in files]` |
| `developer` | `files` ← `files_changed` |
| `reviewer` | `verdict`, `escalate_to` |
| `debugger` | `attempts` (auto-incremented) |
| `commit` | `commit_sha`, `branch` |

Query with `foreman state task <id>` — files, handoffs, verdict,
commit_sha, attempts, conflicts, and any `--force` overrides.

---

## Safety rails

`foreman state done <id>` refuses if:

- Tester says `all_pass: false` → hint: run debugger
- Reviewer says `REJECT` → hint: escalate
- Reviewer says `CHANGES_REQUIRED` → hint: run refactorer

Missing `commit_sha` produces a warning, not a block (trivial tasks may
legitimately have no diff). Bypass with `--force`; every force is
recorded in the audit log.

`foreman state add` refuses unknown deps, circular deps, and duplicates.

`foreman handoff` refuses schema-invalid JSON. `--force` records the
override to `.foreman/handoffs/.forced.jsonl`, which `state guide`
surfaces as a warning.

---

## The YAGNI ladder

Every sub-agent that writes code follows the same ordered ladder:

```
1. Does this need to exist?          → no: skip
2. Already in this codebase?         → reuse
3. dart:core / Flutter SDK does it?  → use it
4. Native platform feature?          → use it
5. Package already in pubspec.yaml?  → use it
6. One line?                         → one line
7. Only then: the minimum that works
```

**Never on the chopping block, even at ultra-YAGNI:** input validation on
trust boundaries, error handling that prevents data loss, security
checks, accessibility.

Deliberate shortcuts get a `// yagni: <reason>` comment. Harvest them
any time with `foreman debt` so *later* doesn't become *never*.

The reviewer emits a `delete_candidates[]` field — code that should be
removed outright, not refactored. The refactorer deletes first, then
tidies the rest.

---

## End-to-end example

A single-page Flutter app: a Material 3 welcome card with a rotating
greeting snackbar. Note how short and concrete both files are — this is
enough to run the whole pipeline without back-and-forth.

`tasks/prd.md`:

```markdown
# Welcome Card — PRD

## Goal
A single-page Flutter app that greets the user with a beautiful, calm
welcome screen. No navigation, no state, no persistence.

## Core Features
- One centred card with an app icon, headline, and short subtitle.
- A primary button labelled "Say hi" that shows a snackbar with a
  rotating greeting from a hardcoded list.
- Adaptive light/dark theme.

## Constraints
- Any Flutter platform.
- No dependencies beyond the Flutter SDK.
- No routing / no other screens.

## Non-goals
Login, backend, i18n, animations beyond default Material.
```

`tasks/design.md` (excerpt):

```markdown
# Welcome Card — Design

## Widget structure
- WelcomeCard — root StatefulWidget
- Scaffold background: subtle vertical gradient
- Center → Card (elevation 2, radius 20) → Padding(32) → Column:
  - Icon(Icons.waving_hand_rounded, 56, primary)
  - Headline "Welcome" (headlineMedium, w600)
  - Subtitle "A little Flutter demo." (bodyMedium, muted)
  - FilledButton.icon(Icons.emoji_emotions_outlined, "Say hi")

## Color
- ColorScheme.fromSeed(seedColor: Colors.teal)
- Light gradient: surface → surfaceContainerHighest
- Dark gradient:  surface → surfaceContainerLow

## Layout
- Base spacing 8dp (uses 8/16/24/32)
- Card max width 360; horizontal padding 24 on smaller screens

## Greetings method
- `_greetings` is a `const List<String>` on the state class
- `_index` increments modulo `_greetings.length` on button press
```

Once those exist under `tasks/`:

```bash
foreman init
foreman state add welcome_screen "Beautiful centered welcome card" \
                                  --acceptance "Card renders; button shows rotating greetings"
foreman state guide welcome_screen
```

Then follow the guide.

---

## Templates

Canned task DAGs for common archetypes:

```
foreman state template todo     # 7 tasks: scaffold, model, storage, list, add, toggle, delete
foreman state template chat     # 6 tasks: chat client with echo bot
foreman state template blog     # 6 tasks: markdown blog reader
```

Templates live at `templates/*.json`. Each declares its target framework
so `foreman state template todo` warns if run outside a Flutter project.
Add your own by writing another `*.json` in the same shape.

---

## Observability

Every tool appends one line to `.foreman/log.jsonl`:

```json
{"ts": 1720498273.412, "tool": "handoff.py", "exit": 0, "ms": 47,
 "role": "architect", "task_id": "auth_screen"}
```

Auto-rotates at 500 lines.

```bash
foreman log 20                    # last 20 raw records
foreman log --summary             # by tool, avg ms, exit codes
foreman log --task auth_screen    # every event for one task
```

`foreman doctor` runs 12 environment checks: FOREMAN_HOME, role prompts,
skill, templates, python3, git, flutter, dart, gh, project layout,
skill symlink, `.foreman/` state.

---

## Testing

```bash
python3 tests/test_tools.py             # run the full suite
python3 tests/test_tools.py --verbose   # stack traces on failure
```

Covers every tool direct and via the wrapper, all 8 role prompts, JSON
schema validation, shell-injection safety, handoff archival + force
tracking + state auto-propagation, cycle and unknown-dep rejection,
safety rails on `state done`, cross-task file conflicts, adaptive
`state auto`, template structural validity, `foreman doctor`, and a
full integration test on a fake Flutter fixture.

---

## Project layout

```
bin/foreman              wrapper (single entry point)
install.sh
skills/foreman.md        the skill loaded by OpenCode

prompts/roles/           product_owner · architect · qa_lead · implementer
                         tester · reviewer · refactorer · debugger

templates/               todo · chat · blog

foreman/
  config.py  models.py  sdk.py  log.py  schemas.py
  proc.py    validator.py  vcs.py  bootstrap.py
  tools/     init · project_info · plan · state · spawn · handoff
             validate · verify · commit · rollback · deploy · debt

tests/test_tools.py
```

---

## FAQ

**Q: Where do I put my PRD and design.md?**
In `<project>/tasks/prd.md` and `<project>/tasks/design.md`. Either
write them yourself before `foreman init`, or let `foreman init` seed
skeletons and edit before spawning the product owner. See
[Your job: write two files](#your-job-write-two-files).

**Q: Which sub-agents actually read the spec files?**
`product_owner` sees both. `architect` and `qa_lead` get `design.md`
excerpts. Every other role prompt reminds the sub-agent that it can
`read tasks/prd.md` / `tasks/design.md` itself for more context.

**Q: Why not MCP?**
MCP requires a server process, lifecycle, protocol layer. Bash + JSON is
simpler, more debuggable, works with any LLM that has a bash tool.

**Q: Can this run without a human?**
The LLM types the commands, but they're mostly `foreman spawn` and
`foreman handoff` — one per sub-agent turn. `foreman state guide` and
`foreman state auto` tell it exactly what to type next. The one place a
human is needed is device deploy (pick platform, connect device).

**Q: What if a sub-agent returns garbage?**
`foreman handoff` refuses to save schema-invalid JSON. Fix the output or
pass `--force` (recorded for audit).

**Q: What if a task fails 3 times?**
`foreman rollback` + `foreman state fail`. The task is marked failed
with the error; the LLM moves on to the next ready task.

**Q: Non-Flutter frameworks?**
`project_info` detects flutter/python/node/rust/go. The role prompts
and templates are Flutter-flavoured but the framework isn't baked in.
Extend by adding non-Flutter templates and adjusting `validator.py`.

**Q: What if I really need the 120-line cache class?**
The reviewer will flag it as `yagni`. Push back with `--force` on
`state done` if you're sure. Every force is logged.

---

## License

MIT.
