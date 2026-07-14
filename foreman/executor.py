"""Hard autonomous executor: advances remaining_roles via OpenCode role agents.

Still runs inside OpenCode (`opencode run --agent <role>`). Python owns the loop:
state plan → spawn → opencode role session → handoff check → validate/commit/done.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from typing import Any

from foreman.readiness import assess

ROLE_AGENTS = {
    "product_owner", "architect", "qa_lead", "developer", "tester",
    "reviewer", "refactorer", "debugger",
}

MAX_TASKS_DEFAULT = 50
MAX_DEBUG_ATTEMPTS = 3
OPENCODE_TIMEOUT = 1800  # seconds per role session


def _run_json(home: str, project: str, tool: str, *args: str, stdin: str | None = None) -> tuple[int, dict]:
    script = os.path.join(home, "foreman", "tools", tool)
    cmd = [os.environ.get("PYTHON", "python3"), script, "--project", project, *args]
    r = subprocess.run(
        cmd, capture_output=True, text=True, timeout=120,
        input=stdin, cwd=project,
        env={**os.environ, "FOREMAN_HOME": home, "FOREMAN_PROJECT": project, "FOREMAN_PLAIN": "1"},
    )
    out = (r.stdout or "").strip()
    try:
        # last JSON object if mixed
        data = json.loads(out) if out.startswith("{") else json.loads(out[out.find("{"):])
    except (json.JSONDecodeError, ValueError):
        data = {"ok": False, "raw": out[:500], "stderr": (r.stderr or "")[:300]}
    return r.returncode, data if isinstance(data, dict) else {"ok": False, "data": data}


def _handoff_exists(project: str, task_id: str, role: str) -> bool:
    p = os.path.join(project, ".foreman", "handoffs", f"{task_id}.{role}.json")
    return os.path.isfile(p)


def _read_handoff(project: str, task_id: str, role: str) -> dict:
    p = os.path.join(project, ".foreman", "handoffs", f"{task_id}.{role}.json")
    try:
        return json.load(open(p))
    except (OSError, json.JSONDecodeError):
        return {}


def _extract_json_from_text(text: str) -> dict | None:
    from foreman.jsonutil import extract_json_object
    obj, _ = extract_json_object(text or "")
    return obj


def _opencode_role(
    project: str,
    role: str,
    prompt: str,
    *,
    model: str | None = None,
    auto: bool = True,
    dry: bool = False,
) -> tuple[int, str]:
    """Run one OpenCode session as a role subagent. Returns (exit, combined_output)."""
    opencode = shutil.which("opencode")
    if not opencode:
        return 127, "opencode not found on PATH"
    # Instruct role agent: do work, print JSON, self-handoff if possible
    body = (
        prompt
        + "\n\n## Executor contract\n"
        "Complete this role. Output the required JSON. "
        "If the prompt includes a self-handoff bash block, run it. "
        "Otherwise print ONLY the JSON object as your final message.\n"
    )
    cmd = [
        opencode, "run",
        "--agent", role,
        "--dir", project,
        "--title", f"foreman-{role}",
    ]
    if auto:
        cmd.append("--auto")
    if model:
        cmd.extend(["--model", model])
    cmd.append(body)
    if dry:
        return 0, "DRY:" + " ".join(cmd[:8])
    try:
        r = subprocess.run(
            cmd, cwd=project, capture_output=True, text=True,
            timeout=OPENCODE_TIMEOUT,
            env={**os.environ, "FOREMAN_PROJECT": project},
        )
        combined = (r.stdout or "") + "\n" + (r.stderr or "")
        return r.returncode, combined
    except subprocess.TimeoutExpired:
        return 124, "opencode role session timed out"
    except OSError as e:
        return 1, str(e)


def _persist_handoff(home: str, project: str, task_id: str, role: str, text: str) -> tuple[bool, dict]:
    if _handoff_exists(project, task_id, role):
        return True, {"ok": True, "already": True}
    obj = _extract_json_from_text(text)
    if not obj:
        return False, {"ok": False, "message": "no JSON in opencode output"}
    raw = json.dumps(obj)
    rc, data = _run_json(home, project, "handoff.py", "--task-id", task_id, "--role", role, "--stdin", stdin=raw)
    return rc == 0 and data.get("ok", True), data


def _spawn_prompt(home: str, project: str, role: str, task_id: str, **flags: str) -> tuple[bool, str, dict]:
    args = ["--role", role, "--task-id", task_id]
    if role != "reviewer":
        args.append("--self-handoff")
    if role == "developer":
        args.extend(["--load-from", "architect"])
    if role == "tester":
        # load qa_lead if present else skip
        if _handoff_exists(project, task_id, "qa_lead"):
            args.extend(["--load-from", "qa_lead"])
    if role == "refactorer" and _handoff_exists(project, task_id, "reviewer"):
        args.extend(["--load-from", "reviewer"])
    if role == "debugger" and flags.get("error"):
        args.extend(["--error", flags["error"]])
    rc, data = _run_json(home, project, "spawn.py", *args)
    if rc != 0 or not data.get("prompt"):
        return False, "", data
    return True, data["prompt"], data


def _plan(home: str, project: str, task_id: str) -> dict:
    _, data = _run_json(home, project, "state.py", "--plan", task_id)
    return data


def _ready_tasks(home: str, project: str) -> list[str]:
    _, data = _run_json(home, project, "state.py", "--ready")
    tasks = data.get("tasks") or []
    return [t["id"] for t in tasks if isinstance(t, dict) and t.get("id")]


def _seed_if_empty(home: str, project: str, template: str | None) -> dict:
    _, summary = _run_json(home, project, "state.py")
    if (summary.get("total") or 0) > 0:
        return {"ok": True, "seeded": False}
    tpl = template or "todo"
    rc, data = _run_json(home, project, "state.py", "--template", tpl)
    return {"ok": rc == 0, "seeded": True, "template": tpl, "result": data}


def execute_task(
    home: str,
    project: str,
    task_id: str,
    *,
    model: str | None = None,
    auto: bool = True,
    dry: bool = False,
    mock: bool = False,
) -> dict[str, Any]:
    """Execute one task fully via OpenCode role agents (or mock handoffs)."""
    log: list[dict] = []
    plan = _plan(home, project, task_id)
    roles = list(plan.get("remaining_roles") or plan.get("roles") or [])
    needs_validate = plan.get("needs_validate", True)
    needs_reviewer = plan.get("needs_reviewer", True)
    profile = plan.get("profile") or "full"

    def step(msg: str, **extra: Any) -> None:
        log.append({"msg": msg, **extra})

    step("plan", profile=profile, roles=roles)

    for role in roles:
        if role not in ROLE_AGENTS:
            step("skip_unknown_role", role=role)
            continue
        if _handoff_exists(project, task_id, role):
            step("skip_handoff_exists", role=role)
            continue
        ok_s, prompt, spawn_data = _spawn_prompt(home, project, role, task_id)
        if not ok_s:
            return {"ok": False, "task_id": task_id, "error": "spawn_failed", "spawn": spawn_data, "log": log}
        step("spawn", role=role)
        if mock:
            # Golden e2e: write minimal valid handoff without LLM
            from foreman.schemas import ROLE_SCHEMAS
            obj: dict[str, Any] = {"role": role, "task_id": task_id}
            for k in ROLE_SCHEMAS.get(role, []):
                if k == "role":
                    continue
                if k == "tasks":
                    obj[k] = []
                elif k == "files":
                    obj[k] = [{"path": "lib/main.dart", "purpose": "app"}]
                elif k == "files_changed":
                    obj[k] = ["lib/main.dart"]
                elif k == "test_files":
                    obj[k] = []
                elif k == "all_pass":
                    obj[k] = True
                elif k == "findings":
                    obj[k] = []
                elif k == "verdict":
                    obj[k] = "APPROVED"
                elif k == "fixes_applied":
                    obj[k] = []
                elif k in ("root_cause", "fix", "approach", "test_strategy"):
                    obj[k] = f"mock-{role}"
                else:
                    obj[k] = f"mock-{k}"
            raw = json.dumps(obj)
            rc, hdata = _run_json(home, project, "handoff.py", "--task-id", task_id, "--role", role, "--stdin", stdin=raw)
            if rc != 0:
                return {"ok": False, "task_id": task_id, "error": "mock_handoff", "handoff": hdata, "log": log}
            step("mock_handoff", role=role)
            continue

        code, out = _opencode_role(project, role, prompt, model=model, auto=auto, dry=dry)
        step("opencode", role=role, exit=code)
        if dry:
            continue
        ok_h, hdata = _persist_handoff(home, project, task_id, role, out)
        if not ok_h and not _handoff_exists(project, task_id, role):
            return {
                "ok": False, "task_id": task_id, "error": "handoff_missing",
                "role": role, "handoff": hdata, "opencode_exit": code, "log": log,
            }
        step("handoff_ok", role=role)

    if dry:
        return {"ok": True, "task_id": task_id, "dry_run": True, "log": log}

    if needs_validate and profile not in ("design", "scope"):
        if mock:
            step("validate", ok=True, mock=True)
            vdata = {"ok": True}
        else:
            rc, vdata = _run_json(home, project, "validate.py", "--lines", "50")
            step("validate", ok=vdata.get("ok"), exit=rc)
            attempts = 0
            while not vdata.get("ok") and attempts < MAX_DEBUG_ATTEMPTS:
                attempts += 1
                err = json.dumps(vdata)[:2000]
                ok_s, prompt, _ = _spawn_prompt(home, project, "debugger", task_id, error=err)
                if not ok_s:
                    break
                code, out = _opencode_role(project, "debugger", prompt, model=model, auto=auto)
                _persist_handoff(home, project, task_id, "debugger", out)
                rc, vdata = _run_json(home, project, "validate.py", "--lines", "50")
                step("revalidate", attempt=attempts, ok=vdata.get("ok"))
            if not vdata.get("ok"):
                _run_json(home, project, "rollback.py", "--task-id", task_id)
                _run_json(
                    home, project, "state.py", "--mark", task_id,
                    "--status", "failed", "--error", "validate failed",
                )
                return {"ok": False, "task_id": task_id, "error": "validate_failed", "log": log}

    if needs_reviewer and profile not in ("design", "scope"):
        if not _handoff_exists(project, task_id, "reviewer"):
            ok_s, prompt, _ = _spawn_prompt(home, project, "reviewer", task_id)
            if ok_s:
                if mock:
                    raw = json.dumps({"role": "reviewer", "findings": [], "verdict": "APPROVED"})
                    _run_json(home, project, "handoff.py", "--task-id", task_id, "--role", "reviewer", "--stdin", stdin=raw)
                else:
                    code, out = _opencode_role(project, "reviewer", prompt, model=model, auto=auto)
                    _persist_handoff(home, project, task_id, "reviewer", out)
        rev = _read_handoff(project, task_id, "reviewer")
        verdict = rev.get("verdict", "APPROVED" if mock else "")
        step("review", verdict=verdict)
        if verdict == "CHANGES_REQUIRED":
            ok_s, prompt, _ = _spawn_prompt(home, project, "refactorer", task_id)
            if ok_s and not mock:
                code, out = _opencode_role(project, "refactorer", prompt, model=model, auto=auto)
                _persist_handoff(home, project, task_id, "refactorer", out)
            elif mock:
                raw = json.dumps({"role": "refactorer", "fixes_applied": ["mock"]})
                _run_json(home, project, "handoff.py", "--task-id", task_id, "--role", "refactorer", "--stdin", stdin=raw)
        elif verdict == "REJECT":
            _run_json(home, project, "state.py", "--mark", task_id, "--status", "failed", "--error", "reviewer REJECT")
            return {"ok": False, "task_id": task_id, "error": "rejected", "log": log}

    # commit + done
    desc = (plan.get("task_desc") or task_id)[:72]
    rc, cdata = _run_json(home, project, "commit.py", "--task-id", task_id, "--desc", desc)
    step("commit", ok=cdata.get("ok"), data=cdata)
    if not cdata.get("ok"):
        # allow force done only in mock with empty tree
        if mock:
            # inject fake sha for mock e2e
            sp = os.path.join(project, ".foreman", "tasks.json")
            try:
                st = json.load(open(sp))
                if task_id in st:
                    st[task_id]["commit_sha"] = "mockdeadbeef"
                    json.dump(st, open(sp, "w"), indent=2)
            except (OSError, json.JSONDecodeError):
                pass
        else:
            return {"ok": False, "task_id": task_id, "error": "commit_failed", "commit": cdata, "log": log}

    rc, ddata = _run_json(home, project, "state.py", "--mark", task_id, "--status", "done")
    if rc != 0 and mock:
        rc, ddata = _run_json(home, project, "state.py", "--mark", task_id, "--status", "done", "--force")
    step("done", ok=rc == 0, data=ddata)
    return {"ok": rc == 0, "task_id": task_id, "log": log, "done": ddata}


def execute_project(
    home: str,
    project: str,
    *,
    model: str | None = None,
    template: str | None = None,
    max_tasks: int = MAX_TASKS_DEFAULT,
    auto: bool = True,
    dry: bool = False,
    mock: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Run full autonomous ship: ready gate → seed → each ready task via OpenCode roles."""
    project = os.path.abspath(project)
    home = os.path.abspath(home)
    ready = assess(project)
    if not ready.get("ready") and not force:
        return {
            "ok": False,
            "phase": "discover",
            "message": "Product docs not ready",
            "ready": ready,
            "hint": "foreman discover && foreman ready && foreman run",
        }
    if not shutil.which("opencode") and not mock and not dry:
        return {"ok": False, "message": "opencode not found on PATH", "hint": "https://opencode.ai"}

    seed = _seed_if_empty(home, project, template)
    results = []
    n = 0
    while n < max_tasks:
        ids = _ready_tasks(home, project)
        if not ids:
            break
        tid = ids[0]
        n += 1
        r = execute_task(home, project, tid, model=model, auto=auto, dry=dry, mock=mock)
        results.append(r)
        if dry:
            break
        if not r.get("ok") and not mock:
            return {
                "ok": False,
                "phase": "ship",
                "seed": seed,
                "completed": results,
                "failed": tid,
                "message": r.get("error") or "task failed",
            }
        if mock and not r.get("ok"):
            # still stop on hard mock failure
            return {"ok": False, "phase": "ship", "seed": seed, "completed": results, "failed": tid}

    return {
        "ok": True,
        "phase": "ship",
        "seed": seed,
        "tasks_run": n,
        "results": results,
        "message": "DAG empty or max tasks reached" if n else "no ready tasks",
    }
