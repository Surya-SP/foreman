# Foreman

**OpenCode multi-agent pipeline for Flutter, with durable task state.**

Foreman does **not** call LLMs itself. It:

1. Helps you define a product (`discover` → `ready`)
2. Produces a **design language** for human review (`design`)
3. Runs a **Python control loop** that starts **OpenCode role agents**  
   (`opencode run --agent architect|developer|…`) until the task graph is done

Quality still depends on your **model**, **PRD**, and **OpenCode**. Weak models will stall; re-run `foreman run`.

```text
foreman discover → ready → design approve → run
```

App lives **outside** the Foreman repo (`flutter create` anywhere).

---

## What you need

| Tool | Why |
|------|-----|
| [Flutter](https://docs.flutter.dev/get-started) | App project |
| [OpenCode](https://opencode.ai) | Role agents |
| Python 3 | Foreman CLI |
| git | Commits / resume |

---

## Install once

```bash
git clone https://github.com/Surya-SP/foreman
cd foreman
./install.sh
export PATH="$HOME/.local/bin:$PATH"
```

Restart OpenCode after install.

---

## Build an app

```bash
flutter create my_app && cd my_app
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

foreman doctor
foreman discover          # product brainstorm → tasks/prd.md + design.md
foreman ready             # must pass
foreman design run        # OpenCode designer: mockups + draft language
foreman design show       # review wireframes
foreman design approve    # writes tasks/design_language.md (STRICT for other roles)
foreman run               # autonomous: OpenCode per role until DAG empty
```

**Resume:** `foreman run` again.  
**TUI:** `opencode --agent foreman` then `/ship`.  
**Default ship mode:** hard `execute` loop (not freeform chat). Legacy: `foreman run --agent-loop`.

After a real ship:

```bash
foreman report --write    # draft from state + metrics
# complete human sections → see docs/FIELD_REPORT.md
```

Limits: [docs/KNOWN_LIMITS.md](docs/KNOWN_LIMITS.md).

---

## Everyday commands

| Command | Purpose |
|---------|---------|
| `foreman discover` | PRD + design docs |
| `foreman ready` | Product-doc gate |
| `foreman design run\|show\|approve\|reject` | Design language + human gate |
| `foreman run` / `execute` | Autonomous OpenCode ship |
| `foreman status` | Progress |
| `foreman doctor` | Install / PATH |
| `foreman deploy list\|install` | Devices |
| `foreman metrics` | Handoff / role-session proxies |
| `foreman report --write` | Field-report draft (not live proof alone) |
| `foreman demo` | Terminal UX mock |
| `foreman help` | This guide |

Agent tools: `foreman help --agent`.

---

## Safety rails

| Rule | Behavior |
|------|----------|
| Primary tech lead | `edit: deny` — no app code |
| Product gate | `ready` before ship |
| Design gate | human `design approve` before implement (mock auto-approves in CI) |
| Design language | injected into architect/developer/reviewer; must follow |
| Done | requires `commit_sha` |
| Commit | scoped + secret-path/content guard |
| Rollback | `foreman rollback --task-id T` (scoped) |
| Handoff | balanced JSON + retries on miss |
| Validate | env missing Flutter ≠ app bug (no debugger thrash) |
| Verify | advisory by default |

---

## How ship works

```
ready ✓ + design language approved
        ↓
seed task DAG (if empty)
        ↓
for each ready task:
  state plan → remaining roles only
  for each role:
    spawn prompt → opencode run --agent <role>
    handoff JSON (retry if missing)
  validate → commit → state done
```

State: `.foreman/` (gitignore it). Design language: `tasks/design_language.md`.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ready` fails | `foreman discover` |
| design blocked / WAITING FOR approve | `foreman design show` then `approve` then `run` |
| `command not found: foreman` | fix PATH |
| build stopped | `foreman run` again |
| handoff missing | `foreman metrics`; reinstall agents; stronger model |
| colors ignore design language | `foreman verify --task-id T` (design_token findings) |

---

## License

See the repository.
