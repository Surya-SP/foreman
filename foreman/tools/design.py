#!/usr/bin/env python3
"""Design language workflow: run designer → human review → approve.

  design.py --project . --status
  design.py --project . --show
  design.py --project . --run [--mock]
  design.py --project . --approve
  design.py --project . --reject [reason]
"""
import json, os, sys, time
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
sys.path.insert(0, _ROOT)

from foreman.log import log
from foreman import design_gate as dg
from foreman import ui

_start = time.time()

def _arg(name, default=None):
    return next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == name), default)

target = os.path.abspath(_arg("--project") or os.environ.get("FOREMAN_PROJECT") or ".")
home = os.environ.get("FOREMAN_HOME") or _ROOT

def _out(obj, code=0):
    if ui.is_pretty() and obj.get("status") is not None:
        ui.block("Design language", command="foreman design status",
                 detail=f"status: {obj.get('status')} · approved={obj.get('approved')}")
        for n in obj.get("next") or []:
            ui.plain_line(ui.dim(f"  → {n}"))
    json.dump(obj, sys.stdout, indent=2)
    print()
    log(os.path.join(target, ".foreman"), "design.py", code, int((time.time() - _start) * 1000))
    sys.exit(code)

if "--status" in sys.argv or not any(
    a in sys.argv for a in ("--run", "--approve", "--reject", "--show")
):
    if "--run" not in sys.argv and "--approve" not in sys.argv and "--reject" not in sys.argv and "--show" not in sys.argv:
        _out(dg.assess_design(target), 0 if dg.assess_design(target).get("ok") else 1)

if "--show" in sys.argv:
    a = dg.assess_design(target)
    preview = os.path.join(target, ".foreman", "design_preview.md")
    lang = dg.design_language_text(target)
    text = ""
    if os.path.exists(preview):
        text = open(preview, encoding="utf-8", errors="replace").read()
    elif lang:
        text = lang
    elif os.path.exists(a["handoff_path"]):
        try:
            h = json.load(open(a["handoff_path"]))
            text = h.get("design_language_md") or json.dumps(h.get("mockups"), indent=2)
        except (OSError, json.JSONDecodeError):
            text = ""
    if ui.is_pretty() or True:
        print(text or "(no design preview yet — foreman design run)", file=sys.stderr)
    _out({**a, "preview_chars": len(text)}, 0)

if "--approve" in sys.argv:
    r = dg.approve(target)
    _out(r, 0 if r.get("ok") else 1)

if "--reject" in sys.argv:
    # reason = next non-flag arg after --reject
    reason = ""
    for i, a in enumerate(sys.argv):
        if a == "--reject" and i + 1 < len(sys.argv) and not sys.argv[i + 1].startswith("--"):
            reason = sys.argv[i + 1]
    r = dg.reject(target, reason)
    _out(r, 0)

if "--run" in sys.argv:
    mock = "--mock" in sys.argv
    from foreman.executor import run_designer_phase
    r = run_designer_phase(home, target, mock=mock, model=_arg("--model"), auto="--no-auto" not in sys.argv)
    _out(r, 0 if r.get("ok") or r.get("status") == "pending_review" else 1)

_out(dg.assess_design(target), 0 if dg.assess_design(target).get("ok") else 1)
