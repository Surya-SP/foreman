"""SDK detection — minimal replacement for the old resources.py."""
from __future__ import annotations

import re

from .proc import run_command, which

_SEMVER = re.compile(r"(\d+\.\d+\.\d+(?:[-+][\w.]+)?)")
_CACHE: dict[str, str] | None = None


def detect_sdk() -> dict[str, str]:
    """Return {flutter, dart} versions; empty when undetectable. Cached."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    out: dict[str, str] = {}
    if which("flutter"):
        res = run_command(["flutter", "--version"], timeout=30, heartbeat=False)
        m = re.search(r"Flutter\s+" + _SEMVER.pattern, res.combined)
        if m:
            out["flutter"] = m.group(1)
        md = re.search(r"Dart\s+" + _SEMVER.pattern, res.combined)
        if md:
            out["dart"] = md.group(1)
    if "dart" not in out and which("dart"):
        res = run_command(["dart", "--version"], timeout=20, heartbeat=False)
        m = _SEMVER.search(res.combined)
        if m:
            out["dart"] = m.group(1)
    _CACHE = out
    return out
