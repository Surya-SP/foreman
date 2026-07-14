#!/usr/bin/env python3
"""Prepare project for build loop (pub get + git init). Idempotent.

Usage: init.py --project /path/to/project
"""
import json, os, sys, time
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..")))

from foreman.config import Config
from foreman.bootstrap import ensure_format
from foreman.log import log

_start = time.time()

def _arg(name, default=None):
    return next((sys.argv[i+1] for i,a in enumerate(sys.argv) if a==name), default)

target = os.path.abspath(_arg("--project") or os.environ.get("FOREMAN_PROJECT") or ".")
cfg = Config(project_dir=target)

ok, msgs = ensure_format(cfg)
result = {"ok": ok, "messages": msgs}
from foreman import ui
ui.init_view(result)
json.dump(result, sys.stdout, indent=2)
print()
log(os.path.join(target, ".foreman"), "init.py", 0 if ok else 1, int((time.time()-_start)*1000))
sys.exit(0 if ok else 1)
