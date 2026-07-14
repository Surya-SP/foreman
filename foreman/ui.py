"""Terminal presentation for humans. Machine JSON stays on stdout.

Pretty mode: stderr is TTY, and not FOREMAN_JSON=1 / --json / FOREMAN_PLAIN=1.
Agent tools: blocks on stderr; JSON on stdout (unchanged for parsers).
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

ROLE_BLURB = {
    "product_owner": "Break PRD into tasks",
    "architect": "Design approach before coding",
    "qa_lead": "Decide test strategy",
    "developer": "Write the code",
    "tester": "Write and run tests",
    "reviewer": "Review changes (no edits)",
    "refactorer": "Apply review fixes only",
    "debugger": "Fix validate failure",
}

_DIM = "\033[2m"
_BOLD = "\033[1m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_RST = "\033[0m"


def wants_json(argv: list[str] | None = None) -> bool:
    argv = argv if argv is not None else sys.argv
    if "--json" in argv:
        return True
    if os.environ.get("FOREMAN_JSON", "").strip().lower() in ("1", "true", "yes"):
        return True
    return False


def color_ok() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    return sys.stderr.isatty()


def is_pretty(argv: list[str] | None = None) -> bool:
    if wants_json(argv):
        return False
    if os.environ.get("FOREMAN_PLAIN", "").strip().lower() in ("1", "true", "yes"):
        return False
    return sys.stderr.isatty()


def _c(code: str, text: str) -> str:
    if not (color_ok() and is_pretty()):
        return text
    return f"{code}{text}{_RST}"


def dim(text: str) -> str:
    return _c(_DIM, text)


def bold(text: str) -> str:
    return _c(_BOLD, text)


def ok_mark() -> str:
    return _c(_GREEN, "✓") if color_ok() and is_pretty() else "OK"


def fail_mark() -> str:
    return _c(_RED, "✗") if color_ok() and is_pretty() else "X"


def _width() -> int:
    try:
        return max(40, min(72, os.get_terminal_size(2).columns))
    except (OSError, ValueError):
        return 56


def _chars() -> tuple[str, str, str, str]:
    """tl, horizontal, bl, vertical."""
    if os.environ.get("FOREMAN_ASCII", "").strip().lower() in ("1", "true", "yes"):
        return "+", "-", "+", "|"
    if sys.stderr.isatty():
        return "┌", "─", "└", "│"
    return "+", "-", "+", "|"


def block(
    title: str,
    command: str | None = None,
    detail: str | None = None,
    footer: str | None = None,
    *,
    file=None,
) -> None:
    """Container: what (title), then command, optional detail/footer."""
    if not is_pretty():
        return
    file = file or sys.stderr
    tl, h, bl, v = _chars()
    bar = h * (_width() - 1)
    print(f"{dim(tl + bar)}", file=file)
    print(f"{dim(v)} {bold(title)}", file=file)
    if command:
        print(f"{dim(v)} {dim('$ ' + command)}", file=file)
    if detail:
        for line in str(detail).splitlines()[:8]:
            print(f"{dim(v)}  {line}", file=file)
    if footer:
        print(f"{dim(v)} {footer}", file=file)
    print(f"{dim(bl + bar)}", file=file)


def result_line(ok: bool, text: str, *, file=None) -> None:
    if not is_pretty():
        return
    file = file or sys.stderr
    mark = ok_mark() if ok else fail_mark()
    print(f"  {mark} {text}", file=file)


def plain_line(text: str, *, file=None) -> None:
    if not is_pretty():
        return
    print(text, file=file or sys.stderr)


def role_block(
    role: str,
    task_id: str = "",
    command: str | None = None,
    status: str | None = None,
    *,
    file=None,
) -> None:
    blurb = ROLE_BLURB.get(role, role)
    head = f"{role}" + (f" · {task_id}" if task_id else "")
    block(f"{head} — {blurb}", command=command, footer=status, file=file)


def emit_json(obj: Any) -> None:
    json.dump(obj, sys.stdout, indent=2)
    print(file=sys.stdout)


def status_view(data: dict) -> None:
    if not is_pretty():
        return
    brief = data.get("brief") or "?"
    total = data.get("total_tasks", 0)
    ready = data.get("ready") or {}
    n_ready = ready.get("count", 0) if isinstance(ready, dict) else 0
    tasks = (ready.get("tasks") or []) if isinstance(ready, dict) else []
    guide = data.get("guidance") or ""
    how = data.get("how_to_run") or "foreman run"

    block("Project status", command="foreman status", detail=str(brief))
    result_line(True, f"{total} tasks total · {n_ready} ready")
    for t in tasks[:5]:
        if isinstance(t, dict):
            tid = t.get("id", "?")
            desc = t.get("desc") or t.get("description") or ""
            plain_line(f"    → {tid}" + (f"  {desc[:50]}" if desc else ""))
        else:
            plain_line(f"    → {t}")
    if guide:
        plain_line(dim(f"  {guide}"))
    plain_line(dim(f"  next: {how}"))
    print(file=sys.stderr)


def doctor_view(data: dict) -> None:
    if not is_pretty():
        return
    block("Check install", command="foreman doctor")
    for c in data.get("checks") or []:
        name = c.get("check", "?")
        ok = c.get("ok", False)
        detail = c.get("detail") or ""
        mark = ok_mark() if ok else fail_mark()
        extra = ""
        if detail and (not ok or len(str(detail)) < 48):
            extra = f"  {dim(str(detail))}"
        print(f"  {mark} {name}{extra}", file=sys.stderr)
    crit = data.get("critical_failures", 0)
    result_line(bool(data.get("ok")), f"{'ready' if data.get('ok') else 'fix issues'} · {crit} critical")
    for n in data.get("next") or []:
        plain_line(dim(f"  → {n}"))
    print(file=sys.stderr)


def init_view(data: dict) -> None:
    if not is_pretty():
        return
    block("Create project docs", command="foreman init")
    for m in data.get("messages") or []:
        plain_line(f"  · {m}")
    result_line(bool(data.get("ok", True)), "edit tasks/prd.md + design.md, then foreman run")
    print(file=sys.stderr)


def run_banner(project: str, model: str | None, auto: bool) -> None:
    if not is_pretty():
        return
    block(
        "Start autonomous build",
        command="foreman run",
        detail=f"project: {project}\nmodel: {model or 'default'} · auto-approve: {auto}",
        footer="OpenCode takes over — resume anytime with: foreman run",
    )
    print(file=sys.stderr)


def deploy_list_view(data: dict) -> None:
    if not is_pretty():
        return
    block("Devices", command="foreman deploy list")
    devices = data.get("devices") or []
    if not devices:
        plain_line(dim("  (none found — start a simulator or plug in a phone)"))
    else:
        for d in devices[:20]:
            if isinstance(d, dict):
                plain_line(
                    f"  · {d.get('id') or d.get('name')}  "
                    f"{dim(str(d.get('platform') or ''))}"
                )
            else:
                plain_line(f"  · {d}")
    result_line(True, f"{len(devices)} device(s)")
    if data.get("hint"):
        plain_line(dim(f"  {data['hint']}"))
    print(file=sys.stderr)


def spawn_view(role: str, task_id: str, ok: bool, tokens: int | None = None) -> None:
    if not is_pretty():
        return
    cmd = f"foreman spawn {role}" + (f" {task_id}" if task_id else "")
    status = None
    if ok:
        status = "prompt ready" + (f" · ~{tokens} tokens" if tokens else "")
    else:
        status = "failed"
    role_block(role, task_id, command=cmd, status=status)


def handoff_view(role: str, task_id: str, ok: bool, path: str = "") -> None:
    if not is_pretty():
        return
    cmd = f"foreman handoff {task_id} {role}"
    if ok:
        status = f"saved · {path}" if path else "saved"
    else:
        status = "failed"
    role_block(role, task_id, command=cmd, status=status)


def validate_view(ok: bool, summary: str = "") -> None:
    if not is_pretty():
        return
    block("Validate app", command="foreman validate")
    result_line(ok, summary or ("pass" if ok else "fail"))
    print(file=sys.stderr)


def state_plan_view(data: dict) -> None:
    if not is_pretty():
        return
    tid = data.get("task") or "?"
    profile = data.get("profile") or "?"
    roles = data.get("remaining_roles") or data.get("roles") or []
    chain = " → ".join(roles) if roles else "(none remaining)"
    block(
        f"Plan task {tid}",
        command=f"foreman state plan {tid}",
        detail=f"profile: {profile}\nroles: {chain}",
    )
    print(file=sys.stderr)


def demo_mock() -> str:
    """Static mock of the pretty UX (no TTY required)."""
    return """\
┌───────────────────────────────────────────────────────
│ Project status
│ $ foreman status
│  flutter · 12 files · main
└───────────────────────────────────────────────────────
  ✓ 4 tasks total · 1 ready
    → t2  Login screen
  Next ready: t2. Run: foreman run
  next: foreman run

┌───────────────────────────────────────────────────────
│ Check install
│ $ foreman doctor
└───────────────────────────────────────────────────────
  ✓ FOREMAN_HOME
  ✓ python3
  ✓ opencode
  ✓ foreman agent (project or global)
  ✓ flutter
  ✓ ripgrep (rg)
  ✓ ready · 0 critical
  → Next: foreman init  →  edit tasks  →  foreman run

┌───────────────────────────────────────────────────────
│ Create project docs
│ $ foreman init
└───────────────────────────────────────────────────────
  · wrote tasks/prd.md
  · wrote tasks/design.md
  ✓ edit tasks/prd.md + design.md, then foreman run

┌───────────────────────────────────────────────────────
│ Start autonomous build
│ $ foreman run
│  project: /Users/you/my_app
│  model: default · auto-approve: True
│ OpenCode takes over — resume anytime with: foreman run
└───────────────────────────────────────────────────────

┌───────────────────────────────────────────────────────
│ architect · t2 — Design approach before coding
│ $ foreman spawn architect t2 --self-handoff
│ prompt ready · ~980 tokens
└───────────────────────────────────────────────────────

┌───────────────────────────────────────────────────────
│ developer · t2 — Write the code
│ $ foreman spawn developer t2 --load-from architect --self-handoff
│ prompt ready · ~1.4k tokens
└───────────────────────────────────────────────────────

┌───────────────────────────────────────────────────────
│ Validate app
│ $ foreman validate
└───────────────────────────────────────────────────────
  ✓ analyze + test pass

┌───────────────────────────────────────────────────────
│ reviewer · t2 — Review changes (no edits)
│ $ foreman spawn reviewer t2
│ prompt ready
└───────────────────────────────────────────────────────

┌───────────────────────────────────────────────────────
│ reviewer · t2 — Review changes (no edits)
│ $ foreman handoff t2 reviewer
│ saved · .foreman/handoffs/t2.reviewer.json
└───────────────────────────────────────────────────────
  ✓ verdict APPROVED · commit + done
"""
