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

def _hash(p):
    try: return hashlib.md5(open(p, "rb").read()).hexdigest()
    except OSError: return ""

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
cache_path = os.path.join(target, ".foreman", ".plan_cache.json")
os.makedirs(os.path.dirname(cache_path), exist_ok=True)

cached = {}
if not no_cache and os.path.exists(cache_path):
    try: cached = json.load(open(cache_path))
    except (json.JSONDecodeError, OSError): pass

key = f"{_hash(prd_path)}:{_hash(design_path)}:{section or ''}:{lines or ''}"
if not no_cache and key in cached:
    _out(cached[key])

result = {"ok": True, "project_dir": target,
          "prd": _read(prd_path, "PRD"),
          "design": _read(design_path, "design.md"),
          "_cache_key": key}
cached[key] = result
try: json.dump(cached, open(cache_path, "w"), indent=2)
except OSError: pass
_out(result)
