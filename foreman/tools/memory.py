#!/usr/bin/env python3
"""Memory CLI: graph, decisions, retrieve, rg, cache, rebuild.

  memory.py --project . --stats
  memory.py --project . --retrieve --role architect --task-id t1 [--query "..."]
  memory.py --project . --decisions [--task-id t1]
  memory.py --project . --rebuild
  memory.py --project . --rg PATTERN [--glob "*.dart"]
  memory.py --project . --cache-clear
  memory.py --project . --rg-status
"""
import json, os, sys, time
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
sys.path.insert(0, _ROOT)

from foreman.log import log
from foreman import memory as mem

_start = time.time()

def _arg(name, default=None):
    return next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == name), default)

target = os.path.abspath(_arg("--project") or os.environ.get("FOREMAN_PROJECT") or ".")

def _out(obj, code=0):
    json.dump(obj, sys.stdout, indent=2)
    log(os.path.join(target, ".foreman"), "memory.py", code, int((time.time() - _start) * 1000))
    sys.exit(code)

if "--rg-status" in sys.argv:
    _out(mem.ensure_rg())

if "--cache-clear" in sys.argv:
    _out(mem.tool_cache_clear(target))

if "--rebuild" in sys.argv:
    _out(mem.rebuild_from_handoffs(target))

if "--decisions" in sys.argv:
    tid = _arg("--task-id")
    lim = _arg("--limit")
    lim = int(lim) if lim and str(lim).isdigit() else 30
    _out(mem.list_decisions(target, task_id=tid, limit=lim))

if "--retrieve" in sys.argv:
    role = _arg("--role") or ""
    tid = _arg("--task-id") or ""
    query = _arg("--query") or ""
    lim = _arg("--limit")
    lim = int(lim) if lim and str(lim).isdigit() else 12
    files_raw = _arg("--files") or ""
    files = [f.strip() for f in files_raw.split(",") if f.strip()]
    r = mem.retrieve(target, role=role, task_id=tid, query=query, files=files, limit=lim)
    r["block"] = mem.format_memory_block(r)
    _out(r)

if "--rg" in sys.argv:
    pattern = _arg("--rg") or _arg("--pattern") or ""
    if not pattern or str(pattern).startswith("--"):
        pattern = _arg("--pattern") or ""
    glob = _arg("--glob")
    _out(mem.rg_search(target, pattern, glob=glob))

# default / --stats
_out(mem.stats(target))
