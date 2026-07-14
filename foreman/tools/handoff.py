#!/usr/bin/env python3
"""Persist a sub-agent's JSON output for the next role to load.

Extracts the outermost {...} JSON block from the raw response, validates
required keys against the role's contract, and writes to
.foreman/handoffs/<task_id>.<role>.json.

Usage:
  handoff.py --project . --task-id t3 --role architect --stdin
  handoff.py --project . --task-id t3 --role architect --data '{...}'
"""
import json, os, re, sys, time
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
sys.path.insert(0, _ROOT)

from foreman.log import log
from foreman.schemas import check
from foreman import memory as mem
from foreman.jsonutil import extract_json_object

_start = time.time()

def _arg(name, default=None):
    return next((sys.argv[i+1] for i,a in enumerate(sys.argv) if a==name), default)

target = os.path.abspath(_arg("--project") or ".")
task_id = _arg("--task-id")
role = _arg("--role")
data = _arg("--data")

def _out(obj, code):
    json.dump(obj, sys.stdout)
    log(os.path.join(target, ".foreman"), "handoff.py", code, int((time.time()-_start)*1000),
        extra={"role": role or "", "task_id": task_id or ""})
    sys.exit(code)

if not (task_id and role):
    _out({"ok": False, "message": "Need --task-id and --role"}, 1)

if "--stdin" in sys.argv:
    data = sys.stdin.read()
if not data:
    _out({"ok": False, "message": "No data (use --data or --stdin)"}, 1)

# Balanced JSON extract (no greedy DOTALL)
obj, raw_or_err = extract_json_object(data)
if obj is None:
    _out({"ok": False, "message": raw_or_err, "raw_preview": (data or "")[:200]}, 1)
raw = raw_or_err

errors = check(role, obj)
forced = False
if errors and "--force" not in sys.argv:
    _out({"ok": False, "message": "Schema violation", "errors": errors, "hint": "Fix the sub-agent output or pass --force"}, 1)
if errors and "--force" in sys.argv:
    forced = True

hdir = os.path.join(target, ".foreman", "handoffs")
os.makedirs(hdir, exist_ok=True)
path = os.path.join(hdir, f"{task_id}.{role}.json")

# If a handoff already exists, archive the old one (timestamped) so we can trace revisions.
overwrote = False
if os.path.exists(path):
    overwrote = True
    archive = os.path.join(hdir, f"{task_id}.{role}.{int(time.time())}.json")
    try:
        os.rename(path, archive)
    except OSError:
        pass

with open(path, "w") as f:
    json.dump(obj, f, indent=2)

# Record forced writes so `state guide` can warn about them
if forced:
    with open(os.path.join(hdir, ".forced.jsonl"), "a") as f:
        f.write(json.dumps({"task_id": task_id, "role": role, "errors": errors, "ts": time.time()}) + "\n")

# ─── Auto-propagate handoff data into task state ────────────────────────────
# Handoffs are the source of truth for their own facts; state.json mirrors the
# few fields other tools need to look up cheaply (files, verdict, attempts).
state_path = os.path.join(target, ".foreman", "tasks.json")
state_updates = {}
if os.path.exists(state_path):
    try:
        state_all = json.load(open(state_path))
    except (json.JSONDecodeError, OSError):
        state_all = {}
    task = state_all.get(task_id, {})
    if role == "architect":
        # files: [{path, purpose}] or [str]
        arch_files = []
        for f in obj.get("files", []):
            arch_files.append(f.get("path") if isinstance(f, dict) else f)
        if arch_files:
            task["files"] = arch_files; state_updates["files"] = arch_files
    elif role == "developer":
        if obj.get("files_changed"):
            task["files"] = obj["files_changed"]; state_updates["files"] = obj["files_changed"]
    elif role == "reviewer":
        task["verdict"] = obj.get("verdict", "")
        task["escalate_to"] = obj.get("escalate_to")
        state_updates.update({"verdict": task["verdict"], "escalate_to": task["escalate_to"]})
    elif role == "debugger":
        task["attempts"] = int(task.get("attempts", 0)) + 1
        state_updates["attempts"] = task["attempts"]
    if state_updates and task_id in state_all:
        state_all[task_id] = task
        with open(state_path, "w") as f:
            json.dump(state_all, f, indent=2)

# ─── Memory graph: record decisions + file edges (facts only) ───────────────
memory_rec = {}
try:
    memory_rec = mem.record_handoff(target, task_id, role, obj, path)
except Exception as e:
    memory_rec = {"ok": False, "message": str(e)}

from foreman import ui
rel = os.path.relpath(path, target) if path.startswith(target) else path
ui.handoff_view(role, task_id, True, path=rel)
_out({"ok": True, "path": path, "bytes": os.path.getsize(path),
      "schema_errors": errors, "forced": forced, "overwrote_previous": overwrote,
      "state_updates": state_updates, "memory": memory_rec}, 0)
