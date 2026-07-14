"""Generate a field-report draft from local project state (not a live-ship proof)."""
from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from typing import Any

from foreman.design_gate import assess_design
from foreman.log import metrics_summary
from foreman.readiness import assess as assess_ready


def _git(project: str, *args: str) -> str:
    try:
        r = subprocess.run(
            ["git", *args], cwd=project, capture_output=True, text=True, timeout=10
        )
        return (r.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _foreman_commit(home: str) -> str:
    return _git(home, "rev-parse", "--short", "HEAD") or "unknown"


def _which_version(cmd: str) -> str:
    try:
        r = subprocess.run([cmd, "--version"], capture_output=True, text=True, timeout=15)
        line = (r.stdout or r.stderr or "").splitlines()
        return line[0][:120] if line else "unknown"
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return "not found"


def _state_summary(project: str) -> dict[str, Any]:
    p = os.path.join(project, ".foreman", "tasks.json")
    if not os.path.exists(p):
        return {"total": 0, "done": 0, "failed": 0, "pending": 0}
    try:
        st = json.load(open(p))
    except (json.JSONDecodeError, OSError):
        return {"total": 0, "done": 0, "failed": 0, "pending": 0}
    done = sum(1 for t in st.values() if t.get("status") == "done")
    failed = sum(1 for t in st.values() if t.get("status") == "failed")
    pending = sum(1 for t in st.values() if t.get("status") == "pending")
    return {"total": len(st), "done": done, "failed": failed, "pending": pending}


def _session_counts(project: str) -> dict[str, int]:
    path = os.path.join(project, ".foreman", "metrics.jsonl")
    roles: dict[str, int] = {}
    sessions = 0
    if not os.path.exists(path):
        return {"opencode_role_sessions": 0, "by_role": {}}
    try:
        for line in open(path):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("kind") in ("handoff_ok", "handoff_self", "role_session"):
                sessions += 1
                role = r.get("role") or "?"
                roles[role] = roles.get(role, 0) + 1
    except OSError:
        pass
    return {"opencode_role_sessions": sessions, "by_role": roles}


def build_report(project: str, home: str, *, live: bool = False) -> dict[str, Any]:
    project = os.path.abspath(project)
    home = os.path.abspath(home)
    ready = assess_ready(project)
    design = assess_design(project)
    metrics = metrics_summary(os.path.join(project, ".foreman"))
    state = _state_summary(project)
    sessions = _session_counts(project)
    prd = os.path.join(project, "tasks", "prd.md")
    goal = ""
    if os.path.exists(prd):
        try:
            for line in open(prd, encoding="utf-8", errors="ignore"):
                if line.strip() and not line.startswith("#"):
                    goal = line.strip()[:120]
                    break
        except OSError:
            pass
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "live_ship": bool(live),
        "warning": (
            None if live else
            "AUTO-DRAFT from local state — NOT a completed live-ship proof. "
            "Fill human sections after a real foreman run with a capable model."
        ),
        "environment": {
            "foreman_commit": _foreman_commit(home),
            "opencode": _which_version("opencode"),
            "flutter": _which_version("flutter"),
            "project": project,
            "git_head": _git(project, "rev-parse", "--short", "HEAD") or "n/a",
        },
        "gates": {
            "product_ready": ready.get("ready"),
            "design_approved": design.get("approved"),
            "design_status": design.get("status"),
        },
        "app": {
            "goal_guess": goal,
            "design_language": design.get("language_path") if design.get("has_language_doc") else None,
        },
        "state": state,
        "metrics": metrics,
        "sessions": sessions,
        "next": _next_actions(ready, design, state),
    }


def _next_actions(ready: dict, design: dict, state: dict) -> list[str]:
    if not ready.get("ready"):
        return ["foreman discover", "foreman ready"]
    if not design.get("approved"):
        return ["foreman design show", "foreman design approve", "foreman run"]
    if state.get("pending", 0) > 0 or state.get("total", 0) == 0:
        return ["foreman run"]
    return ["Fill human verdict in field report", "Optional: foreman deploy list"]


def render_markdown(data: dict[str, Any]) -> str:
    env = data.get("environment") or {}
    gates = data.get("gates") or {}
    st = data.get("state") or {}
    met = data.get("metrics") or {}
    ses = data.get("sessions") or {}
    app = data.get("app") or {}
    warn = data.get("warning") or ""
    lines = [
        "# Field report (auto-draft)",
        "",
        f"_Generated: {data.get('generated_at')}_",
        f"_Live ship claimed: **{data.get('live_ship')}**_",
        "",
    ]
    if warn:
        lines += [f"> **{warn}**", ""]
    lines += [
        "## Environment",
        "",
        f"| Item | Value |",
        f"|------|--------|",
        f"| Foreman commit | {env.get('foreman_commit')} |",
        f"| OpenCode | {env.get('opencode')} |",
        f"| Flutter | {env.get('flutter')} |",
        f"| Project | {env.get('project')} |",
        f"| Project git | {env.get('git_head')} |",
        "",
        "## Gates",
        "",
        f"- Product ready: **{gates.get('product_ready')}**",
        f"- Design approved: **{gates.get('design_approved')}** (`{gates.get('design_status')}`)",
        "",
        "## App",
        "",
        f"- Goal (from prd first line): {app.get('goal_guess') or '—'}",
        f"- Design language: {app.get('design_language') or '—'}",
        "",
        "## Task state",
        "",
        f"| total | done | failed | pending |",
        f"|-------|------|--------|---------|",
        f"| {st.get('total')} | {st.get('done')} | {st.get('failed')} | {st.get('pending')} |",
        "",
        "## Handoff metrics",
        "",
        f"- handoff_success_rate: **{met.get('handoff_success_rate')}**",
        f"- handoff_ok: {met.get('handoff_ok')} · handoff_miss: {met.get('handoff_miss')}",
        f"- by_kind: `{json.dumps(met.get('by_kind') or {})}`",
        "",
        "## Role session proxies (from metrics)",
        "",
        f"- counted events: {ses.get('opencode_role_sessions')}",
        f"- by_role: `{json.dumps(ses.get('by_role') or {})}`",
        "",
        "## Human sections (fill after live ship)",
        "",
        "### Timeline",
        "",
        "| Phase | Duration | Notes |",
        "|-------|----------|-------|",
        "| discover | | |",
        "| design approve | | |",
        "| execute | | |",
        "| total | | |",
        "",
        "### Outcomes",
        "",
        "- [ ] flutter analyze clean",
        "- [ ] flutter test pass",
        "- [ ] app launches",
        "- [ ] UI matches design language (visual)",
        "",
        "### Interventions",
        "",
        "| Step | Issue | Action | Recovered? |",
        "|------|-------|--------|------------|",
        "| | | | |",
        "",
        "### Verdict",
        "",
        "Would run again? **Yes / No / With changes:**",
        "",
        "## Next",
        "",
    ]
    for n in data.get("next") or []:
        lines.append(f"- `{n}`")
    lines.append("")
    return "\n".join(lines)
