#!/usr/bin/env python3
"""Product readiness gate. Exit 0 only when PRD+design are shippable.

  ready.py --project .
  ready.py --project . --json
"""
import json, os, sys, time
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
sys.path.insert(0, _ROOT)

from foreman.log import log
from foreman.readiness import assess
from foreman import ui

_start = time.time()

def _arg(name, default=None):
    return next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == name), default)

target = os.path.abspath(_arg("--project") or os.environ.get("FOREMAN_PROJECT") or ".")
report = assess(target)

if ui.is_pretty():
    ui.block(
        "Product readiness",
        command="foreman ready",
        detail=f"phase: {report['phase']} · prd {report['prd_chars']} chars · design {report['design_chars']} chars",
    )
    for c in report["checks"]:
        mark = ui.ok_mark() if c["ok"] else ui.fail_mark()
        extra = f"  {ui.dim(c['detail'])}" if c.get("detail") and not c["ok"] else ""
        print(f"  {mark} {c['check']}{extra}", file=sys.stderr)
    ui.result_line(report["ready"], "ready to ship" if report["ready"] else "still in discovery — fill PRD + design")
    for n in report.get("next") or []:
        ui.plain_line(ui.dim(f"  → {n}"))
    print(file=sys.stderr)

json.dump(report, sys.stdout, indent=2)
print()
log(os.path.join(target, ".foreman"), "ready.py", 0 if report["ready"] else 1,
    int((time.time() - _start) * 1000))
sys.exit(0 if report["ready"] else 1)
