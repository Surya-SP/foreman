#!/usr/bin/env python3
"""Discard uncommitted changes.

Flags:
  --dry-run   Show what would be discarded without executing
"""
import json, os, subprocess, sys, time
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..")))

from foreman.log import log

_start = time.time()

def _arg(name, default=None):
    return next((sys.argv[i+1] for i,a in enumerate(sys.argv) if a==name), default)

target = os.path.abspath(_arg("--project") or os.environ.get("FOREMAN_PROJECT") or ".")
dry = "--dry-run" in sys.argv

def _out(obj, code):
    json.dump(obj, sys.stdout)
    log(os.path.join(target, ".foreman"), "rollback.py", code, int((time.time()-_start)*1000))
    sys.exit(code)

if not os.path.isdir(os.path.join(target, ".git")):
    _out({"ok": False, "message": "Not a git repository"}, 1)

if dry:
    r = subprocess.run(["git", "status", "--porcelain"], cwd=target, capture_output=True, text=True, timeout=10)
    _out({"ok": True, "dry_run": True, "would_discard": r.stdout.strip().splitlines()}, 0)

try:
    subprocess.run(["git", "checkout", "--", "."], cwd=target, capture_output=True, timeout=10)
    subprocess.run(["git", "clean", "-fd"], cwd=target, capture_output=True, timeout=10)
    _out({"ok": True, "message": "Uncommitted changes discarded"}, 0)
except Exception as e:
    _out({"ok": False, "message": f"Rollback failed: {e}"}, 1)
