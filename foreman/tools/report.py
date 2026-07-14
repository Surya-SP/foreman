#!/usr/bin/env python3
"""Write/print a field-report draft from local state.

  report.py --project .
  report.py --project . --write          # → docs/field_report_DRAFT.md or .foreman/
  report.py --project . --live           # mark as live attempt (still needs human fill)
"""
import json, os, sys, time
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
sys.path.insert(0, _ROOT)

from foreman.log import log
from foreman.report import build_report, render_markdown
from foreman import ui

_start = time.time()

def _arg(name, default=None):
    return next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == name), default)

target = os.path.abspath(_arg("--project") or os.environ.get("FOREMAN_PROJECT") or ".")
home = os.environ.get("FOREMAN_HOME") or _ROOT
live = "--live" in sys.argv
do_write = "--write" in sys.argv

data = build_report(target, home, live=live)
md = render_markdown(data)

if ui.is_pretty():
    ui.block(
        "Field report draft",
        command="foreman report" + (" --write" if do_write else ""),
        detail=("LIVE flag set" if live else "auto-draft — not live-ship proof"),
    )

path = None
if do_write:
    out_dir = os.path.join(target, ".foreman")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "field_report_DRAFT.md")
    open(path, "w", encoding="utf-8").write(md)
    # also copy template reminder
    if ui.is_pretty():
        ui.result_line(True, f"wrote {path}")
        ui.plain_line(ui.dim("  complete human sections after a real ship"))

print(md if not do_write else json.dumps({**data, "path": path, "markdown_bytes": len(md)}, indent=2))
if do_write:
    print()
log(os.path.join(target, ".foreman"), "report.py", 0, int((time.time() - _start) * 1000))
sys.exit(0)
