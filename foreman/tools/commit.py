#!/usr/bin/env python3
"""Git commit for a task.

Usage:
  commit.py --project . --task-id t3 --desc "added login"
  commit.py --project . --task-id t3 --desc "..." --branch feature/t3
  commit.py --project . --task-id t3 --desc "..." --dry-run
"""
import json, os, subprocess, sys, time
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..")))

from foreman.config import Config
from foreman.vcs import Vcs
from foreman.log import log

_start = time.time()

def _arg(name, default=None):
    return next((sys.argv[i+1] for i,a in enumerate(sys.argv) if a==name), default)

target = os.path.abspath(_arg("--project") or os.environ.get("FOREMAN_PROJECT") or ".")
task_id = _arg("--task-id")
desc = _arg("--desc", "")
branch = _arg("--branch")
dry = "--dry-run" in sys.argv

def _out(obj, code):
    json.dump(obj, sys.stdout)
    log(os.path.join(target, ".foreman"), "commit.py", code, int((time.time()-_start)*1000))
    sys.exit(code)

if not task_id:
    _out({"ok": False, "message": "Missing --task-id"}, 1)

cfg = Config(project_dir=target)
vcs = Vcs(cfg)
if not vcs.ready:
    _out({"ok": False, "message": "Not a git repository"}, 1)

if dry:
    diff = subprocess.run(["git", "diff", "--stat", "HEAD"], cwd=target, capture_output=True, text=True, timeout=10)
    staged = subprocess.run(["git", "status", "--porcelain"], cwd=target, capture_output=True, text=True, timeout=10)
    _out({"ok": True, "dry_run": True, "would_commit": bool(staged.stdout.strip()),
          "stat": diff.stdout.strip(), "changed_files": staged.stdout.strip()}, 0)

if branch:
    subprocess.run(["git", "checkout", "-B", branch], cwd=target, capture_output=True, timeout=10)

# Scope commit to task files when known
files = None
sp = os.path.join(target, ".foreman", "tasks.json")
if os.path.exists(sp):
    try:
        files = json.load(open(sp)).get(task_id, {}).get("files") or None
    except (json.JSONDecodeError, OSError):
        files = None
if not files:
    hp = os.path.join(target, ".foreman", "handoffs", f"{task_id}.developer.json")
    if os.path.exists(hp):
        try:
            files = json.load(open(hp)).get("files_changed") or None
        except (json.JSONDecodeError, OSError):
            pass

try:
    ok = vcs.commit_task(task_id, desc, files=files)
    if ok:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=target, capture_output=True, text=True, timeout=5).stdout.strip()[:12]
        # Mirror into state.json so `state task <id>` sees the sha.
        state_path = os.path.join(target, ".foreman", "tasks.json")
        if os.path.exists(state_path):
            try:
                s = json.load(open(state_path))
                if task_id in s:
                    s[task_id]["commit_sha"] = sha
                    s[task_id]["branch"] = branch or ""
                    json.dump(s, open(state_path, "w"), indent=2)
            except (json.JSONDecodeError, OSError):
                pass
        _out({"ok": True, "task_id": task_id, "sha": sha, "branch": branch or "current", "desc": desc[:80]}, 0)
    else:
        err = getattr(vcs, "last_error", "") or "Nothing to commit"
        _out({"ok": False, "message": err}, 1)
except Exception as e:
    _out({"ok": False, "message": f"Commit failed: {e}"}, 1)
