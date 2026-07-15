#!/usr/bin/env python3
"""CI prove: full gates + mock roles writing real Dart + commits + report."""
import json
import os
import subprocess
import sys
import tempfile

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _parse_json(out: str) -> dict:
    """Parse last complete JSON object from tool stdout."""
    decoder = json.JSONDecoder()
    idx = 0
    last = {}
    while True:
        i = out.find("{", idx)
        if i < 0:
            break
        try:
            obj, end = decoder.raw_decode(out, i)
            if isinstance(obj, dict):
                last = obj
            idx = end
        except json.JSONDecodeError:
            idx = i + 1
    return last


def main():
    with tempfile.TemporaryDirectory() as t:
        env = {
            **os.environ,
            "FOREMAN_HOME": _ROOT,
            "FOREMAN_PROJECT": t,
            "FOREMAN_PLAIN": "1",
            "CI": "true",
        }
        r = subprocess.run(
            [sys.executable, os.path.join(_ROOT, "foreman", "tools", "prove.py"),
             "--project", t, "--max-tasks", "12"],
            capture_output=True, text=True, env=env, timeout=300,
        )
        data = _parse_json(r.stdout or "")
        assert r.returncode == 0, f"prove failed rc={r.returncode}\n{r.stdout}\n{r.stderr}"
        assert data.get("ok") is True, data
        assert data.get("tasks_run", 0) >= 1, data
        assert os.path.exists(os.path.join(t, "lib", "main.dart"))
        assert os.path.exists(os.path.join(t, "tasks", "design_language.md"))
        assert os.path.exists(os.path.join(t, ".foreman", "PROVE_REPORT.md"))
        log = subprocess.run(
            ["git", "log", "--oneline"], cwd=t, capture_output=True, text=True
        )
        assert "foreman(" in (log.stdout or ""), log.stdout
        print("PROVE_OK", json.dumps({
            "tasks_run": data.get("tasks_run"),
            "flutter": data.get("flutter"),
            "report": data.get("report_path"),
        }))
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("PROVE_FAIL", e, file=sys.stderr)
        sys.exit(1)
