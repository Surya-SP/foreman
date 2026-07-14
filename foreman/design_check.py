"""Mechanical checks: approved design language tokens vs Dart sources."""
from __future__ import annotations

import json
import os
import re
from typing import Any

from foreman.design_gate import design_language_text, assess_design

_HEX = re.compile(r"#([0-9A-Fa-f]{6})\b")
_COLOR_CONST = re.compile(r"Color\(0x([0-9A-Fa-f]{8})\)")


def _hexes_from_language(md: str) -> set[str]:
    found = set()
    for m in _HEX.findall(md or ""):
        found.add(m.upper())
    return found


def _hexes_from_dart(text: str) -> set[str]:
    found = set()
    for m in _HEX.findall(text or ""):
        found.add(m.upper())
    for m in _COLOR_CONST.findall(text or ""):
        # 0xAARRGGBB → RRGGBB
        if len(m) >= 6:
            found.add(m[-6:].upper())
    return found


def _walk_dart(project: str, files: list[str] | None = None) -> list[tuple[str, str]]:
    out = []
    if files:
        for f in files:
            p = os.path.join(project, f) if not os.path.isabs(f) else f
            if os.path.isfile(p) and p.endswith(".dart"):
                try:
                    out.append((f, open(p, encoding="utf-8", errors="ignore").read()))
                except OSError:
                    pass
        return out
    lib = os.path.join(project, "lib")
    if not os.path.isdir(lib):
        return out
    for root, _, names in os.walk(lib):
        if "/." in root:
            continue
        for n in names:
            if n.endswith(".dart"):
                p = os.path.join(root, n)
                rel = os.path.relpath(p, project)
                try:
                    out.append((rel, open(p, encoding="utf-8", errors="ignore").read()))
                except OSError:
                    pass
    return out


def check_design_language(project: str, files: list[str] | None = None) -> dict[str, Any]:
    """Return findings if code ignores approved primary/surface tokens."""
    project = os.path.abspath(project)
    gate = assess_design(project)
    if not gate.get("approved"):
        return {
            "ok": True,
            "skipped": True,
            "reason": "design language not approved",
            "findings": [],
        }
    md = design_language_text(project)
    tokens = _hexes_from_language(md)
    if not tokens:
        return {
            "ok": True,
            "skipped": True,
            "reason": "no hex tokens in design language",
            "findings": [],
        }
    # Prefer primary-like tokens: first 1–3 hexes from language often include primary
    primary_candidates = list(tokens)[:8]
    dart_files = _walk_dart(project, files)
    code_hex: set[str] = set()
    for _, body in dart_files:
        code_hex |= _hexes_from_dart(body)
    findings = []
    # If code defines any colors at all, at least one design token should appear
    if code_hex and not (code_hex & tokens):
        findings.append({
            "tag": "design_token",
            "message": (
                "Dart Color/hex values do not include any hex from tasks/design_language.md. "
                f"Expected one of: {', '.join('#' + t for t in sorted(primary_candidates)[:5])}"
            ),
        })
    # Soft: if language has primary and code has colors, check primary specifically
    # Parse token_index from handoff if present
    hp = os.path.join(project, ".foreman", "handoffs", "design.designer.json")
    primary = None
    if os.path.exists(hp):
        try:
            h = json.load(open(hp))
            ti = h.get("token_index") or {}
            p = ti.get("primary") or ""
            m = _HEX.search(p)
            if m:
                primary = m.group(1).upper()
        except (json.JSONDecodeError, OSError):
            pass
    if primary and code_hex and primary not in code_hex:
        findings.append({
            "tag": "design_primary",
            "message": f"Approved primary #{primary} not found in scanned Dart colors",
        })
    return {
        "ok": len(findings) == 0,
        "skipped": False,
        "design_tokens": sorted(tokens)[:20],
        "code_colors": sorted(code_hex)[:20],
        "findings": findings,
        "files_scanned": len(dart_files),
    }
