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
    "product_owner", "designer", "architect", "qa_lead", "developer", "tester",
    "reviewer", "refactorer", "debugger",
}
HANDOFF_RETRIES = 2

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
    from foreman.log import metric
    opencode = shutil.which("opencode")
    if not opencode:
        return 127, "opencode not found on PATH"
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
        metric(_mem_dir(project), "role_session", role=role, dry=True, model=model or "")
        return 0, "DRY:" + " ".join(cmd[:8])
    t0 = time.time()
    try:
        r = subprocess.run(
            cmd, cwd=project, capture_output=True, text=True,
            timeout=OPENCODE_TIMEOUT,
            env={**os.environ, "FOREMAN_PROJECT": project},
        )
        combined = (r.stdout or "") + "\n" + (r.stderr or "")
        metric(
            _mem_dir(project), "role_session",
            role=role, exit=r.returncode, ms=int((time.time() - t0) * 1000),
            model=model or "", prompt_chars=len(prompt),
        )
        return r.returncode, combined
    except subprocess.TimeoutExpired:
        metric(_mem_dir(project), "role_session", role=role, exit=124, ms=OPENCODE_TIMEOUT * 1000, model=model or "")
        return 124, "opencode role session timed out"
    except OSError as e:
        metric(_mem_dir(project), "role_session", role=role, exit=1, error=str(e))
        return 1, str(e)


def _mem_dir(project: str) -> str:
    return os.path.join(os.path.abspath(project), ".foreman")


def _persist_handoff(home: str, project: str, task_id: str, role: str, text: str) -> tuple[bool, dict]:
    from foreman.log import metric
    if _handoff_exists(project, task_id, role):
        metric(_mem_dir(project), "handoff_self", role=role, task_id=task_id)
        return True, {"ok": True, "already": True}
    obj = _extract_json_from_text(text)
    if not obj:
        metric(_mem_dir(project), "handoff_miss", role=role, task_id=task_id, reason="no_json")
        return False, {"ok": False, "message": "no JSON in opencode output"}
    raw = json.dumps(obj)
    rc, data = _run_json(home, project, "handoff.py", "--task-id", task_id, "--role", role, "--stdin", stdin=raw)
    ok = rc == 0 and data.get("ok", True)
    metric(
        _mem_dir(project),
        "handoff_ok" if ok else "handoff_miss",
        role=role, task_id=task_id, reason="schema" if not ok else "parse",
    )
    return ok, data


def _run_role_with_retry(
    home: str,
    project: str,
    role: str,
    prompt: str,
    task_id: str,
    *,
    model: str | None,
    auto: bool,
    dry: bool,
) -> tuple[bool, dict, list[dict]]:
    """OpenCode role session + handoff; retry with JSON-only re-prompt."""
    from foreman.log import metric
    log: list[dict] = []
    for attempt in range(1, HANDOFF_RETRIES + 2):
        p = prompt
        if attempt > 1:
            p = (
                prompt
                + "\n\n## RETRY: previous output had no valid handoff JSON.\n"
                "Reply with ONLY one JSON object matching the role schema. No prose.\n"
            )
            metric(_mem_dir(project), "handoff_retry", role=role, task_id=task_id, attempt=attempt)
        code, out = _opencode_role(project, role, p, model=model, auto=auto, dry=dry)
        log.append({"attempt": attempt, "exit": code})
        if dry:
            return True, {"dry": True}, log
        if _handoff_exists(project, task_id, role):
            metric(_mem_dir(project), "handoff_self", role=role, task_id=task_id)
            return True, {"ok": True, "self_handoff": True}, log
        ok_h, hdata = _persist_handoff(home, project, task_id, role, out)
        if ok_h:
            return True, hdata, log
        log.append({"attempt": attempt, "handoff": hdata})
    metric(_mem_dir(project), "handoff_miss", role=role, task_id=task_id, reason="exhausted_retries")
    return False, {"ok": False, "message": "handoff missing after retries"}, log


def _spawn_prompt(home: str, project: str, role: str, task_id: str, **flags: str) -> tuple[bool, str, dict]:
    args = ["--role", role, "--task-id", task_id]
    if role not in ("reviewer",):
        args.append("--self-handoff")
    if role == "developer":
        args.extend(["--load-from", "architect"])
    if role == "tester":
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


def run_designer_phase(
    home: str,
    project: str,
    *,
    mock: bool = False,
    model: str | None = None,
    auto: bool = True,
) -> dict[str, Any]:
    """Run designer role; leaves status pending_review until human approve."""
    from foreman import design_gate as dg
    tid = "design"
    ok_s, prompt, spawn_data = _spawn_prompt(home, project, "designer", tid)
    if not ok_s:
        return {"ok": False, "error": "spawn_failed", "spawn": spawn_data}
    if mock:
        obj = {
            "role": "designer",
            "summary": "Calm utility system for CI mock",
            "personality": "calm utility",
            "platforms": ["ios", "android"],
            "mockups": [{
                "screen": "HomeScreen",
                "goal": "See items",
                "primary_cta": "Add",
                "wireframe": "AppBar\nList\nFAB",
                "notes": "single primary FAB",
            }],
            "design_language_md": (
                "# Design Language — CI\n\n## 1. Personality & principles\nCalm utility\n\n"
                "## 2. Color\n- Primary: #2196F3\n- On primary: #FFFFFF\n- Surface: #FFFBFE\n"
                "- On surface: #1C1B1F\n- Error: #B3261E\n\n"
                "## 3. Typography\nM3 type scale\n\n## 4. Space & layout\n8dp grid\n\n"
                "## 5. Shape & elevation\n12dp cards\n\n## 6. Components\nMaterial 3\n\n"
                "## 7. Navigation\nBottom bar if multi-section\n\n## 8. Motion\nShort fades\n\n"
                "## 9. Content & empty/loading/error\nRequired\n\n## 10. Accessibility\n48dp\n\n"
                "## 11. Do / Don't\nNo purple gradient slop\n\n## 12. Screen specs\nHomeScreen\n"
            ),
            "token_index": {
                "primary": "#2196F3",
                "on_primary": "#FFFFFF",
                "primary_container": "#BBDEFB",
                "surface": "#FFFBFE",
                "on_surface": "#1C1B1F",
                "error": "#B3261E",
                "outline": "#79747E",
            },
            "anti_slop_checklist": {
                "no_generic_purple_gradient": True,
                "single_primary_cta_per_screen": True,
                "semantic_color_roles": True,
                "contrast_aa_text": True,
                "empty_loading_error_defined": True,
                "min_touch_48": True,
            },
            "open_questions": [],
            "status": "pending_review",
        }
        raw = json.dumps(obj)
        rc, hdata = _run_json(home, project, "handoff.py", "--task-id", tid, "--role", "designer", "--stdin", stdin=raw)
        if rc != 0:
            return {"ok": False, "error": "mock_handoff", "handoff": hdata}
        a = dg.assess_design(project)
        return {
            **a,
            "ok": True,
            "status": a.get("status") or "pending_review",
            "message": "Designer draft ready — human: foreman design show && foreman design approve",
        }
    ok, hdata, log = _run_role_with_retry(home, project, "designer", prompt, tid, model=model, auto=auto, dry=False)
    if not ok:
        return {"ok": False, "error": "designer_handoff_failed", "handoff": hdata, "log": log}
    a = dg.assess_design(project)
    return {
        **a,
        "ok": True,
        "status": a.get("status") or "pending_review",
        "message": "Review mockups: foreman design show → foreman design approve",
    }


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
            from foreman.mock_impl import apply_developer, apply_tester, mock_handoff_payload
            files_changed: list[str] = []
            task_desc = ""
            sp = os.path.join(project, ".foreman", "tasks.json")
            if os.path.exists(sp):
                try:
                    task_desc = (json.load(open(sp)).get(task_id) or {}).get("description") or ""
                except (json.JSONDecodeError, OSError):
                    pass
            if role in ("architect", "developer"):
                files_changed = apply_developer(project, task_id, task_desc)
            elif role == "tester":
                files_changed = apply_tester(project, task_id)
            # Keep dart format --set-exit-if-changed green
            if files_changed and shutil.which("dart"):
                subprocess.run(
                    ["dart", "format", "."], cwd=project,
                    capture_output=True, timeout=60,
                )
            obj = mock_handoff_payload(role, task_id, files_changed or None)
            raw = json.dumps(obj)
            rc, hdata = _run_json(home, project, "handoff.py", "--task-id", task_id, "--role", role, "--stdin", stdin=raw)
            if rc != 0:
                return {"ok": False, "task_id": task_id, "error": "mock_handoff", "handoff": hdata, "log": log}
            step("mock_handoff", role=role, files=files_changed)
            continue

        ok_r, hdata, rlog = _run_role_with_retry(
            home, project, role, prompt, task_id, model=model, auto=auto, dry=dry,
        )
        step("opencode_role", role=role, retries=rlog)
        if dry:
            continue
        if not ok_r and not _handoff_exists(project, task_id, role):
            return {
                "ok": False, "task_id": task_id, "error": "handoff_missing",
                "role": role, "handoff": hdata, "log": log,
            }
        step("handoff_ok", role=role)

    if dry:
        return {"ok": True, "task_id": task_id, "dry_run": True, "log": log}

    if needs_validate and profile not in ("design", "scope"):
        # Match validate pipeline order: fix then format so --set-exit-if-changed is clean
        if mock and shutil.which("dart"):
            subprocess.run(["dart", "fix", "--apply"], cwd=project, capture_output=True, timeout=120)
            subprocess.run(["dart", "format", "."], cwd=project, capture_output=True, timeout=60)
        # Always attempt real validate when flutter is present (including mock code path).
        # Skip only when flutter missing (env), so CI without Flutter still passes plumbing.
        rc, vdata = _run_json(home, project, "validate.py", "--lines", "50")
        step("validate", ok=vdata.get("ok"), exit=rc, mock=mock)
        steps = vdata.get("steps") or []
        env_fail = any(
            isinstance(s, dict) and s.get("name") == "sdk-preflight" and not s.get("ok")
            for s in steps
        ) or "flutter not on PATH" in json.dumps(vdata)
        if env_fail:
            if mock:
                step("validate_skipped_env", ok=True)
                vdata = {"ok": True, "skipped_env": True}
            else:
                return {
                    "ok": False, "task_id": task_id, "error": "env_flutter_missing",
                    "validate": vdata, "log": log,
                    "hint": "Install Flutter SDK; not an app bug",
                }
        elif not vdata.get("ok"):
            if mock:
                # Retry once: fix+format can race with validate's own fix step
                if shutil.which("dart"):
                    subprocess.run(["dart", "fix", "--apply"], cwd=project, capture_output=True, timeout=120)
                    subprocess.run(["dart", "format", "."], cwd=project, capture_output=True, timeout=60)
                rc, vdata = _run_json(home, project, "validate.py", "--lines", "50")
                step("validate_retry", ok=vdata.get("ok"), exit=rc)
                if not vdata.get("ok"):
                    return {
                        "ok": False, "task_id": task_id, "error": "mock_validate_failed",
                        "validate": vdata, "log": log,
                    }
            attempts = 0
            while not vdata.get("ok") and attempts < MAX_DEBUG_ATTEMPTS:
                attempts += 1
                err = json.dumps(vdata)[:2000]
                ok_s, prompt, _ = _spawn_prompt(home, project, "debugger", task_id, error=err)
                if not ok_s:
                    break
                ok_r, _, rlog = _run_role_with_retry(
                    home, project, "debugger", prompt, task_id, model=model, auto=auto, dry=False,
                )
                step("debugger", attempt=attempts, ok=ok_r, retries=rlog)
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

    # Mechanical design-language check (advisory unless findings)
    try:
        from foreman.design_check import check_design_language
        files = None
        sp = os.path.join(project, ".foreman", "tasks.json")
        if os.path.exists(sp):
            try:
                files = json.load(open(sp)).get(task_id, {}).get("files")
            except (json.JSONDecodeError, OSError):
                files = None
        dchk = check_design_language(project, files=files)
        step("design_check", **{k: dchk.get(k) for k in ("ok", "skipped", "findings") if k in dchk})
    except Exception as e:
        step("design_check", ok=True, error=str(e))

    # commit + done
    desc = (plan.get("task_desc") or task_id)[:72]
    rc, cdata = _run_json(home, project, "commit.py", "--task-id", task_id, "--desc", desc)
    step("commit", ok=cdata.get("ok"), data=cdata)
    if not cdata.get("ok"):
        return {"ok": False, "task_id": task_id, "error": "commit_failed", "commit": cdata, "log": log}

    rc, ddata = _run_json(home, project, "state.py", "--mark", task_id, "--status", "done")
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
    skip_design: bool = False,
) -> dict[str, Any]:
    """Run full autonomous ship: ready → design approve gate → seed → OpenCode roles."""
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

    # Design language gate (human-in-the-loop) before implementation
    from foreman import design_gate as dg
    dstat = dg.assess_design(project)
    if not dstat.get("approved") and not skip_design and not force:
        if dry:
            return {
                "ok": True, "dry_run": True, "phase": "design",
                "message": "Would run designer then wait for human approve",
                "design": dstat,
            }
        # Auto-run designer if no draft yet
        if dstat.get("status") in ("missing", "rejected") or not dstat.get("has_handoff"):
            if mock:
                from foreman.mock_impl import mock_handoff_payload
                raw = json.dumps(mock_handoff_payload("designer", "design"))
                _run_json(home, project, "handoff.py", "--task-id", "design", "--role", "designer", "--stdin", stdin=raw)
                dr = {"ok": True, "mock": True}
            else:
                dr = run_designer_phase(home, project, mock=False, model=model, auto=auto)
            dstat = dg.assess_design(project)
            if mock:
                # Prove/CI: auto-approve design language after draft
                dg.approve(project)
                dstat = dg.assess_design(project)
            elif not dstat.get("approved"):
                preview = os.path.join(project, ".foreman", "design_preview.md")
                return {
                    "ok": False,
                    "phase": "design",
                    "waiting_for": "design_approve",
                    "message": "WAITING FOR: human design approval (mockups ready)",
                    "design": dstat,
                    "designer": dr,
                    "preview_path": preview if os.path.exists(preview) else None,
                    "next_commands": [
                        "foreman design show",
                        "foreman design approve",
                        "foreman run",
                    ],
                    "hint": "foreman design show  &&  foreman design approve  &&  foreman run",
                }
        else:
            preview = os.path.join(project, ".foreman", "design_preview.md")
            return {
                "ok": False,
                "phase": "design",
                "waiting_for": "design_approve",
                "message": "WAITING FOR: human design approval",
                "design": dstat,
                "preview_path": preview if os.path.exists(preview) else None,
                "language_path": dstat.get("language_path"),
                "next_commands": [
                    "foreman design show",
                    "foreman design approve",
                    "foreman run",
                ],
                "hint": "foreman design show  &&  foreman design approve  &&  foreman run",
            }

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

    from foreman.log import metrics_summary
    ms = metrics_summary(_mem_dir(project))
    role_sessions = (ms.get("by_kind") or {}).get("role_session", 0)
    return {
        "ok": True,
        "phase": "ship",
        "seed": seed,
        "tasks_run": n,
        "results": results,
        "cost_proxy": {
            "role_sessions": role_sessions,
            "handoff_success_rate": ms.get("handoff_success_rate"),
            "handoff_miss": ms.get("handoff_miss"),
            "note": "proxy only — not provider $; see foreman metrics",
        },
        "message": "DAG empty or max tasks reached" if n else "no ready tasks",
    }
