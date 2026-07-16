# Known limits

Honest operational constraints. Read before production use.

## What Foreman guarantees

- Durable task DAG + handoffs under `.foreman/`
- Product gate (`ready`) and design gate (`design approve`) before implement
- Python-driven loop of `opencode run --agent <role>` per planned role
- Safety rails: primary `edit: deny`, commit required for done, scoped rollback, secret heuristics

## What Foreman does **not** guarantee

- Correct or beautiful UI without a capable model + human design approval
- That role agents always emit valid JSON (retries help; not perfect)
- Cost or latency (one OpenCode process per role is expensive)
- Secret-free repos beyond path/content heuristics
- Live ship success — CI uses `--mock` (no real OpenCode / flutter validate)

## Cost / latency

| Factor | Impact |
|--------|--------|
| Roles per task | Smart plan reduces roles; complex tasks still run many |
| Cold `opencode run` per role | High wall-clock and $ |
| Handoff retries | Extra role sessions on miss |
| Designer | Extra session before ship |

Prefer strong models for ship; weak models thrash retries.

## Modes

| Mode | When |
|------|------|
| `foreman run` (default execute) | Autonomous after gates |
| `foreman run --agent-loop` | Freeform tech-lead TUI-style session |
| `opencode --agent foreman` + `/ship` | Interactive TUI |
| `foreman execute --mock` | Mock handoffs (prefer `foreman prove`) |
| `foreman prove [dir]` | Deterministic ship: mock roles **write real Dart**, design approve, commits, report. Optional real `flutter analyze` if Flutter installed. **Not** live-LLM quality. |

## Handoff failures

Check: `foreman metrics` → `handoff_success_rate`, `handoff_miss`.

Common causes: model prose without JSON, wrong role agent install, PATH missing `foreman` inside OpenCode.

## Design language

- Enforcement is **prompt STRICT + mechanical hex check** (verify / executor), not a full visual compiler.
- Humans must still review `foreman design show` before approve.

## Field proof

After a real ship:

```bash
foreman report --write          # auto-draft from .foreman state
# then complete human sections in .foreman/field_report_DRAFT.md
# or copy into FIELD_REPORT.md
```

Without a human-completed live report, reliability claims are unproven.

## Metrics

```bash
foreman metrics                 # handoff_success_rate, role_session counts
```

`role_session` events are cost/latency **proxies**, not provider dollars.

## Models

Per-role models come from **capabilities** in `models.json` (see README).

- Wrong or unavailable `provider/model` IDs → OpenCode role session fails.
- Run `opencode models` and edit `~/.config/foreman/models.json` aliases.
- `foreman run --model X` forces **all** roles to X for that run.
