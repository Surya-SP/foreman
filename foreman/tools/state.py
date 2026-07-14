#!/usr/bin/env python3
"""Persistent task DAG.

Actions:
  --add <id> --desc "..." [--deps a,b] [--acceptance "..."]
  --import                     (stdin JSON: {tasks:[...]} or [...])
  --template <name>            (seed from templates/<name>.json)
  --mark <id> --status STATUS [--error TEXT]
  --pending | --ready | --blocked | --all | --dag | --reset
  --task <id>
  --plan  <id>                 analyze task → needed roles only (PRINT)
  --guide <id>                 next-step for one task (uses smart plan)
  --auto  <id>                 remaining sequence for needed roles (PRINT)
  --batch [N]                  N ready tasks safe to run in parallel
"""
import json, os, re, sys, time
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
sys.path.insert(0, _ROOT)

from foreman.log import log

_start = time.time()

def _arg(name, default=None):
    return next((sys.argv[i+1] for i,a in enumerate(sys.argv) if a==name), default)

target = os.path.abspath(_arg("--project") or os.environ.get("FOREMAN_PROJECT") or ".")
state_dir = os.path.join(target, ".foreman")
os.makedirs(state_dir, exist_ok=True)
state_path = os.path.join(state_dir, "tasks.json")
handoff_dir = os.path.join(state_dir, "handoffs")
force_marker = os.path.join(handoff_dir, ".forced.jsonl")

def _load():
    if not os.path.exists(state_path): return {}
    try: return json.load(open(state_path))
    except (json.JSONDecodeError, OSError): return {}

def _save(state): json.dump(state, open(state_path, "w"), indent=2)

def _out(obj, code=0):
    from foreman import ui
    if obj.get("profile") is not None and obj.get("task") and (
        "--plan" in sys.argv or "--auto" in sys.argv
    ):
        ui.state_plan_view(obj)
    json.dump(obj, sys.stdout, indent=2)
    print()
    log(state_dir, "state.py", code, int((time.time()-_start)*1000))
    sys.exit(code)

def _status(t): return t.get("status", "pending")
def _deps_done(t, s): return all(s.get(d, {}).get("status") == "done" for d in t.get("depends_on", []))

def _make_task(tid, desc, deps=None, acceptance=""):
    return {"id": tid, "description": desc or tid, "acceptance": acceptance,
            "status": "pending", "depends_on": list(deps or []),
            "attempts": 0, "last_error": ""}

def _forced_roles(tid):
    """Which handoffs for tid were saved with --force (suspect quality)."""
    if not os.path.exists(force_marker): return []
    forced = []
    try:
        for line in open(force_marker):
            r = json.loads(line)
            if r.get("task_id") == tid: forced.append(r.get("role"))
    except (json.JSONDecodeError, OSError): pass
    return forced

def _handoff_files(tid):
    if not os.path.isdir(handoff_dir): return set()
    return {n.split(".", 2)[1] for n in os.listdir(handoff_dir)
            if n.startswith(f"{tid}.") and n.endswith(".json")}

def _touches_files(tid):
    """Return the set of files an architect handoff planned for tid."""
    p = os.path.join(handoff_dir, f"{tid}.architect.json")
    if not os.path.exists(p): return set()
    try:
        arch = json.load(open(p))
        files = arch.get("files", [])
        return {(f.get("path") if isinstance(f, dict) else f) for f in files}
    except (json.JSONDecodeError, OSError): return set()

# ── Smart role planner ──────────────────────────────────────────────────────
# Classify task text → only the sub-agents that are actually needed.
# profile: full | implement | bugfix | tests | review | refactor | design | scope

_RE_BUG = re.compile(
    r"\b(bug|fix|crash|error|exception|stacktrace|stack\s*trace|failing|"
    r"broken|regression|null\s*check|npe|segfault|assert(?:ion)?\s*error|"
    r"validate\s+fail|analyzer\s+error|build\s+fail|runtime\s+error)\b",
    re.I,
)
_RE_TEST = re.compile(
    r"\b(unit\s*test|widget\s*test|integration\s*test|golden\s*test|"
    r"test\s*coverage|write\s+tests?|add\s+tests?|missing\s+tests?|"
    r"test\s+plan|qa\s+only|coverage\s+gap)\b",
    re.I,
)
_RE_REVIEW = re.compile(
    r"\b(code\s*review|review\s+(this|the|pr|diff|change)|is\s+this\s+ok|"
    r"lgtm|approve|verdict)\b",
    re.I,
)
_RE_REFACTOR = re.compile(
    r"\b(refactor|cleanup|clean\s*up|rename|simplify|dedupe|deduplicate|"
    r"extract\s+(method|widget|class)|reorganize|lint\s+fix)\b",
    re.I,
)
_RE_DESIGN = re.compile(
    r"\b(architect(?:ure)?|design\s+(only|the|how)|how\s+should\s+we\s+split|"
    r"structure\s+only|plan\s+only|approach\s+only)\b",
    re.I,
)
_RE_SCOPE = re.compile(
    r"\b(prd|product\s*owner|priorit|backlog|scope|roadmap|"
    r"what\s+should\s+we\s+build|break\s+down\s+(the\s+)?prd)\b",
    re.I,
)
_RE_FEATURE = re.compile(
    r"\b(add|implement|build|create|new\s+feature|screen|page|widget|"
    r"flow|feature|integrate|support)\b",
    re.I,
)
_RE_COMPLEX = re.compile(
    r"\b(auth|login|oauth|payment|checkout|sync|offline|migration|"
    r"multi[- ]?step|navigation\s+graph|state\s+management|bloc|riverpod|"
    r"provider|database|sqlite|hive|api\s+client|websocket|push\s+notif|"
    r"permission|secure\s*storage|deep\s*link)\b",
    re.I,
)
_RE_TRIVIAL = re.compile(
    r"\b(typo|wording|copy\s+change|label|padding|margin|color|hex|"
    r"spacing|icon\s+only|string\s+const|const\s+string|bump\s+version|"
    r"changelog|comment\s+only|docs?\s+only)\b",
    re.I,
)
_RE_TEST_SIGNAL = re.compile(
    r"\b(test|spec|coverage|golden|mock|fake)\b", re.I,
)

def _task_blob(t):
    parts = [
        str(t.get("id") or ""),
        str(t.get("description") or ""),
        str(t.get("acceptance") or ""),
        str(t.get("last_error") or ""),
    ]
    return " ".join(parts)

def _classify_task(tid, t):
    """Return (profile, reasons[]) from task text + status signals."""
    blob = _task_blob(t)
    reasons = []
    st = _status(t)

    if st == "failed" or t.get("last_error"):
        reasons.append("failed/last_error → bugfix")
        return "bugfix", reasons

    override = (t.get("profile") or t.get("pipeline") or "").strip().lower()
    if override in ("full", "implement", "bugfix", "tests", "review",
                    "refactor", "design", "scope"):
        reasons.append(f"task.profile={override}")
        return override, reasons

    if tid.startswith("chat-") and _RE_BUG.search(blob):
        reasons.append("chat-* + bug keywords")
        return "bugfix", reasons

    # Intent verbs first (even if domain words like "login" appear)
    if _RE_REFACTOR.search(blob):
        reasons.append("refactor keywords")
        return "refactor", reasons
    if _RE_REVIEW.search(blob):
        reasons.append("review keywords")
        return "review", reasons
    if _RE_DESIGN.search(blob):
        reasons.append("design-only keywords")
        return "design", reasons
    if _RE_SCOPE.search(blob) and not _RE_FEATURE.search(blob):
        reasons.append("scope/PRD keywords")
        return "scope", reasons
    if _RE_BUG.search(blob):
        # "fix login" / stacktrace → bugfix; pure "add login" has no bug words
        reasons.append("bug/fix keywords")
        return "bugfix", reasons
    if _RE_TEST.search(blob) and not _RE_FEATURE.search(blob):
        reasons.append("test-only keywords")
        return "tests", reasons

    if _RE_COMPLEX.search(blob) and _RE_FEATURE.search(blob):
        reasons.append("complex domain + feature → full pipeline")
        return "full", reasons
    if _RE_COMPLEX.search(blob) and not _RE_TRIVIAL.search(blob):
        reasons.append("complex domain keywords → full pipeline")
        return "full", reasons
    if _RE_TRIVIAL.search(blob):
        reasons.append("trivial UI/copy → implement (skip qa_lead)")
        return "implement", reasons
    if _RE_FEATURE.search(blob) or len(blob.split()) >= 6:
        acc = str(t.get("acceptance") or "")
        if _RE_TEST_SIGNAL.search(acc) or acc.count(";") >= 2 or acc.count("\n") >= 2:
            reasons.append("feature + multi acceptance/tests → full")
            return "full", reasons
        reasons.append("feature/default → implement (architect+dev; tests if needed)")
        return "implement", reasons

    reasons.append("fallback → full pipeline")
    return "full", reasons

_PROFILE_ROLES = {
    "full":      ["architect", "qa_lead", "developer", "tester"],
    "implement": ["architect", "developer", "tester"],
    "bugfix":   ["debugger"],
    "tests":     ["qa_lead", "tester"],
    "review":    [],
    "refactor":  ["refactorer"],
    "design":    ["architect"],
    "scope":     ["product_owner"],
}

def _plan_roles(tid, t, have=None):
    """Compute needed roles + remaining work for a task."""
    have = set(have if have is not None else _handoff_files(tid))
    st = _status(t)
    profile, reasons = _classify_task(tid, t)
    roles = list(_PROFILE_ROLES.get(profile, _PROFILE_ROLES["full"]))

    if profile == "implement":
        touches = _touches_files(tid) if "architect" in have else set()
        blob = _task_blob(t)
        if touches and len(touches) <= 1 and not _RE_TEST_SIGNAL.search(blob):
            if "tester" in roles:
                roles = [r for r in roles if r != "tester"]
                reasons.append("single-file plan + no test signal → skip tester")

    needs_validate = profile not in ("design", "scope")
    needs_reviewer = needs_validate and profile not in ("design", "scope")
    needs_code = profile not in ("design", "scope", "review")

    remaining_roles = [r for r in roles if r not in have]
    skipped = [r for r in roles if r in have]

    return {
        "profile": profile,
        "reasons": reasons,
        "roles": roles,
        "remaining_roles": remaining_roles,
        "already_done": skipped,
        "needs_validate": needs_validate,
        "needs_reviewer": needs_reviewer,
        "needs_code": needs_code,
        "status": st,
    }

def _sequence_for_plan(tid, plan):
    """Build printable command sequence from a smart plan."""
    seq, step = [], 1
    for role in plan["remaining_roles"]:
        if role == "architect":
            seq.append({"step": step, "role": role,
                        "cmd": f"foreman spawn architect {tid} --self-handoff",
                        "then": "Task tool agent=architect"}); step += 1
        elif role == "qa_lead":
            seq.append({"step": step, "role": role,
                        "cmd": f"foreman spawn qa_lead {tid} --self-handoff",
                        "then": "Task tool agent=qa_lead"}); step += 1
        elif role == "developer":
            load = " --load-from architect" if "architect" in plan["roles"] else ""
            seq.append({"step": step, "role": role,
                        "cmd": f"foreman spawn developer {tid}{load} --self-handoff",
                        "then": "Task tool agent=developer"}); step += 1
        elif role == "tester":
            load = " --load-from qa_lead" if "qa_lead" in plan["roles"] else ""
            seq.append({"step": step, "role": role,
                        "cmd": f"foreman spawn tester {tid}{load} --self-handoff",
                        "then": "Task tool agent=tester"}); step += 1
        elif role == "debugger":
            seq.append({"step": step, "role": role,
                        "cmd": f"foreman spawn debugger {tid} --error \"$(foreman validate --lines 200)\" --self-handoff",
                        "then": "Task tool agent=debugger"}); step += 1
        elif role == "refactorer":
            seq.append({"step": step, "role": role,
                        "cmd": f"foreman spawn refactorer {tid} --self-handoff",
                        "then": "Task tool agent=refactorer"}); step += 1
        elif role == "product_owner":
            seq.append({"step": step, "role": role,
                        "cmd": f"foreman spawn product_owner {tid} --self-handoff",
                        "then": "Task tool agent=product_owner; maybe state import"}); step += 1

    if plan["status"] == "done":
        return [{"step": 0, "cmd": "# already done"}]

    if plan["needs_validate"] and plan["profile"] != "review":
        branches = {
            "PASS": [f"foreman verify --task-id {tid}"],
            "FAIL": [f"foreman spawn debugger {tid} --error \"$OUT\" --self-handoff  (retry ≤3)",
                     f"foreman rollback && foreman state fail {tid}  (if 3 fails)"],
        }
        if plan["needs_reviewer"]:
            branches["PASS"] += [
                f"foreman spawn reviewer {tid}",
                "# Task tool agent=reviewer (NO self-handoff)",
                f"printf '%s\\n' \"$REV\" | foreman handoff {tid} reviewer",
                f"if APPROVED: foreman commit --task-id {tid} --desc \"...\"",
                f"             foreman state done {tid}",
                f"if CHANGES_REQUIRED: foreman spawn refactorer {tid} --load-from reviewer --self-handoff",
                "                     then re-run validate",
            ]
        else:
            branches["PASS"] += [
                f"foreman commit --task-id {tid} --desc \"...\"",
                f"foreman state done {tid}",
            ]
        seq.append({"step": step, "cmd": "foreman validate --lines 200", "branches": branches})
    elif plan["profile"] == "review":
        seq.append({"step": step, "role": "reviewer",
                    "cmd": f"foreman spawn reviewer {tid}",
                    "then": "Task tool agent=reviewer (NO self-handoff); handoff; act on verdict"})
    elif plan["profile"] == "design":
        seq.append({"step": step, "cmd": f"# design-only: keep handoff; foreman state done {tid} if no code needed"})
    elif plan["profile"] == "scope":
        seq.append({"step": step, "cmd": f"# scope: import tasks if PO returned tasks[]; then state done {tid}"})

    return seq

# ---- Flags ----
task_id  = _arg("--add") or _arg("--mark") or _arg("--task") or _arg("--guide") or _arg("--auto") or _arg("--plan") or ""
desc     = _arg("--desc", "")
deps_str = _arg("--deps", "")
accept   = _arg("--acceptance", "")
status_v = _arg("--status", "")
error_v  = _arg("--error", "")
template = _arg("--template")
batch_n  = _arg("--batch")

# ---- Reset ----
if "--reset" in sys.argv:
    _save({}); _out({"ok": True, "message": "Reset."})

# ---- Resume: find in-flight task and its next step ----
if "--resume" in sys.argv:
    state = _load()
    # Priority: running > failed > partial (has handoffs but not done) > ready
    inflight = None; category = ""
    for tid, t in state.items():
        if t.get("status") == "running":
            inflight = tid; category = "running"; break
    if not inflight:
        for tid, t in state.items():
            if t.get("status") == "failed":
                inflight = tid; category = "failed"; break
    if not inflight:
        for tid, t in state.items():
            if t.get("status") == "pending" and _handoff_files(tid) and _deps_done(t, state):
                inflight = tid; category = "partial"; break
    if not inflight:
        # Just first ready
        for tid, t in sorted(state.items()):
            if t.get("status") == "pending" and _deps_done(t, state):
                inflight = tid; category = "ready"; break
    if not inflight:
        _out({"ok": True, "message": "Nothing to resume — no tasks in flight or ready"})
    _out({"ok": True, "task": inflight, "category": category,
          "hint": f"foreman state guide {inflight}"})

# ---- Escalations: any reviewer verdict that said escalate ----
if "--escalations" in sys.argv:
    state = _load()
    esc = [{"id": tid, "verdict": t.get("verdict"), "escalate_to": t.get("escalate_to")}
           for tid, t in state.items() if t.get("escalate_to")]
    _out({"ok": True, "count": len(esc), "escalations": esc})

state = _load()

# ---- Template ----
if template:
    tpl_path = os.path.join(_ROOT, "templates", f"{template}.json")
    if not os.path.exists(tpl_path):
        available = sorted(f[:-5] for f in os.listdir(os.path.join(_ROOT, "templates")) if f.endswith(".json"))
        _out({"ok": False, "message": f"Unknown template '{template}'", "available": available}, 1)
    tpl = json.load(open(tpl_path))
    # Framework compatibility check: if project isn't the template's framework, warn.
    warns = []
    tpl_fw = tpl.get("framework")
    if tpl_fw:
        has_pubspec = os.path.exists(os.path.join(target, "pubspec.yaml"))
        if tpl_fw == "flutter" and not has_pubspec:
            warns.append(f"Template '{template}' is {tpl_fw}-specific but no pubspec.yaml found. "
                         f"Run `flutter create .` first, then re-run this command.")
    added = skipped = 0
    for t in tpl.get("tasks", []):
        if t["id"] in state: skipped += 1; continue
        state[t["id"]] = _make_task(t["id"], t.get("description",""),
                                    t.get("depends_on", []), t.get("acceptance", ""))
        added += 1
    _save(state)
    _out({"ok": True, "template": template, "framework": tpl_fw or "any",
          "added": added, "skipped": skipped, "total": len(state), "warnings": warns})

# ---- Import ----
if "--import" in sys.argv:
    raw = sys.stdin.read()
    try: obj = json.loads(raw)
    except json.JSONDecodeError as e: _out({"ok": False, "message": f"Invalid JSON: {e}"}, 1)
    tasks = obj.get("tasks") if isinstance(obj, dict) else obj
    if not isinstance(tasks, list): _out({"ok": False, "message": "Expected array or {tasks:[...]}"}, 1)
    added = skipped = 0
    for t in tasks:
        if not isinstance(t, dict) or not t.get("id"): skipped += 1; continue
        if t["id"] in state: skipped += 1; continue
        state[t["id"]] = _make_task(t["id"], t.get("description",""),
                                    t.get("depends_on", []), t.get("acceptance", ""))
        added += 1
    _save(state)
    _out({"ok": True, "added": added, "skipped": skipped, "total": len(state)})

# ---- Add ----
def _has_cycle(state, new_id, new_deps):
    """DFS from new_id through state graph; return True if new_id reachable via deps."""
    # Reverse: for each dep, check its deps chain doesn't reach back to new_id.
    def visits(current, visiting):
        if current == new_id: return True
        if current in visiting: return False
        visiting.add(current)
        for d in state.get(current, {}).get("depends_on", []):
            if visits(d, visiting): return True
        return False
    return any(visits(d, set()) for d in new_deps)

if "--add" in sys.argv:
    if not task_id: _out({"ok": False, "message": "Need task id"}, 1)
    if task_id in state: _out({"ok": False, "message": f"Task '{task_id}' exists"}, 1)
    deps = [d.strip() for d in deps_str.split(",") if d.strip()] if deps_str else []
    unknown_deps = [d for d in deps if d not in state]
    if unknown_deps:
        _out({"ok": False, "message": f"Unknown deps: {unknown_deps}"}, 1)
    if _has_cycle(state, task_id, deps):
        _out({"ok": False, "message": f"Circular dependency: {task_id} → {deps}"}, 1)
    state[task_id] = _make_task(task_id, desc, deps, accept)
    _save(state)
    _out({"ok": True, "task_id": task_id, "status": "pending"})

# ---- Mark ----
if "--mark" in sys.argv:
    if task_id not in state: _out({"ok": False, "message": f"Task '{task_id}' not found"}, 1)

    # Safety rails when marking done: check tester + commit exist.
    warnings = []
    if status_v == "done" and "--force" not in sys.argv:
        # Tests must pass (if a tester handoff exists)
        tp = os.path.join(handoff_dir, f"{task_id}.tester.json")
        if os.path.exists(tp):
            try:
                tester = json.load(open(tp))
                if tester.get("all_pass") is False:
                    _out({"ok": False, "message": "Tester reported all_pass=false. Fix tests or pass --force.",
                          "hint": "foreman spawn debugger " + task_id + "  or  foreman state mark done --force"}, 1)
            except (json.JSONDecodeError, OSError): pass
        # Reviewer must approve (if reviewer handoff exists)
        rp = os.path.join(handoff_dir, f"{task_id}.reviewer.json")
        if os.path.exists(rp):
            try:
                rev = json.load(open(rp))
                v = rev.get("verdict", "")
                if v == "REJECT":
                    _out({"ok": False, "message": "Reviewer REJECTED. Escalate or pass --force.",
                          "escalate_to": rev.get("escalate_to")}, 1)
                if v == "CHANGES_REQUIRED":
                    _out({"ok": False, "message": "Reviewer requested changes. Run refactorer or pass --force."}, 1)
            except (json.JSONDecodeError, OSError):
                pass
        # Hard require commit (autonomy integrity)
        if not state[task_id].get("commit_sha"):
            _out({"ok": False,
                  "message": "Cannot mark done without commit_sha. Run: foreman commit --task-id "
                             + task_id + " --desc \"...\"",
                  "hint": "commit first, then state done (or --force only for recovery)"}, 1)

    if status_v: state[task_id]["status"] = status_v
    if error_v:
        state[task_id]["last_error"] = error_v
        state[task_id]["status"] = "failed"
    _save(state)
    _out({"ok": True, "task_id": task_id, "status": state[task_id]["status"], "warnings": warnings})

# ---- Task detail (with cross-task conflict detection) ----
if "--task" in sys.argv:
    if task_id not in state: _out({"ok": False, "message": f"Task '{task_id}' not found"}, 1)
    t = state[task_id].copy()
    t["handoffs"] = sorted(_handoff_files(task_id))
    t["forced_handoffs"] = _forced_roles(task_id)
    # Cross-task conflicts: other in-flight tasks that touch the same files.
    my_files = set(t.get("files") or [])
    conflicts = []
    if my_files:
        for other_id, other_t in state.items():
            if other_id == task_id: continue
            if other_t.get("status") == "done": continue
            other_files = set(other_t.get("files") or [])
            shared = my_files & other_files
            if shared:
                conflicts.append({"task": other_id, "status": other_t.get("status"),
                                  "shared_files": sorted(shared)})
    t["conflicts"] = conflicts
    _out({"ok": True, "task": t})

# ---- Plan (smart: analyze → needed roles only) ----
if "--plan" in sys.argv:
    if not task_id:
        _out({"ok": False, "message": "state plan requires a task-id",
              "hint": "foreman state plan scaffold"}, 1)
    if task_id not in state:
        _out({"ok": False, "message": f"Task '{task_id}' not found", "hint": "foreman state all"}, 1)
    t = state[task_id]
    have = _handoff_files(task_id)
    plan = _plan_roles(task_id, t, have)
    seq = _sequence_for_plan(task_id, plan)
    _out({"ok": True, "task": task_id, "status": plan["status"],
          "task_desc": t.get("description", ""),
          "acceptance": t.get("acceptance", ""),
          "profile": plan["profile"],
          "reasons": plan["reasons"],
          "roles": plan["roles"],
          "remaining_roles": plan["remaining_roles"],
          "already_done": plan["already_done"],
          "needs_validate": plan["needs_validate"],
          "needs_reviewer": plan["needs_reviewer"],
          "sequence": seq,
          "note": "SMART PLAN — only needed roles. Execute via spawn→Task; or foreman run"})

# ---- Guide (next step, smart) ----
if "--guide" in sys.argv:
    if task_id not in state: _out({"ok": False, "message": f"Task '{task_id}' not found"}, 1)
    t = state[task_id]; st = _status(t)
    have = _handoff_files(task_id)
    forced = _forced_roles(task_id)
    warns = []
    if forced: warns.append(f"Handoffs saved with --force (suspect): {forced}")
    plan = _plan_roles(task_id, t, have)
    if st == "done":
        steps = ["Task complete.",
                 "(optional) foreman deploy list  → ask user which platform/device",
                 "(optional) foreman deploy install --device <id>  → build + install for testing"]
    elif st == "failed" or plan["profile"] == "bugfix" and "debugger" in plan["remaining_roles"]:
        steps = [f"foreman spawn debugger {task_id} --error \"$(foreman validate)\"  → Task agent=debugger"]
    elif plan["remaining_roles"]:
        role = plan["remaining_roles"][0]
        steps = [f"profile={plan['profile']}: foreman spawn {role} {task_id}  → Task agent={role}",
                 f"foreman state plan {task_id}  # full smart sequence"]
    elif plan["needs_validate"]:
        steps = ["foreman validate --lines 200",
                 f"# on pass: foreman verify --task-id {task_id}" +
                 (f" && foreman spawn reviewer {task_id}" if plan["needs_reviewer"] else "")]
    else:
        steps = [f"No remaining roles (profile={plan['profile']}). Consider: foreman state done {task_id}"]
    _out({"ok": True, "task": task_id, "status": st, "profile": plan["profile"],
          "roles": plan["roles"], "remaining_roles": plan["remaining_roles"],
          "reasons": plan["reasons"], "next_steps": steps, "warnings": warns})

# ---- Auto (smart remaining sequence) ----
if "--auto" in sys.argv:
    if not task_id:
        _out({"ok": False, "message": "state auto requires a task-id",
              "hint": "foreman state auto scaffold",
              "note": "auto only PRINTS the plan — use foreman run to execute"}, 1)
    if task_id not in state: _out({"ok": False, "message": f"Task '{task_id}' not found",
                                   "hint": "foreman state all"}, 1)
    t = state[task_id]
    have = _handoff_files(task_id)
    st = _status(t)
    plan = _plan_roles(task_id, t, have)

    if st == "done":
        _out({"ok": True, "task": task_id, "status": "done", "profile": plan["profile"],
              "sequence": [{"step": 0, "cmd": "# already done"}],
              "note": "This is a plan only. Autonomous execution: foreman run"})
    if st == "failed":
        plan = _plan_roles(task_id, {**t, "status": "failed", "last_error": t.get("last_error") or "failed"}, have)
        seq = _sequence_for_plan(task_id, {**plan, "profile": "bugfix",
                                           "roles": ["debugger"],
                                           "remaining_roles": ["debugger"] if "debugger" not in have else [],
                                           "needs_validate": True, "needs_reviewer": True})
        _out({"ok": True, "task": task_id, "status": "failed", "profile": "bugfix",
              "reasons": plan["reasons"], "sequence": seq,
              "note": "This is a plan only. Autonomous execution: foreman run"})

    seq = _sequence_for_plan(task_id, plan)
    _out({"ok": True, "task": task_id, "status": st,
          "task_desc": t.get("description", ""),
          "acceptance": t.get("acceptance", ""),
          "profile": plan["profile"],
          "reasons": plan["reasons"],
          "roles": plan["roles"],
          "remaining_roles": plan["remaining_roles"],
          "already_done": plan["already_done"],
          "sequence": seq,
          "note": "SMART PLAN ONLY — needed roles only. Autonomous: foreman run  |  TUI: opencode --agent foreman /ship"})

# ---- Batch (parallel-safe ready tasks) ----
if "--batch" in sys.argv:
    n = int(batch_n) if batch_n and batch_n.isdigit() else 3
    ready = [(k, v) for k, v in state.items() if _status(v) == "pending" and _deps_done(v, state)]
    ready.sort(key=lambda kv: kv[0])
    picked = []
    used_files = set()
    for tid, t in ready:
        touches = _touches_files(tid)
        # No architect yet → conservatively assume it might touch anything → only allow
        # as first pick.
        if not touches:
            if not picked: picked.append({"id": tid, "desc": t.get("description",""), "touches": []})
            continue
        if touches & used_files: continue
        picked.append({"id": tid, "desc": t.get("description",""), "touches": sorted(touches)})
        used_files |= touches
        if len(picked) >= n: break
    _out({"ok": True, "batch_size": len(picked), "tasks": picked,
          "note": "Tasks whose planned files don't overlap. Safe to spawn in parallel."})

# ---- Pending / Ready / Blocked / All / Dag ----
if "--pending" in sys.argv:
    pending = {k: v for k, v in state.items() if _status(v) in ("pending", "running", "failed")}
    ready   = {k: v for k, v in pending.items() if _deps_done(v, state)}
    blocked = {k: v for k, v in pending.items() if not _deps_done(v, state)}
    _out({"ok": True, "pending_count": len(pending), "ready_count": len(ready),
          "blocked_count": len(blocked),
          "ready":   [{"id": k, "desc": v.get("description","")[:60]} for k,v in sorted(ready.items())],
          "blocked": [{"id": k, "desc": v.get("description","")[:60], "depends_on": v.get("depends_on",[])} for k,v in sorted(blocked.items())]})

if "--ready" in sys.argv:
    r = {k: v for k, v in state.items() if _status(v) == "pending" and _deps_done(v, state)}
    _out({"ok": True, "count": len(r),
          "tasks": [{"id": k, "desc": v.get("description","")[:80]} for k,v in sorted(r.items())]})

if "--blocked" in sys.argv:
    b = {k: v for k, v in state.items() if _status(v) in ("pending","running") and not _deps_done(v, state)}
    _out({"ok": True, "count": len(b),
          "tasks": [{"id": k, "desc": v.get("description","")[:60], "depends_on": v.get("depends_on",[])} for k,v in sorted(b.items())]})

if "--all" in sys.argv:
    _out({"ok": True, "count": len(state), "tasks": state})

if "--dag" in sys.argv:
    lines = ["graph TD;"]
    for tid, t in state.items():
        cls = {"done":"done","failed":"failed","blocked":"blocked","pending":"pending","running":"running"}.get(_status(t),"pending")
        lines.append(f"    {tid}[\"{t.get('description', tid)[:30]}\"]:::{cls};")
        for dep in t.get("depends_on", []):
            lines.append(f"    {dep} --> {tid};")
    lines += ["classDef done fill:#1a7f37,color:#fff;",
              "classDef failed fill:#cf222e,color:#fff;",
              "classDef blocked fill:#9a6700,color:#fff;",
              "classDef pending fill:#57606a,color:#fff;",
              "classDef running fill:#0969da,color:#fff;"]
    _out({"ok": True, "mermaid": "\n".join(lines)})

# Default: summary
total = len(state)
ready_n = sum(1 for t in state.values() if _status(t) == "pending" and _deps_done(t, state))
done_n = sum(1 for t in state.values() if _status(t) == "done")
pending_n = sum(1 for t in state.values() if _status(t) == "pending")
failed_n = sum(1 for t in state.values() if _status(t) == "failed")
if total == 0:
    hint = ("Task DAG empty. Seed: foreman state template todo|chat|blog  "
            "OR product_owner → state import. Autonomous: foreman run")
elif ready_n:
    first = next(k for k, t in sorted(state.items())
                 if _status(t) == "pending" and _deps_done(t, state))
    hint = (f"{ready_n} ready. Next: foreman state plan {first}  "
            f"|  Autonomous: foreman run  |  Guide: foreman state guide {first}")
elif pending_n:
    hint = "Tasks pending but blocked on deps. See: foreman state blocked"
elif done_n == total:
    hint = "All tasks done. Optional: foreman deploy list"
else:
    hint = "foreman state all | resume | escalations"
_out({"ok": True, "total": total, "done": done_n, "pending": pending_n,
      "failed": failed_n, "ready": ready_n, "hint": hint})
