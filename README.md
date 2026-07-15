# Foreman

Local **control plane** for shipping Flutter apps with [OpenCode](https://opencode.ai).

Foreman does **not** call LLM APIs. It:

1. Gates product docs (`discover` → `ready`)
2. Gates a human-approved design language (`design run` → `show` → `approve`)
3. Runs a **Python loop** that, for each planned role, runs  
   `opencode run --agent <role>` → handoff JSON → validate → commit → next task

Quality depends on your **OpenCode install**, **model**, and **docs**. Weak models stall; re-run `foreman run`.

```text
foreman discover → ready → design approve → run
```

The Flutter app lives **outside** this repo (`flutter create` anywhere).  
This repo is only the tool (CLI + OpenCode agents + prompts).

---

## Requirements

| Dependency | Role |
|------------|------|
| [Flutter](https://docs.flutter.dev/get-started) | App project (`pubspec.yaml`) |
| [OpenCode](https://opencode.ai) | Role agents (`opencode run --agent …`) |
| Python 3 | CLI tools under `foreman/tools/` |
| git | Per-task commits, resume |

Optional: [ripgrep](https://github.com/BurntSushi/ripgrep) (`rg`) for code search; `gh` for `foreman pr`.

---

## Install (once, global)

```bash
git clone https://github.com/Surya-SP/foreman
cd foreman
./install.sh
export PATH="$HOME/.local/bin:$PATH"
```

What install does:

- Symlinks CLI → `~/.local/bin/foreman` (and Homebrew/local bin if writable)
- Symlinks OpenCode agents/command/skill → `~/.config/opencode/`
- Does **not** create a Flutter app inside this repo

Restart OpenCode after install so agents reload.

---

## Ship a Flutter app

```bash
flutter create my_app && cd my_app
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

foreman doctor
foreman discover              # writes tasks/prd.md + tasks/design.md
foreman ready                 # exit 0 only if docs pass heuristics
foreman design run            # OpenCode designer → draft + mockups
foreman design show           # review (.foreman/design_preview.md)
foreman design approve        # writes tasks/design_language.md
foreman run                   # execute loop: OpenCode per role until DAG empty
```

### What each gate does

| Step | Tool behavior |
|------|----------------|
| `discover` | Interactive or flags → markdown PRD/design |
| `ready` | Heuristic check (length, features, not empty template). Exit 1 if not ready |
| `design run` | `opencode run --agent designer` (or mock in `prove`) → handoff `design.designer.json` |
| `design approve` | Human only → `tasks/design_language.md` + approved status |
| `run` | If not ready → discovery OpenCode session. If design not approved → exit 2 with `WAITING FOR: design approve`. Else → `execute` |

### What `foreman run` does after gates pass

1. Seed task DAG if empty (`state template todo` when using templates, or empty until seeded)
2. For each ready task from `.foreman/tasks.json`:
   - `state plan <id>` → profile + `remaining_roles` (not always full pipeline)
   - For each role: `spawn` prompt → `opencode run --agent <role> --auto` → handoff JSON (retries on miss)
   - `validate` (pub get, dart fix, format, analyze, test if present)
   - `commit --task-id` (scoped files; secret path/content guard)
   - `state done` (**blocked** without `commit_sha`)
3. Resume: run again; handoffs skip completed roles

Legacy freeform tech-lead session: `foreman run --agent-loop`  
TUI: `opencode --agent foreman` then `/ship` (agent policy; not the hard execute loop)

### Prove (no live LLM)

Deterministic control-plane check: mock roles write real Dart, design auto-approved, real git commits, optional real Flutter validate if Flutter is installed.

```bash
foreman prove                 # uses a temp directory (never this repo)
foreman prove /tmp/my_app     # explicit app dir
# → <app>/.foreman/PROVE_REPORT.md
```

`prove` refuses to use the Foreman source tree as the project.

---

## Commands (user)

| Command | What it actually does |
|---------|------------------------|
| `foreman doctor` | Env/install checks (python, opencode, agents, flutter optional) |
| `foreman init` | Seeds empty `tasks/prd.md` + `design.md`, pub get, optional git init |
| `foreman discover` | Interactive or `--goal` / `--features` → product docs |
| `foreman ready` | Product-doc gate JSON + exit code |
| `foreman design status\|show\|run\|approve\|reject` | Design language workflow |
| `foreman run` / `ship` | Gates then execute (or discover if not ready) |
| `foreman execute` | Same hard loop as run ship phase (`--mock`, `--task-id`, `--template`) |
| `foreman prove [dir]` | Deterministic ship proof (mock code, no live LLM) |
| `foreman status` / `next` | Brief + ready tasks + product/design gate + guidance |
| `foreman metrics` | Handoff / role_session proxies from `.foreman/metrics.jsonl` |
| `foreman report [--write]` | Field-report draft from local state (**not** live proof alone) |
| `foreman deploy list\|install` | `flutter devices` / install |
| `foreman demo` | Print mock terminal UX blocks |
| `foreman help` | User help; `foreman help --agent` for low-level tools |

### Agent / advanced (`foreman help --agent`)

Used by the executor and OpenCode agents:

- **State:** `state pending|ready|blocked|all|dag|add|done|fail|task|plan|guide|auto|batch|import|template|resume|…`
- **Roles:** `spawn <role> [task_id]`, `handoff <task_id> <role>`
- **Build:** `validate`, `verify`, `commit`, `rollback --task-id T`
- **Other:** `info`, `plan`, `log`, `debt`, `memory …`, `branch`, `pr`

Roles (OpenCode agents + spawn prompts):  
`product_owner` · `designer` · `architect` · `qa_lead` · `developer` · `tester` · `reviewer` · `refactorer` · `debugger`

Primary agent `foreman` has **`edit: deny`** — it must not write app code; implementers are subagents.

---

## Runtime layout (inside the Flutter app)

```text
my_app/
  tasks/
    prd.md                 # product
    design.md              # early design notes
    design_language.md     # after design approve (STRICT for implementers)
  .foreman/                # gitignore this
    tasks.json             # task DAG
    handoffs/<task>.<role>.json
    design_status.json
    design_preview.md
    memory/                # fact graph from handoffs (optional)
    log.jsonl
    metrics.jsonl
    PROVE_REPORT.md        # after foreman prove
    field_report_DRAFT.md  # after foreman report --write
  lib/ …
```

Templates for seeding DAGs (when used): `todo` · `chat` · `blog` under this repo’s `templates/`.

---

## Safety rails (as implemented)

| Rule | Implementation |
|------|----------------|
| Tech lead does not edit app code | OpenCode agent `foreman.md`: `edit: deny` |
| No ship without product docs | `ready` gate; `run` opens discovery if not ready |
| No implement without design language | `design approve` required; execute exits if pending (mock auto-approves only in mock/prove) |
| Design consistency | Language injected into architect/developer/reviewer prompts; hex check in `verify` / executor |
| Task done | `state done` fails without `commit_sha` (unless `--force`) |
| Commit | Task files or lib/test/tasks scope; refuses secret-like paths/content |
| Rollback | Default scoped: `rollback --task-id T` (not silent `git clean -fd`) |
| Handoff | Balanced JSON extract; retries in executor |
| Validate | Missing Flutter = env preflight, not debugger thrash |
| Verify | Advisory by default (`--gate` / `--strict` optional) |
| YAGNI | Prompt ladder for developer/reviewer/refactorer — not a compiler |

Escape hatches (recovery only): `--force`, `--skip-ready`, `run --agent-loop`.

---

## What is guaranteed vs not

**Guaranteed by the tool**

- Durable DAG + handoffs on disk  
- Product + design gates before implement (when not forced)  
- Execute loop structure and commit/done rules  
- Deterministic `prove` path (mock roles + real files/commits)

**Not guaranteed**

- Correct or beautiful UI without a capable model and human design approval  
- Valid handoff JSON on every OpenCode run (retries only)  
- Cost/latency (one OpenCode process per role is expensive)  
- Live-LLM ship success — CI proves plumbing via `prove` / mock, not production quality  

Details: [docs/KNOWN_LIMITS.md](docs/KNOWN_LIMITS.md).

---

## PATH (common failure)

OpenCode shells often omit `~/.local/bin`:

```bash
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
```

Agents are instructed to bootstrap PATH; still fix your shell profile if needed.

---

## Development / CI

```bash
python3 tests/test_tools.py    # unit + wrapper tests
python3 tests/test_prove.py    # deterministic ship proof
```

GitHub Actions runs both. `prove` is **not** a live OpenCode quality claim.

After a real human+model ship: `foreman report --write` and complete [docs/FIELD_REPORT.md](docs/FIELD_REPORT.md).

---

## License

See [LICENSE](LICENSE).
