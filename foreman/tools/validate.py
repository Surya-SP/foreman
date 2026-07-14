#!/usr/bin/env python3
"""Validate: pub get -> dart fix -> format -> analyze -> test [-> coverage].

Flags:
  --lines N            Keep only the last N lines of each step's output
                       (default 40; 0 = full output)
  --coverage           Run tests with --coverage; parse lcov.info
  --min-coverage PCT   Fail if line coverage < PCT (0-100). Default 0.
  --dry-run
"""
import json, os, sys, time
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..")))

from foreman.config import Config
from foreman.validator import validate
from foreman.log import log

_start = time.time()

def _arg(name, default=None):
    return next((sys.argv[i+1] for i,a in enumerate(sys.argv) if a==name), default)

target = os.path.abspath(_arg("--project") or os.environ.get("FOREMAN_PROJECT") or ".")
lines_arg = _arg("--lines")
tail_n = int(lines_arg) if lines_arg else 40   # LINES, not characters
dry = "--dry-run" in sys.argv
coverage = "--coverage" in sys.argv
min_cov = _arg("--min-coverage"); min_cov = float(min_cov) if min_cov else 0.0

def _out(obj, code):
    from foreman import ui
    summary = obj.get("summary") or ("pass" if obj.get("ok") else "fail")
    if not obj.get("dry_run"):
        ui.validate_view(bool(obj.get("ok")), str(summary)[:120])
    json.dump(obj, sys.stdout, indent=2)
    print()
    log(os.path.join(target, ".foreman"), "validate.py", code, int((time.time()-_start)*1000))
    sys.exit(code)

if dry:
    steps = ["flutter pub get", "dart fix --apply", "dart format --set-exit-if-changed .",
             "flutter analyze", "flutter test" + (" --coverage" if coverage else "")]
    if coverage: steps.append(f"coverage >= {min_cov}%")
    _out({"ok": True, "dry_run": True, "would_run": steps}, 0)

cfg = Config(project_dir=target)
with open(os.devnull, "w") as n:
    old = sys.stderr; sys.stderr = n
    vr = validate(cfg, coverage=coverage, min_coverage=min_cov)
    sys.stderr = old

def _tail(text, n):
    """Keep only the last n lines. n<=0 means keep all."""
    lines_ = (text or "").splitlines()
    if n <= 0 or len(lines_) <= n:
        return "\n".join(lines_)
    omitted = len(lines_) - n
    return f"... ({omitted} earlier lines omitted)\n" + "\n".join(lines_[-n:])

steps = [{"name": s.name, "ok": s.ok, "skipped": s.skipped, "output": _tail(s.output, tail_n)} for s in vr.steps]
_out({"ok": vr.ok, "steps": steps, "summary": vr.summary}, 0 if vr.ok else 1)
