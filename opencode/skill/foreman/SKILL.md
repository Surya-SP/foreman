---
name: foreman
description: Use when shipping a Flutter app from tasks/prd.md and tasks/design.md with the Foreman task DAG, or when the user says foreman, ship the app, or run the multi-agent build pipeline.
---

# Foreman skill (Tech Lead reference)

You are **orchestrator only** (`edit` denied on primary). Prefer **foreman** agent (Tab, `/ship`).

**Phases:** `foreman ready` first. If not ready → discover (questions + `foreman discover`). If ready → ship via spawn/Task only.

Use the `foreman` CLI — never raw python tool paths.

**PATH:** OpenCode bash often lacks `~/.local/bin`. First command every session:
```bash
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
```

## One-line model

```
classify user intent → (chat- task if freeform) → state plan → spawn ONLY needed roles → Task → handoff → done
seed main DAG → for each ready task → state plan T → execute remaining_roles (never full pipeline by default)
```

`foreman state plan <id>` / `auto <id>` **print** the smart plan; they do **not** execute. You execute **by delegating only listed roles**.

## Hard rule: do not implement

Tech Lead / this skill must **not** edit `lib/`, `test/`, or app source. Bugs, features, refactors → `foreman state add chat-<slug> "…"` (no deps on main tasks) → `foreman spawn <role>` → **Task** tool with that subagent.

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

## One task (smart)

```bash
foreman state resume                 # → task id T
foreman state plan T                 # profile + remaining_roles — DO THIS FIRST
# spawn ONLY roles in remaining_roles (not always architect→qa→dev→tester)
# e.g. bugfix → debugger only; implement → architect+developer[+tester]
foreman validate --lines 200         # if needs_validate
# PASS + needs_reviewer → verify → reviewer → commit + done
# FAIL → debugger ≤3
```

## Freeform chat (user pastes bug / asks for work)

```
foreman next && foreman state all
foreman state add chat-<slug> "<goal>" --acceptance "..."
# route: bug→debugger | feature→architect (full) | tests→qa_lead/tester | review→reviewer | cleanup→refactorer
foreman spawn debugger chat-<slug> --error "<paste>" --self-handoff   # example
# Task agent=<role> with spawn.prompt → track handoffs → validate → commit → state done
```

Chat tasks must use id prefix `chat-` and **must not** depend on (or block) main ship tasks.

## Memory (facts only)

```
foreman memory stats
foreman memory retrieve --role developer --task-id T
foreman memory decisions --task-id T
foreman memory rg SymbolName --glob "*.dart"
foreman memory rebuild          # from handoffs if graph missing
foreman memory cache-clear
```

Handoffs auto-write decisions into `.foreman/memory/`. Spawn injects a capped fact block. No invented memory.

## Safety

- `state done` blocks on tester all_pass=false, REJECT, CHANGES_REQUIRED
- handoff refuses invalid schema (fix or --force with audit)
- `foreman log --task T` for debugging
- Never self-implement; always spawn + Task

## YAGNI ladder

Need? → reuse? → SDK? → native? → pubspec? → one line? → minimum.

Never cut: validation on trust boundaries, data-loss errors, security, a11y.
