"""Append-only audit log at .foreman/log.jsonl.

Each tool logs one line: {ts, tool, args, exit, ms}.
Bounded to last 500 lines so it never grows unbounded.
"""
from __future__ import annotations

import json
import os
import sys
import time


def log(memory_dir: str, tool: str, exit_code: int, ms: int, extra: dict | None = None) -> None:
    try:
        os.makedirs(memory_dir, exist_ok=True)
        path = os.path.join(memory_dir, "log.jsonl")
        rec = {
            "ts": round(time.time(), 3),
            "tool": tool,
            "args": sys.argv[1:],
            "exit": exit_code,
            "ms": ms,
        }
        if extra:
            rec.update(extra)
        with open(path, "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        # Rotate: keep last 500 lines
        try:
            with open(path) as f:
                lines = f.readlines()
            if len(lines) > 500:
                with open(path, "w") as f:
                    f.writelines(lines[-500:])
        except OSError:
            pass
    except OSError:
        pass  # audit log failures never break tools
