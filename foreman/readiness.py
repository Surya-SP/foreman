"""Product readiness gate: PRD + design must be real before autonomous ship.

Interactive discovery fills tasks/prd.md and tasks/design.md.
Autonomous build is blocked until ready() passes (unless forced).
"""
from __future__ import annotations

import os
import re
from typing import Any

# Markers from bootstrap seeds / empty templates
_PLACEHOLDER_MARKERS = (
    "one or two sentences",
    "feature 1",
    "feature 2",
    "personality:",
    "users:",
    "platforms:",
    "non-goals:",
    "spacing base: 8dp",
    "design loading, empty, error explicitly",
    "min tap target 48x48",
)

_MIN_PRD_CHARS = 180
_MIN_DESIGN_CHARS = 120
_MIN_PRD_BULLETS = 2


def _read(path: str) -> str:
    try:
        return open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _is_placeholder(text: str) -> bool:
    """True only if doc still looks like the empty bootstrap seed.

    Generated discover output may reuse some default phrases (spacing, a11y);
    those alone must not fail readiness when concrete content exists.
    """
    n = _norm(text)
    if not n:
        return True
    # Unfilled seed fields (colon with nothing after on same line)
    empty_fields = len(re.findall(
        r"(?m)^[-*]\s+(?:personality|users|primary|secondary|background|surface|error|font|platforms|storage)\s*:\s*$",
        text or "",
        flags=re.I,
    ))
    if empty_fields >= 3:
        return True
    if "one or two sentences describing what this app should do" in n:
        return True
    if "- feature 1" in n and "- feature 2" in n and len(n) < 500:
        return True
    # Hex color or screen/widget names with enough body ⇒ real content
    if re.search(r"#[0-9a-f]{3,8}|0x[0-9a-f]{6,8}", n):
        return False
    if re.search(r"\bscreen\b|\bwidget\b", n) and len(n) > 200:
        return False
    return len(n) < 100


def _bullet_count(text: str) -> int:
    return len(re.findall(r"(?m)^\s*[-*]\s+\S+", text or ""))


def _heading_count(text: str) -> int:
    return len(re.findall(r"(?m)^#{1,3}\s+\S+", text or ""))


def assess(project: str) -> dict[str, Any]:
    """Return readiness report. ready=True only when product docs are filled."""
    project = os.path.abspath(project)
    prd_path = os.path.join(project, "tasks", "prd.md")
    design_path = os.path.join(project, "tasks", "design.md")
    pubspec = os.path.join(project, "pubspec.yaml")

    issues: list[str] = []
    warnings: list[str] = []
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": ok, "detail": detail})
        if not ok:
            issues.append(f"{name}: {detail}" if detail else name)

    add("flutter_project", os.path.exists(pubspec), "pubspec.yaml required")
    prd = _read(prd_path)
    design = _read(design_path)
    add("prd_exists", bool(prd.strip()), "tasks/prd.md missing — run foreman init or discover")
    add("design_exists", bool(design.strip()), "tasks/design.md missing — run foreman init or discover")

    if prd.strip():
        ph = _is_placeholder(prd)
        add("prd_not_placeholder", not ph, "still looks like the empty template")
        add("prd_length", len(prd.strip()) >= _MIN_PRD_CHARS,
            f"need ≥{_MIN_PRD_CHARS} chars (have {len(prd.strip())})")
        bullets = _bullet_count(prd)
        add("prd_features", bullets >= _MIN_PRD_BULLETS,
            f"need ≥{_MIN_PRD_BULLETS} feature bullets (have {bullets})")
        if "goal" not in _norm(prd) and _heading_count(prd) < 1:
            warnings.append("prd: add a clear Goal section")

    if design.strip():
        ph = _is_placeholder(design)
        add("design_not_placeholder", not ph, "still looks like the empty template")
        add("design_length", len(design.strip()) >= _MIN_DESIGN_CHARS,
            f"need ≥{_MIN_DESIGN_CHARS} chars (have {len(design.strip())})")
        # concrete UI signal: color hex, or named screen/widget
        concrete = bool(
            re.search(r"#[0-9a-fA-F]{3,8}|0x[0-9a-fA-F]{6,8}|Color\(", design)
            or re.search(r"(?i)(screen|widget|appbar|scaffold|button|list|padding)", design)
        )
        add("design_concrete", concrete, "name screens/widgets or colors so agents can match UI")

    ready = all(c["ok"] for c in checks)
    phase = "ship" if ready else "discover"
    next_steps = []
    if not ready:
        next_steps.append("foreman discover   # interactive product brainstorm")
        next_steps.append("or edit tasks/prd.md + tasks/design.md until foreman ready passes")
    else:
        next_steps.append("foreman run   # autonomous build")

    return {
        "ok": ready,
        "ready": ready,
        "phase": phase,
        "project": project,
        "checks": checks,
        "issues": issues,
        "warnings": warnings,
        "next": next_steps,
        "prd_path": prd_path,
        "design_path": design_path,
        "prd_chars": len(prd.strip()),
        "design_chars": len(design.strip()),
    }


def write_specs(project: str, prd: str, design: str) -> dict[str, Any]:
    project = os.path.abspath(project)
    tasks = os.path.join(project, "tasks")
    os.makedirs(tasks, exist_ok=True)
    prd_path = os.path.join(tasks, "prd.md")
    design_path = os.path.join(tasks, "design.md")
    with open(prd_path, "w", encoding="utf-8") as f:
        f.write(prd.rstrip() + "\n")
    with open(design_path, "w", encoding="utf-8") as f:
        f.write(design.rstrip() + "\n")
    return {"ok": True, "prd_path": prd_path, "design_path": design_path, **assess(project)}
