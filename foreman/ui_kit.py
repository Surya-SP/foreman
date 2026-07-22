"""Seed shadcn_flutter UI kit docs into user Flutter projects.

Teaches OpenCode agents the library before they write UI (anti-hallucination).
"""
from __future__ import annotations

import os
import shutil
import urllib.error
import urllib.request
from typing import Any

from .proc import run_command, which

_HERE = os.path.dirname(os.path.abspath(__file__))
_ASSETS = os.path.join(_HERE, "assets")

LLMS_URL = "https://sunarya-thito.github.io/shadcn_flutter/llms-full.txt"
UI_SPEC_NAME = "UI_SPEC.md"
KIT_NAME = "shadcn_flutter_kit.md"
LLMS_NAME = "shadcn_flutter_llms.txt"


def _assets_dir() -> str:
    return _ASSETS


def _cache_dir() -> str:
    xdg = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    d = os.path.join(xdg, "foreman")
    os.makedirs(d, exist_ok=True)
    return d


def _copy_asset(name: str, dest: str) -> bool:
    src = os.path.join(_assets_dir(), name)
    if not os.path.isfile(src):
        return False
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copyfile(src, dest)
    return True


def _ensure_llms(project_docs: str, msgs: list[str], *, fetch: bool = True) -> None:
    """Place full AI reference under docs/. Prefer cache; optionally download."""
    dest = os.path.join(project_docs, LLMS_NAME)
    if os.path.isfile(dest) and os.path.getsize(dest) > 1000:
        return
    cache = os.path.join(_cache_dir(), LLMS_NAME)
    if os.path.isfile(cache) and os.path.getsize(cache) > 1000:
        shutil.copyfile(cache, dest)
        msgs.append(f"seeded docs/{LLMS_NAME} (from cache)")
        return
    if not fetch:
        msgs.append(f"docs/{LLMS_NAME} missing — agents use kit only until fetched")
        return
    try:
        req = urllib.request.Request(LLMS_URL, headers={"User-Agent": "foreman/ui-kit"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        if len(data) < 1000:
            msgs.append("llms download too small — skipped")
            return
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        open(cache, "wb").write(data)
        shutil.copyfile(cache, dest)
        msgs.append(f"seeded docs/{LLMS_NAME} ({len(data) // 1024}KB)")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        msgs.append(f"llms download skipped: {e}")


def _pubspec_has_dep(project: str, name: str) -> bool:
    pub = os.path.join(project, "pubspec.yaml")
    if not os.path.isfile(pub):
        return False
    try:
        text = open(pub, encoding="utf-8", errors="replace").read()
    except OSError:
        return False
    # crude but enough for deps block presence
    return f"{name}:" in text or f"  {name}:" in text


def ensure_shadcn_package(project: str, msgs: list[str]) -> None:
    """Add shadcn_flutter via flutter pub add when Flutter is available."""
    if _pubspec_has_dep(project, "shadcn_flutter"):
        return
    if not which("flutter"):
        msgs.append("shadcn_flutter: flutter not on PATH — add manually: flutter pub add shadcn_flutter")
        return
    res = run_command(
        ["flutter", "pub", "add", "shadcn_flutter"],
        cwd=project, timeout=300, heartbeat=False,
    )
    if res.ok:
        msgs.append("pub add shadcn_flutter: ok")
    else:
        msgs.append("pub add shadcn_flutter: failed — " + (res.combined or "")[-200:])


def seed_ui_kit(project: str, *, fetch_llms: bool = True, add_package: bool = True) -> dict[str, Any]:
    """Idempotently seed docs/UI_SPEC + kit + optional full llms + package."""
    project = os.path.abspath(project)
    msgs: list[str] = []
    docs = os.path.join(project, "docs")
    os.makedirs(docs, exist_ok=True)

    for asset, rel in (
        (UI_SPEC_NAME, os.path.join("docs", UI_SPEC_NAME)),
        (KIT_NAME, os.path.join("docs", KIT_NAME)),
    ):
        dest = os.path.join(project, rel)
        if not os.path.exists(dest):
            if _copy_asset(asset, dest):
                msgs.append(f"seeded {rel}")
            else:
                msgs.append(f"missing asset {asset}")

    _ensure_llms(docs, msgs, fetch=fetch_llms)

    if add_package:
        ensure_shadcn_package(project, msgs)

    return {
        "ok": True,
        "messages": msgs,
        "ui_spec": os.path.join(docs, UI_SPEC_NAME),
        "kit": os.path.join(docs, KIT_NAME),
        "llms": os.path.join(docs, LLMS_NAME),
    }


def ui_kit_block(project: str) -> str:
    """Short inject for spawn prompts: paths + mandatory read order."""
    project = os.path.abspath(project)
    docs = os.path.join(project, "docs")
    spec = os.path.join(docs, UI_SPEC_NAME)
    kit = os.path.join(docs, KIT_NAME)
    llms = os.path.join(docs, LLMS_NAME)
    lines = [
        "UI kit: **shadcn_flutter** (Foreman default).",
        "Before any UI work, READ in order:",
        f"1. `{_rel(project, spec)}`" + (" (present)" if os.path.isfile(spec) else " (MISSING — run foreman init)"),
        f"2. `{_rel(project, kit)}`" + (" (present)" if os.path.isfile(kit) else " (MISSING)"),
    ]
    if os.path.isfile(llms):
        lines.append(f"3. `{_rel(project, llms)}` — full API; grep before inventing widgets")
    else:
        lines.append(
            "3. Full API: https://sunarya-thito.github.io/shadcn_flutter/llms-full.txt "
            "(or re-run foreman init to cache docs/shadcn_flutter_llms.txt)"
        )
    lines += [
        "Rules: only documented APIs; no invented component names; "
        "prefer shadcn over Material; one primary CTA per screen; "
        "spacing 4/8/12/16/24/32/48/64; radius 12/16/20/24.",
    ]
    return "\n".join(lines)


def _rel(project: str, path: str) -> str:
    try:
        return os.path.relpath(path, project)
    except ValueError:
        return path
