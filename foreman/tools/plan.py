#!/usr/bin/env python3
"""Read PRD + design.md as structured JSON. MD5-cached.

Flags:
  --section NAME   Filter to matching design.md section
  --lines N        Truncate each section to N lines
  --no-cache       Bypass cache
"""
import hashlib, json, os, re, sys, time
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..")))

from foreman.log import log
from foreman import memory as mem

_start = time.time()

def _arg(name, default=None):
    return next((sys.argv[i+1] for i,a in enumerate(sys.argv) if a==name), default)

target = os.path.abspath(_arg("--project") or os.environ.get("FOREMAN_PROJECT") or ".")
section = _arg("--section")
lines = _arg("--lines")
lines = int(lines) if lines else None
no_cache = "--no-cache" in sys.argv

def _out(obj, code=0):
    json.dump(obj, sys.stdout, indent=2)
    log(os.path.join(target, ".foreman"), "plan.py", code, int((time.time()-_start)*1000))
    sys.exit(code)

def _read(path, label):
    if not os.path.exists(path):
        return {"path": path, "exists": False, "error": f"{label} not found"}
    content = open(path).read()
    sections, head, buf = [], None, []
    for line in content.splitlines():
        m = re.match(r"^(#{1,3})\s+(.+)$", line)
        if m:
            if head: sections.append({"heading": head, "body": "\n".join(buf)})
            head, buf = m.group(2).strip(), []
        else:
            buf.append(line)
    if head: sections.append({"heading": head, "body": "\n".join(buf)})
    if section:
        sections = [s for s in sections if section.lower() in s["heading"].lower()]
    if lines:
        for s in sections:
            body_lines = s["body"].splitlines()
            if len(body_lines) > lines:
                s["body"] = "\n".join(body_lines[:lines]) + f"\n... ({len(body_lines)} total)"
                s["truncated"] = True
    return {"path": path, "exists": True, "sections": sections, "total_lines": len(content.splitlines())}

prd_path = os.path.join(target, "tasks", "prd.md")
design_path = os.path.join(target, "tasks", "design.md")
watch = [prd_path, design_path]
key_parts = [section or "", str(lines or "")]

if not no_cache:
    hit = mem.tool_cache_get(target, "plan", key_parts, watch)
    if hit is not None:
        hit = dict(hit)
        hit["_cache"] = "hit"
        _out(hit)

result = {"ok": True, "project_dir": target,
          "prd": _read(prd_path, "PRD"),
          "design": _read(design_path, "design.md"),
          "_cache": "miss"}
if not no_cache:
    try:
        mem.tool_cache_set(target, "plan", key_parts, watch, result)
    except OSError:
        pass
_out(result)
