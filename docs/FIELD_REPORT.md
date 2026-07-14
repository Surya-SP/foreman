# Field report template (live ship)

Use this after a **real** `discover → ready → design approve → run` (not `--mock`).

**Bootstrap a draft from local state:**

```bash
foreman report --write
# edit .foreman/field_report_DRAFT.md — fill human sections
```

Auto-draft alone is **not** live-ship proof.

## Environment

| Item | Value |
|------|--------|
| Date | |
| Foreman commit | |
| OpenCode version | |
| Model(s) | |
| OS | |
| Flutter version | |

## App

| Item | Value |
|------|--------|
| App goal (1 line) | |
| Feature count | |
| Repo path | |

## Timeline

| Phase | Duration | Notes |
|-------|----------|--------|
| discover | | |
| ready | | |
| design run + human approve | | |
| execute / run (roles) | | |
| total wall clock | | |

## Outcomes

- [ ] `flutter analyze` clean
- [ ] `flutter test` pass (if tests exist)
- [ ] App launches on device/simulator
- [ ] Design language followed (visual check)

## Failures / interventions

| Step | What broke | Human action | Recovered? |
|------|------------|--------------|------------|
| | | | |

## Cost / usage (if known)

| Item | Value |
|------|--------|
| Est. tokens / $ | |
| OpenCode sessions (roles) | |
| Retries (handoff/debugger) | |

## Verdict

Would you run this again for a real product? **Yes / No / With changes:**

## Attach

- `foreman log --summary` output
- Final `tasks/design_language.md` path
- Screenshot of UI (optional)
