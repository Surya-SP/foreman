"""Minimal project bootstrap: pub get + optional git init + spec seeds."""
from __future__ import annotations

import os

from .config import Config
from .proc import run_command, which

_PRD_SEED = """# Product Requirements

## Goal
One or two sentences describing what this app should do.

## Core Features
- Feature 1
- Feature 2

## User Flows
1. ...

## Constraints
- Platforms:
- Storage:
- Non-goals:
"""

_DESIGN_SEED = """# Design

## Brand
- Personality:
- Users:

## Color
- Primary:
- Secondary:
- Background / Surface:
- Error:

## Typography
- Font:
- Scale: display / headline / title / body / label

## Layout
- Spacing base: 8dp
- Radius: 8 cards / 12 sheets

## States
- Design loading, empty, error explicitly.

## Accessibility
- Min tap target 48x48, WCAG AA contrast.
"""


def ensure_format(config: Config) -> tuple[bool, list[str]]:
    """Prepare the project for a build loop. Returns (ok, messages)."""
    msgs: list[str] = []
    project = config.project_path

    if not os.path.isdir(project):
        return False, [f"Project path does not exist: {project}"]

    pubspec = os.path.join(project, "pubspec.yaml")
    if config.framework == "flutter" and not os.path.exists(pubspec):
        return False, [f"No pubspec.yaml in {project}. Run `flutter create .` first."]

    # Seed spec files if missing (skeletons; user fills them in).
    tasks_dir = os.path.join(project, "tasks")
    os.makedirs(tasks_dir, exist_ok=True)
    for name, seed in [("prd.md", _PRD_SEED), ("design.md", _DESIGN_SEED)]:
        p = os.path.join(tasks_dir, name)
        if not os.path.exists(p):
            with open(p, "w") as f:
                f.write(seed)
            msgs.append(f"seeded tasks/{name}")

    if config.framework == "flutter" and which("flutter"):
        res = run_command(["flutter", "pub", "get"], cwd=project, timeout=300, heartbeat=False)
        msgs.append("pub get: " + ("ok" if res.ok else "failed"))
        if not res.ok:
            return False, msgs + [res.combined[-500:]]

    if which("git") and not os.path.isdir(os.path.join(project, ".git")):
        run_command(["git", "init"], cwd=project, timeout=10, heartbeat=False)
        run_command(["git", "add", "-A"], cwd=project, timeout=30, heartbeat=False)
        run_command(["git", "commit", "-m", "foreman: baseline"], cwd=project, timeout=30, heartbeat=False)
        msgs.append("git: initialised")

    return True, msgs
