#!/usr/bin/env python3
"""Harvest `yagni:` markers from the codebase — the deferred-simplification ledger.

Each `// yagni: <reason>` (or `# yagni: ...` for Python) is a
deliberate shortcut. This tool lists them so "later" doesn't become "never".

Usage:
  foreman debt [--path lib/] [--lines N]
"""
import json, os, re, sys, time
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..")))

from foreman.log import log

_start = time.time()

def _arg(name, default=None):
    return next((sys.argv[i+1] for i,a in enumerate(sys.argv) if a==name), default)

target = os.path.abspath(_arg("--project") or os.environ.get("FOREMAN_PROJECT") or ".")
path_filter = _arg("--path")
lines_arg = _arg("--lines")
max_entries = int(lines_arg) if lines_arg else 0

def _out(obj, code=0):
    json.dump(obj, sys.stdout, indent=2)
    log(os.path.join(target, ".foreman"), "debt.py", code, int((time.time()-_start)*1000))
    sys.exit(code)

# yagni: `[/#*]+ *yagni: ...` covers // and # comment styles
_MARKER = re.compile(r"(?://|#|\*)\s*yagni:\s*(.+?)\s*$")

# Skip build/cache dirs, but scan any text source file.
_SKIP_DIRS = {".git", ".dart_tool", "build", "node_modules", ".foreman",
              "__pycache__", ".venv", "venv", "coverage", ".gradle"}
_SOURCE_EXTS = (".dart", ".py", ".js", ".ts", ".jsx", ".tsx",
                ".java", ".kt", ".swift", ".go", ".rs", ".rb")

base = os.path.join(target, path_filter) if path_filter else target
if not os.path.isdir(base):
    _out({"ok": False, "message": f"Path not found: {base}"}, 1)

entries = []
for root, dirs, names in os.walk(base):
    dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
    for n in names:
        if not n.endswith(_SOURCE_EXTS): continue
        p = os.path.join(root, n)
        rel = os.path.relpath(p, target)
        try:
            for i, line in enumerate(open(p, encoding="utf-8"), 1):
                m = _MARKER.search(line)
                if m:
                    entries.append({"file": rel, "line": i, "note": m.group(1)})
        except (OSError, UnicodeDecodeError):
            continue

if max_entries and len(entries) > max_entries:
    entries = entries[:max_entries]

_out({"ok": True, "count": len(entries), "entries": entries,
      "hint": "Each entry is a deferred simplification. Revisit or delete when the assumption changes."})
