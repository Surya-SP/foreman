#!/usr/bin/env python3
"""Interactive product discovery → write tasks/prd.md + tasks/design.md.

Phases:
  1. Brainstorm with the user (CLI prompts) OR accept flags / JSON stdin
  2. Write polished PRD + design
  3. Run readiness gate

Usage:
  discover.py --project .                 # interactive (TTY)
  discover.py --project . --from-json     # stdin: {goal, features[], design{...}}
  discover.py --project . --goal "..." --features "a;b;c" --primary "#2196F3"
"""
from __future__ import annotations

import json, os, sys, time
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
sys.path.insert(0, _ROOT)

from foreman.log import log
from foreman.readiness import assess, write_specs
from foreman import ui

_start = time.time()

def _arg(name, default=None):
    return next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == name), default)

target = os.path.abspath(_arg("--project") or os.environ.get("FOREMAN_PROJECT") or ".")

def _out(obj, code=0):
    if ui.is_pretty() and obj.get("phase"):
        ui.block(
            "Product discovery",
            command="foreman discover",
            detail=obj.get("summary") or obj.get("message") or "",
            footer="ready" if obj.get("ready") else "not ready yet",
        )
    json.dump(obj, sys.stdout, indent=2)
    print()
    log(os.path.join(target, ".foreman"), "discover.py", code, int((time.time() - _start) * 1000))
    sys.exit(code)

def _ask(prompt: str, default: str = "") -> str:
    tip = f" [{default}]" if default else ""
    try:
        ans = input(f"{prompt}{tip}: ").strip()
    except EOFError:
        return default
    return ans or default

def _ask_list(prompt: str) -> list[str]:
    print(prompt + " (empty line to finish)", file=sys.stderr)
    items = []
    while True:
        try:
            line = input("  - ").strip()
        except EOFError:
            break
        if not line:
            break
        items.append(line)
    return items

def _build_prd(goal: str, features: list[str], users: str, platforms: str,
               non_goals: list[str], flows: list[str]) -> str:
    feat = "\n".join(f"- {f}" for f in features) or "- (add features)"
    ng = "\n".join(f"- {x}" for x in non_goals) or "- None yet"
    fl = "\n".join(f"{i+1}. {x}" for i, x in enumerate(flows)) or "1. Open app → complete primary action"
    return f"""# Product Requirements

## Goal
{goal.strip()}

## Users
{users.strip() or "General mobile users"}

## Core Features
{feat}

## User Flows
{fl}

## Constraints
- Platforms: {platforms.strip() or "iOS, Android"}
- Storage: local-first unless noted
- Non-goals:
{ng}
"""

def _build_design(app_name: str, primary: str, secondary: str, screens: list[str],
                  notes: str) -> str:
    scr = "\n\n".join(
        f"## {s.strip()}\n- Layout: clear hierarchy, 8dp spacing\n- Primary actions obvious\n- Empty / loading / error states"
        for s in screens
    ) or "## HomeScreen\n- AppBar with title\n- Primary content list\n- FAB or main CTA"
    return f"""# Design

## Brand
- App name: {app_name.strip() or "App"}
- Personality: clean, focused, trustworthy
- Users: see PRD

## Color
- Primary: {primary.strip() or "#2196F3"}
- Secondary: {secondary.strip() or "#03A9F4"}
- Background / Surface: #FFFFFF / #F5F5F5
- Error: #B00020

## Typography
- Font: system / Roboto
- Scale: display / headline / title / body / label

## Layout
- Spacing base: 8dp
- Radius: 8 cards / 12 sheets
- Min tap target: 48x48

## Screens
{scr}

## Notes
{notes.strip() or "Use shadcn_flutter (docs/UI_SPEC.md). Prefer kit components over Material."}

## States
- Design loading, empty, error explicitly on every screen.

## Accessibility
- Min tap target 48x48, WCAG AA contrast on primary text.
"""

# ── Collect input ───────────────────────────────────────────────────────────
data: dict = {}
if "--from-json" in sys.argv:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        _out({"ok": False, "message": f"invalid JSON: {e}"}, 1)
else:
    goal = _arg("--goal") or ""
    features_s = _arg("--features") or ""
    primary = _arg("--primary") or ""
    if goal and features_s:
        data = {
            "goal": goal,
            "features": [x.strip() for x in features_s.split(";") if x.strip()],
            "primary": primary or "#2196F3",
            "app_name": _arg("--name") or "App",
            "screens": [x.strip() for x in (_arg("--screens") or "HomeScreen").split(";") if x.strip()],
            "users": _arg("--users") or "General users",
            "platforms": _arg("--platforms") or "iOS, Android",
        }
    elif sys.stdin.isatty() and sys.stderr.isatty():
        print("\nForeman product discovery — answer in plain language.\n", file=sys.stderr)
        print("We will write tasks/prd.md and tasks/design.md.\n"
              "Autonomous build starts only after these pass foreman ready.\n", file=sys.stderr)
        data = {
            "app_name": _ask("App name", "MyApp"),
            "goal": _ask("What should this app do? (one clear goal)"),
            "users": _ask("Who is it for?", "General users"),
            "platforms": _ask("Platforms", "iOS, Android"),
            "features": _ask_list("List core features"),
            "flows": _ask_list("Key user flows (optional)"),
            "non_goals": _ask_list("What is out of scope? (optional)"),
            "screens": _ask_list("Screen names (e.g. HomeScreen, LoginScreen)"),
            "primary": _ask("Primary brand color (hex)", "#2196F3"),
            "secondary": _ask("Secondary color (hex)", "#03A9F4"),
            "notes": _ask("Any design notes", ""),
        }
        if not data["goal"] or len(data.get("features") or []) < 2:
            _out({
                "ok": False,
                "phase": "discover",
                "message": "Need a goal and at least 2 features. Re-run foreman discover.",
                "ready": False,
            }, 1)
    else:
        _out({
            "ok": False,
            "phase": "discover",
            "message": "Non-interactive: pass --goal and --features \"a;b;c\" or --from-json",
            "ready": False,
            "hint": "foreman discover --goal \"Todo app\" --features \"Add todo;Mark done;Delete\"",
        }, 1)

goal = str(data.get("goal") or "").strip()
features = data.get("features") or []
if isinstance(features, str):
    features = [x.strip() for x in features.split(";") if x.strip()]
if not goal or len(features) < 2:
    _out({"ok": False, "message": "goal + ≥2 features required", "ready": False}, 1)

prd = _build_prd(
    goal,
    features,
    str(data.get("users") or ""),
    str(data.get("platforms") or "iOS, Android"),
    list(data.get("non_goals") or []),
    list(data.get("flows") or []),
)
design = _build_design(
    str(data.get("app_name") or "App"),
    str(data.get("primary") or data.get("design", {}).get("primary") if isinstance(data.get("design"), dict) else "") or "#2196F3",
    str(data.get("secondary") or "#03A9F4"),
    list(data.get("screens") or ["HomeScreen"]),
    str(data.get("notes") or ""),
)

result = write_specs(target, prd, design)
result["phase"] = "ship" if result.get("ready") else "discover"
result["summary"] = (
    f"Wrote PRD ({result.get('prd_chars')} chars) + design ({result.get('design_chars')} chars)"
)
if result.get("ready"):
    result["message"] = "Product docs ready. Next: foreman run"
else:
    result["message"] = "Docs written but readiness failed — fix issues and re-check: foreman ready"
_out(result, 0 if result.get("ready") else 1)
