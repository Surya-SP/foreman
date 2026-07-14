# Foreman

**Describe a polished product. Foreman builds the Flutter app.**

Two phases:

1. **Discover** (interactive) — brainstorm until PRD + design are solid  
2. **Ship** (autonomous) — agent team builds, tests, reviews, commits  

You do not need a huge CLI. Day to day:

```text
foreman discover  →  foreman ready  →  foreman run
```

---

## What you need

| Tool | Why |
|------|-----|
| [Flutter](https://docs.flutter.dev/get-started) | App project |
| [OpenCode](https://opencode.ai) | AI agents |
| Python 3 | Foreman tools |
| git | Commits / resume |

Use a **capable model** in OpenCode for shipping. Weak models may stop early — re-run `foreman run`.

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

### 1. Flutter project

```bash
flutter create my_app
cd my_app
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
foreman doctor
```

### 2. Discover (interactive product design)

```bash
foreman discover
```

Answer in plain language: goal, features, screens, colors.  
This writes `tasks/prd.md` and `tasks/design.md`.

Non-interactive:

```bash
foreman discover \
  --goal "Todo app for busy people" \
  --features "Add todo;Mark done;Delete" \
  --name Todos \
  --screens "HomeScreen" \
  --primary "#2196F3"
```

### 3. Gate — must pass before ship

```bash
foreman ready
```

If this fails, keep refining docs (or re-run `discover`).  
**Autonomous build will not start until ready passes.**

### 4. Ship (autonomous — still OpenCode)

```bash
foreman run
```

Same: `foreman ship` / `foreman execute`.

What happens after `ready` passes:

1. Seed task list if empty  
2. For each ready task: `state plan` → only needed roles  
3. Each role: **`opencode run --agent <role>`** (real OpenCode session)  
4. handoff → validate → commit → next task  

Python owns the loop; **every role still runs inside OpenCode**.  
If docs are incomplete, `foreman run` opens **discovery** first.

Resume:

```bash
foreman run
```

TUI alternative: `opencode --agent foreman` then `/ship`.

---

## Everyday commands

| Command | What it does |
|---------|----------------|
| `foreman discover` | Brainstorm → write PRD + design |
| `foreman ready` | Gate: are docs shippable? |
| `foreman run` | Discover if needed, else autonomous build |
| `foreman status` | Progress |
| `foreman doctor` | Install / PATH |
| `foreman init` | Empty templates only |
| `foreman deploy list` / `install` | Devices |
| `foreman demo` | Terminal UX preview |
| `foreman help` | This guide |

Agent internals: `foreman help --agent` (you usually ignore these).

---

## Safety (hard rules)

| Rule | Behavior |
|------|----------|
| Tech Lead cannot edit app code | OpenCode `edit: deny` on primary agent |
| Ship only when ready | `foreman ready` gate on `run` |
| Hard role loop | `foreman execute` / `run` drives OpenCode per role |
| Done requires commit | `state done` blocked without `commit_sha` |
| Scoped commit | Task files / `lib`+`test` — not blind `git add -A` |
| Scoped rollback | `foreman rollback --task-id T` only |
| Verify advisory | Design-drift heuristic does not block by default |
| Sub-agents implement | All code via OpenCode role agents |

---

## How it works

```
discover (you + agent questions)
        ↓
  prd.md + design.md  →  ready ✓
        ↓
  foreman run (OpenCode tech lead)
        ↓
  role sub-agents (architect, developer, tester, …)
        ↓
  validate → commit → next task
```

Progress lives in `.foreman/` (gitignore it).

```bash
echo ".foreman/" >> .gitignore
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ready` fails | `foreman discover` or flesh out `tasks/*.md` |
| `command not found: foreman` | Fix PATH (see above) |
| Build stopped | `foreman run` again |
| OpenCode missing agent | `./install.sh` + restart OpenCode |

---

## For the AI agent

Advanced tools remain for orchestration. See `foreman help --agent` and `opencode/agent/foreman.md`.

Repo: https://github.com/Surya-SP/foreman
