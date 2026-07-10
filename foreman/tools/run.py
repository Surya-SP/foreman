#!/usr/bin/env python3
"""Autonomous entrypoint: launch OpenCode with the foreman agent.

Usage:
  run.py --project . [--message "..."] [--model provider/model] [--dry-run]
  run.py --project . --template todo
  run.py --project . --until-done   (default behaviour of the prompt)

This does NOT call an LLM itself. It starts:
  opencode run --agent foreman --auto --dir <project> "<ship prompt>"

Requires: opencode on PATH, and the foreman agent installed globally
(~/.config/opencode/agent/foreman.md via ./install.sh) or per-project.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
sys.path.insert(0, _ROOT)

from foreman.log import log

_start = time.time()


def _arg(name, default=None):
    return next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == name), default)


def _out(obj, code=0):
    json.dump(obj, sys.stdout, indent=2)
    print()
    log(os.path.join(target, ".foreman"), "run.py", code, int((time.time() - _start) * 1000))
    sys.exit(code)


target = os.path.abspath(_arg("--project") or os.environ.get("FOREMAN_PROJECT") or ".")
message = _arg("--message")
model = _arg("--model")
template = _arg("--template")
dry = "--dry-run" in sys.argv
no_auto = "--no-auto" in sys.argv

# Ensure runtime dirs
os.makedirs(os.path.join(target, ".foreman", "handoffs"), exist_ok=True)

# Preflight
opencode = shutil.which("opencode")
if not opencode:
    _out({
        "ok": False,
        "message": "opencode not found on PATH",
        "hint": "Install OpenCode (https://opencode.ai), then re-run: foreman run",
    }, 1)

def _agent_installed() -> tuple[bool, str]:
    """Project-local or global OpenCode agent is enough."""
    candidates = [
        os.path.join(target, ".opencode", "agent", "foreman.md"),
        os.path.join(target, ".opencode", "agents", "foreman.md"),
        os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
                     "opencode", "agent", "foreman.md"),
        os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
                     "opencode", "agents", "foreman.md"),
    ]
    for p in candidates:
        if os.path.exists(p) or os.path.islink(p):
            return True, p
    return False, candidates[0]

ok_agent, agent_where = _agent_installed()
if not ok_agent:
    _out({
        "ok": False,
        "message": "Foreman OpenCode agent not found (project or global)",
        "hint": "From the foreman repo run once: ./install.sh   # global; no per-project install needed",
        "expected": agent_where,
    }, 1)

# Optional: seed template before launching agent
if template:
    state_py = os.path.join(_ROOT, "foreman", "tools", "state.py")
    r = subprocess.run(
        [sys.executable, state_py, "--project", target, "--template", template],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode != 0:
        _out({"ok": False, "message": f"template seed failed: {r.stdout or r.stderr}"}, 1)

# Default autonomous prompt
default_msg = (
    "Ship this project with Foreman. Work autonomously until the task DAG is empty or blocked. "
    "Run: foreman doctor, then foreman next. "
    "If no tasks, seed with foreman state template todo (or product_owner → state import from PRD). "
    "For each ready task run the full pipeline: architect → qa_lead → developer → tester → "
    "validate → reviewer → commit → state done. "
    "On validate fail: debugger ≤3 then rollback+fail. "
    "On CHANGES_REQUIRED: refactorer then re-validate. "
    "Do not wait for me between steps. Only stop for deploy choices, escalations, or missing PRD."
)
if message:
    default_msg = message + "\n\n" + default_msg

cmd = [opencode, "run", "--agent", "foreman", "--dir", target, "--title", "foreman-ship"]
if not no_auto:
    cmd.append("--auto")
if model:
    cmd.extend(["--model", model])
cmd.append(default_msg)

if dry:
    _out({
        "ok": True,
        "dry_run": True,
        "would_run": cmd,
        "project": target,
        "agent": "foreman",
        "hint": "Remove --dry-run to launch OpenCode. Or: opencode --agent foreman  then /ship",
    })

# Stream OpenCode to the terminal (user watches the autonomous agent)
print(f"foreman run → opencode --agent foreman --dir {target}", file=sys.stderr)
print(f"  auto-approve: {not no_auto}  model: {model or '(default)'}", file=sys.stderr)
print("─" * 60, file=sys.stderr)
sys.stderr.flush()

try:
    proc = subprocess.run(cmd, cwd=target)
    code = proc.returncode
except KeyboardInterrupt:
    code = 130
except OSError as e:
    _out({"ok": False, "message": f"failed to launch opencode: {e}"}, 1)

_out({
    "ok": code == 0,
    "exit": code,
    "project": target,
    "agent": "foreman",
    "hint": "Resume with: foreman run   or   foreman state resume",
}, 0 if code == 0 else code)
