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

from foreman.readiness import assess

force_ship = "--force" in sys.argv or "--skip-ready" in sys.argv
ready_report = assess(target)

# Optional: seed template only when product-ready (or forced)
if template:
    if not ready_report.get("ready") and not force_ship:
        _out({
            "ok": False,
            "phase": "discover",
            "message": "Cannot seed template until product docs are ready",
            "ready": ready_report,
            "hint": "foreman discover   then   foreman ready   then   foreman run --template todo",
        }, 1)
    state_py = os.path.join(_ROOT, "foreman", "tools", "state.py")
    r = subprocess.run(
        [sys.executable, state_py, "--project", target, "--template", template],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode != 0:
        _out({"ok": False, "message": f"template seed failed: {r.stdout or r.stderr}"}, 1)

# Gate: interactive discovery before autonomous ship
if not ready_report.get("ready") and not force_ship:
    # Launch agent in DISCOVER mode (interactive questions), not full ship
    discover_msg = (
        "Foreman DISCOVERY mode (interactive). Do NOT write app code. "
        "export PATH=\"$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH\". "
        "Run foreman doctor, then foreman ready. "
        "Product PRD/design are incomplete. Use the question tool to brainstorm with the user "
        "(goal, users, features≥2, screens, colors, platforms, non-goals). "
        "Then run: foreman discover --goal \"...\" --features \"A;B\" --screens \"Home\" --primary \"#2196F3\" "
        "(or ask user to run foreman discover interactively). "
        "Re-run foreman ready until ready=true. Then tell the user to run: foreman run "
        "for autonomous build. Do not start the ship pipeline until ready."
    )
    if message:
        discover_msg = message + "\n\n" + discover_msg
    cmd = [opencode, "run", "--agent", "foreman", "--dir", target, "--title", "foreman-discover"]
    # discovery needs user interaction — do not force --auto unless user asked
    if model:
        cmd.extend(["--model", model])
    cmd.append(discover_msg)
    if dry:
        _out({
            "ok": True,
            "dry_run": True,
            "phase": "discover",
            "would_run": cmd,
            "ready": ready_report,
            "hint": "Product not ready — would open discovery. After ready: foreman run",
        })
    from foreman import ui
    ui.block("Product discovery required", command="foreman run",
             detail="PRD/design incomplete — starting interactive discovery",
             footer="After ready: re-run foreman run to ship")
    try:
        proc = subprocess.run(cmd, cwd=target)
        code = proc.returncode
    except KeyboardInterrupt:
        code = 130
    except OSError as e:
        _out({"ok": False, "message": f"failed to launch opencode: {e}"}, 1)
    _out({
        "ok": code == 0,
        "phase": "discover",
        "exit": code,
        "ready": assess(target),
        "hint": "When foreman ready passes, run: foreman run",
    }, 0 if code == 0 else code)

# Ship phase: hard executor drives OpenCode **role** agents (fully autonomous).
# Prefer executor loop over freeform tech-lead chat for deterministic progress.
use_legacy_agent = "--agent-loop" in sys.argv  # opt into old freeform tech-lead only

if dry and not use_legacy_agent:
    from foreman.executor import execute_project
    result = execute_project(
        _ROOT, target, model=model, template=None, dry=True, force=force_ship,
    )
    _out({
        "ok": True,
        "dry_run": True,
        "phase": "ship",
        "mode": "execute",
        "executor": result,
        "project": target,
        "ready": ready_report,
        "hint": "Remove --dry-run to run: foreman execute (OpenCode per role). Legacy: --agent-loop",
    })

if not use_legacy_agent:
    from foreman import ui
    from foreman.executor import execute_project
    ui.run_banner(target, model, not no_auto)
    if not ui.is_pretty():
        print(f"foreman run → execute (OpenCode role agents) --dir {target}", file=sys.stderr)
    sys.stderr.flush()
    # Re-read template already applied above; pass None
    result = execute_project(
        _ROOT, target,
        model=model,
        template=None,
        auto=not no_auto,
        dry=False,
        mock=False,
        force=force_ship,
    )
    _out({
        "ok": bool(result.get("ok")),
        "phase": "ship",
        "mode": "execute",
        "project": target,
        "result": result,
        "hint": "Resume: foreman run   |   single task: foreman execute --task-id T",
    }, 0 if result.get("ok") else 1)

# Legacy: freeform OpenCode tech-lead agent loop
default_msg = (
    "Ship this project with Foreman. Product docs are READY. Work autonomously until the task DAG is empty or blocked. "
    "export PATH=\"$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH\". "
    "Prefer: run `foreman execute` yourself via bash to drive the hard OpenCode role loop. "
    "Or manually: state plan → spawn → Task(subagent) → handoff → validate → commit → state done. "
    "You have edit:deny. Never --force. Rollback only: foreman rollback --task-id T."
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
        "phase": "ship",
        "mode": "agent-loop",
        "would_run": cmd,
        "project": target,
        "agent": "foreman",
        "ready": ready_report,
    })

from foreman import ui
ui.run_banner(target, model, not no_auto)
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
    "mode": "agent-loop",
    "project": target,
    "agent": "foreman",
    "hint": "Resume with: foreman run",
}, 0 if code == 0 else code)
