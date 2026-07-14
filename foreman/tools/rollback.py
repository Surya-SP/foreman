#!/usr/bin/env python3
"""Safe rollback of uncommitted work for a task (or last foreman commit).

Default: restore only files listed for the task (state.files / architect handoff).
Never runs git clean -fd unless --hard --i-understand-destructive.

Usage:
  rollback.py --project . --task-id t1
  rollback.py --project . --task-id t1 --dry-run
  rollback.py --project . --last-commit          # reset soft? no — checkout files from HEAD for dirty only
  rollback.py --project . --hard --i-understand-destructive
"""
import json, os, subprocess, sys, time
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..")))

from foreman.log import log

_start = time.time()

def _arg(name, default=None):
    return next((sys.argv[i+1] for i,a in enumerate(sys.argv) if a==name), default)

target = os.path.abspath(_arg("--project") or os.environ.get("FOREMAN_PROJECT") or ".")
task_id = _arg("--task-id") or ""
dry = "--dry-run" in sys.argv
hard = "--hard" in sys.argv and "--i-understand-destructive" in sys.argv

def _out(obj, code):
    json.dump(obj, sys.stdout, indent=2)
    print()
    log(os.path.join(target, ".foreman"), "rollback.py", code, int((time.time()-_start)*1000))
    sys.exit(code)

if not os.path.isdir(os.path.join(target, ".git")):
    _out({"ok": False, "message": "Not a git repository"}, 1)

def _task_files(tid: str) -> list[str]:
    files = []
    sp = os.path.join(target, ".foreman", "tasks.json")
    if os.path.exists(sp):
        try:
            t = json.load(open(sp)).get(tid) or {}
            files = list(t.get("files") or [])
        except (json.JSONDecodeError, OSError):
            pass
    hp = os.path.join(target, ".foreman", "handoffs", f"{tid}.architect.json")
    if not files and os.path.exists(hp):
        try:
            arch = json.load(open(hp))
            for f in arch.get("files") or []:
                p = f.get("path") if isinstance(f, dict) else f
                if p:
                    files.append(p)
        except (json.JSONDecodeError, OSError):
            pass
    # also developer handoff
    dp = os.path.join(target, ".foreman", "handoffs", f"{tid}.developer.json")
    if os.path.exists(dp):
        try:
            dev = json.load(open(dp))
            for p in dev.get("files_changed") or []:
                if p and p not in files:
                    files.append(p)
        except (json.JSONDecodeError, OSError):
            pass
    return files

if hard:
    r = subprocess.run(["git", "status", "--porcelain"], cwd=target, capture_output=True, text=True, timeout=10)
    lines = r.stdout.strip().splitlines()
    if dry:
        _out({"ok": True, "dry_run": True, "mode": "hard", "would_discard": lines,
              "warning": "DESTRUCTIVE: checkout . + clean -fd"}, 0)
    subprocess.run(["git", "checkout", "--", "."], cwd=target, capture_output=True, timeout=10)
    subprocess.run(["git", "clean", "-fd"], cwd=target, capture_output=True, timeout=10)
    _out({"ok": True, "message": "Hard rollback: all uncommitted changes discarded", "mode": "hard"}, 0)

# Safe default: task-scoped restore
if not task_id:
    _out({
        "ok": False,
        "message": "Safe rollback requires --task-id (or pass --hard --i-understand-destructive)",
        "hint": "foreman rollback --task-id t1",
    }, 1)

files = _task_files(task_id)
if not files:
    # Only restore modified tracked files that look like dart under lib/test
    r = subprocess.run(["git", "status", "--porcelain"], cwd=target, capture_output=True, text=True, timeout=10)
    for line in r.stdout.splitlines():
        path = line[3:].strip() if len(line) > 3 else ""
        if path.startswith("lib/") or path.startswith("test/") or path.startswith("integration_test/"):
            files.append(path)

if dry:
    _out({"ok": True, "dry_run": True, "mode": "scoped", "task_id": task_id, "would_restore": files}, 0)

restored = []
for f in files:
    p = os.path.join(target, f)
    # checkout from HEAD if tracked
    r = subprocess.run(["git", "checkout", "HEAD", "--", f], cwd=target, capture_output=True, text=True, timeout=10)
    if r.returncode == 0:
        restored.append(f)
    elif os.path.exists(p) and not os.path.isdir(p):
        # untracked file created by agent — remove only if under lib/test
        if f.startswith("lib/") or f.startswith("test/") or f.startswith("integration_test/"):
            try:
                os.remove(p)
                restored.append(f + " (removed untracked)")
            except OSError:
                pass

_out({
    "ok": True,
    "mode": "scoped",
    "task_id": task_id,
    "restored": restored,
    "message": f"Scoped rollback for {task_id}: {len(restored)} path(s)",
}, 0)
