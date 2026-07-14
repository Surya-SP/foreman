"""Append-only audit log at .foreman/log.jsonl.

Each tool logs one line: {ts, tool, args, exit, ms}.
Bounded to last 500 lines so it never grows unbounded.
Also: metrics.jsonl for handoff success rates.
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
        try:
            with open(path) as f:
                lines = f.readlines()
            if len(lines) > 500:
                with open(path, "w") as f:
                    f.writelines(lines[-500:])
        except OSError:
            pass
    except OSError:
        pass


def metric(memory_dir: str, kind: str, **fields) -> None:
    """Record a structured metric (handoff_ok, handoff_miss, etc.)."""
    try:
        os.makedirs(memory_dir, exist_ok=True)
        path = os.path.join(memory_dir, "metrics.jsonl")
        rec = {"ts": round(time.time(), 3), "kind": kind, **fields}
        with open(path, "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        try:
            with open(path) as f:
                lines = f.readlines()
            if len(lines) > 1000:
                with open(path, "w") as f:
                    f.writelines(lines[-1000:])
        except OSError:
            pass
    except OSError:
        pass


def metrics_summary(memory_dir: str) -> dict:
    path = os.path.join(memory_dir, "metrics.jsonl")
    if not os.path.exists(path):
        return {"ok": True, "total": 0, "by_kind": {}}
    by: dict[str, int] = {}
    n = 0
    try:
        for line in open(path):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            n += 1
            k = r.get("kind") or "?"
            by[k] = by.get(k, 0) + 1
    except OSError:
        return {"ok": False, "total": 0, "by_kind": {}}
    handoff_ok = by.get("handoff_ok", 0) + by.get("handoff_self", 0)
    handoff_miss = by.get("handoff_miss", 0)
    denom = handoff_ok + handoff_miss
    rate = round(handoff_ok / denom, 3) if denom else None
    return {
        "ok": True,
        "total": n,
        "by_kind": by,
        "handoff_success_rate": rate,
        "handoff_ok": handoff_ok,
        "handoff_miss": handoff_miss,
    }
