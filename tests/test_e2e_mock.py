#!/usr/bin/env python3
"""Golden e2e: discover → ready → execute --mock (no live LLM)."""
import json
import os
import subprocess
import sys
import tempfile

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOOLS = os.path.join(_ROOT, "foreman", "tools")
BIN = os.path.join(_ROOT, "bin", "foreman")


def run(cmd, project, **kw):
    env = {**os.environ, "FOREMAN_HOME": _ROOT, "FOREMAN_PROJECT": project, "FOREMAN_PLAIN": "1"}
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=project, timeout=120, **kw)
    return r.returncode, r.stdout, r.stderr


def main():
    with tempfile.TemporaryDirectory() as t:
        open(os.path.join(t, "pubspec.yaml"), "w").write(
            "name: golden\nversion: 0.0.1\ndependencies:\n  flutter:\n    sdk: flutter\n"
        )
        os.makedirs(os.path.join(t, "lib"), exist_ok=True)
        open(os.path.join(t, "lib", "main.dart"), "w").write("void main() {}\n")
        os.makedirs(os.path.join(t, "test"), exist_ok=True)
        # git for commit path
        subprocess.run(["git", "init"], cwd=t, capture_output=True)
        subprocess.run(["git", "config", "user.email", "ci@test"], cwd=t, capture_output=True)
        subprocess.run(["git", "config", "user.name", "ci"], cwd=t, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=t, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=t, capture_output=True)

        # discover
        rc, out, err = run([
            sys.executable, os.path.join(TOOLS, "discover.py"),
            "--project", t,
            "--goal", "Golden todo app for CI verification of the ship pipeline",
            "--features", "Add todo;Mark complete;Delete todo",
            "--name", "GoldenTodos",
            "--screens", "HomeScreen",
            "--primary", "#2196F3",
        ], t)
        assert rc == 0, f"discover failed: {out} {err}"
        d = json.loads(out)
        assert d.get("ready") is True, d

        # ready
        rc, out, _ = run([sys.executable, os.path.join(TOOLS, "ready.py"), "--project", t], t)
        assert rc == 0, out

        # execute mock (Python loop + mock handoffs; no opencode)
        rc, out, err = run([
            sys.executable, os.path.join(TOOLS, "execute.py"),
            "--project", t, "--template", "todo", "--mock", "--max-tasks", "12",
        ], t)
        assert rc == 0, f"execute mock failed rc={rc}\n{out}\n{err}"
        result = json.loads(out)
        assert result.get("ok") is True, result
        assert result.get("tasks_run", 0) >= 1, result

        # all done or no ready left
        rc, out, _ = run([sys.executable, os.path.join(TOOLS, "state.py"), "--project", t, "--ready"], t)
        ready = json.loads(out)
        assert ready.get("count", 0) == 0, ready

        print("GOLDEN_E2E_OK", json.dumps({
            "tasks_run": result.get("tasks_run"),
            "phase": result.get("phase"),
        }))
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("GOLDEN_E2E_FAIL", e, file=sys.stderr)
        sys.exit(1)
