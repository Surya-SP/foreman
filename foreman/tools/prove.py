#!/usr/bin/env python3
"""Deterministic ship proof: full gates + mock roles that write real Dart.

Proves the control plane can take a project from empty → design language →
all tasks done → real git commits → field report. Uses no live LLM.

When Flutter is on PATH, runs real validate (analyze/test) on generated code.
When Flutter is missing (typical CI), skips validate but still proves DAG/handoff/commit.

Usage:
  prove.py --project /tmp/app
  prove.py --project . --max-tasks 12
"""
import json, os, shutil, subprocess, sys, time
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
sys.path.insert(0, _ROOT)

from foreman.log import log
from foreman.executor import execute_project
from foreman.report import build_report, render_markdown
from foreman.readiness import write_specs
from foreman import ui

_start = time.time()

def _arg(name, default=None):
    return next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == name), default)

target = os.path.abspath(_arg("--project") or os.environ.get("FOREMAN_PROJECT") or "")
home = os.environ.get("FOREMAN_HOME") or _ROOT
max_tasks = _arg("--max-tasks")
max_tasks = int(max_tasks) if max_tasks and str(max_tasks).isdigit() else 12

# Never pollute the Foreman source tree
if not target or os.path.abspath(target) == os.path.abspath(home) or os.path.abspath(target) == os.path.abspath(_ROOT):
    import tempfile
    target = tempfile.mkdtemp(prefix="foreman-prove-")
    print(json.dumps({"note": "prove uses temp project (refused FOREMAN_HOME/cwd)", "project": target}), file=sys.stderr)


def _ensure_flutter_project(path: str) -> None:
    os.makedirs(path, exist_ok=True)
    pub = os.path.join(path, "pubspec.yaml")
    if not os.path.exists(pub):
        open(pub, "w").write(
            "name: prove_app\nversion: 0.0.1\npublish_to: none\n"
            "environment:\n  sdk: '>=3.0.0 <4.0.0'\n"
            "dependencies:\n  flutter:\n    sdk: flutter\n"
            "dev_dependencies:\n  flutter_test:\n    sdk: flutter\n"
            "flutter:\n  uses-material-design: true\n"
        )
    os.makedirs(os.path.join(path, "lib"), exist_ok=True)
    os.makedirs(os.path.join(path, "test"), exist_ok=True)
    if not os.path.isdir(os.path.join(path, ".git")):
        subprocess.run(["git", "init"], cwd=path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "prove@foreman.local"], cwd=path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "foreman-prove"], cwd=path, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "prove: baseline"], cwd=path, capture_output=True)


def _seed_product(path: str) -> None:
    write_specs(
        path,
        "# Product Requirements\n\n## Goal\n"
        "A minimal todo app for proving the Foreman ship pipeline end-to-end without a live LLM.\n\n"
        "## Core Features\n- Add a todo with a title\n- Mark a todo complete\n- Delete a todo\n\n"
        "## Users\nDevelopers verifying Foreman\n\n"
        "## Constraints\n- Platforms: iOS, Android\n- Storage: in-memory repository for prove\n",
        "# Design\n\n## Brand\n- App name: Todos\n- Personality: calm utility\n\n"
        "## Color\n- Primary: #2196F3\n- On primary: #FFFFFF\n\n"
        "## HomeScreen\n- AppBar title Todos\n- List of todos with checkbox\n"
        "- FAB add (primary)\n- Empty state: No todos yet\n",
    )


if ui.is_pretty():
    ui.block(
        "Prove ship pipeline (deterministic)",
        command="foreman prove",
        detail=f"project: {target}\nflutter: {bool(shutil.which('flutter'))}",
        footer="mock OpenCode roles + real code + optional flutter analyze",
    )

_ensure_flutter_project(target)
_seed_product(target)

result = execute_project(
    home, target,
    template="todo",
    max_tasks=max_tasks,
    mock=True,
    force=False,
    auto=False,
)

# Design-language token check on final tree
from foreman.design_check import check_design_language
dchk = check_design_language(target)

# Field report draft
report = build_report(target, home, live=False)
report["prove"] = True
report["execute"] = {
    "ok": result.get("ok"),
    "tasks_run": result.get("tasks_run"),
    "cost_proxy": result.get("cost_proxy"),
}
report["design_check"] = dchk
md = render_markdown(report)
# Append prove-specific outcomes
md += "\n## Prove outcomes (auto)\n\n"
md += f"- execute.ok: **{result.get('ok')}**\n"
md += f"- tasks_run: **{result.get('tasks_run')}**\n"
md += f"- design_check.ok: **{dchk.get('ok')}** (skipped={dchk.get('skipped')})\n"
md += f"- flutter_on_path: **{bool(shutil.which('flutter'))}**\n"
md += "\n_This is a deterministic control-plane proof, not a live-LLM field report._\n"

out_dir = os.path.join(target, ".foreman")
os.makedirs(out_dir, exist_ok=True)
report_path = os.path.join(out_dir, "PROVE_REPORT.md")
open(report_path, "w", encoding="utf-8").write(md)

ok = bool(result.get("ok")) and (dchk.get("ok") or dchk.get("skipped"))
# require at least one task and design language file
ok = ok and int(result.get("tasks_run") or 0) >= 1
ok = ok and os.path.exists(os.path.join(target, "tasks", "design_language.md"))
ok = ok and os.path.exists(os.path.join(target, "lib", "main.dart"))

payload = {
    "ok": ok,
    "mode": "prove",
    "project": target,
    "tasks_run": result.get("tasks_run"),
    "execute": result,
    "design_check": dchk,
    "report_path": report_path,
    "flutter": bool(shutil.which("flutter")),
    "message": "PROVE_OK" if ok else "PROVE_FAIL",
    "hint": "Live LLM ship still needs: foreman run (no --mock) + human field report",
}

if ui.is_pretty():
    ui.result_line(ok, payload["message"] + f" · report {report_path}")

json.dump(payload, sys.stdout, indent=2)
print()
log(out_dir, "prove.py", 0 if ok else 1, int((time.time() - _start) * 1000))
sys.exit(0 if ok else 1)
