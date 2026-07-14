#!/usr/bin/env python3
"""Autonomous executor: OpenCode role agents driven by Python loop.

  execute.py --project . [--template todo] [--model provider/model]
  execute.py --project . --dry-run
  execute.py --project . --mock          # CI golden path (no LLM)
  execute.py --project . --task-id t1    # single task
"""
import json, os, sys, time
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
sys.path.insert(0, _ROOT)

from foreman.log import log
from foreman.executor import execute_project, execute_task
from foreman import ui

_start = time.time()

def _arg(name, default=None):
    return next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == name), default)

target = os.path.abspath(_arg("--project") or os.environ.get("FOREMAN_PROJECT") or ".")
home = os.environ.get("FOREMAN_HOME") or _ROOT
model = _arg("--model")
template = _arg("--template")
task_id = _arg("--task-id")
dry = "--dry-run" in sys.argv
mock = "--mock" in sys.argv
force = "--force" in sys.argv or "--skip-ready" in sys.argv
no_auto = "--no-auto" in sys.argv
max_tasks = _arg("--max-tasks")
max_tasks = int(max_tasks) if max_tasks and str(max_tasks).isdigit() else 50

if ui.is_pretty():
    ui.block(
        "Autonomous execute (OpenCode roles)",
        command="foreman execute" + (" --mock" if mock else ""),
        detail=f"project: {target}\nmodel: {model or 'default'} · mock={mock}",
    )

if task_id:
    result = execute_task(
        home, target, task_id, model=model, auto=not no_auto, dry=dry, mock=mock,
    )
else:
    result = execute_project(
        home, target, model=model, template=template, max_tasks=max_tasks,
        auto=not no_auto, dry=dry, mock=mock, force=force,
    )

if ui.is_pretty():
    ui.result_line(bool(result.get("ok")), result.get("message") or result.get("phase") or "")
    print(file=sys.stderr)

json.dump(result, sys.stdout, indent=2)
print()
code = 0 if result.get("ok") else 1
log(os.path.join(target, ".foreman"), "execute.py", code, int((time.time() - _start) * 1000))
sys.exit(code)
