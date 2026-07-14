"""Design language gate: human-approved tokens for implementers.

Status file: .foreman/design_status.json
Artifact:    tasks/design_language.md  (only when approved)
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

STATUS_NAME = "design_status.json"
HANDOFF_TASK = "design"
LANG_REL = os.path.join("tasks", "design_language.md")


def _status_path(project: str) -> str:
    return os.path.join(os.path.abspath(project), ".foreman", STATUS_NAME)


def _lang_path(project: str) -> str:
    return os.path.join(os.path.abspath(project), LANG_REL)


def _handoff_path(project: str) -> str:
    return os.path.join(
        os.path.abspath(project), ".foreman", "handoffs", f"{HANDOFF_TASK}.designer.json"
    )


def load_status(project: str) -> dict[str, Any]:
    p = _status_path(project)
    if not os.path.exists(p):
        return {"status": "missing", "approved": False}
    try:
        return json.load(open(p))
    except (json.JSONDecodeError, OSError):
        return {"status": "missing", "approved": False}


def save_status(project: str, obj: dict[str, Any]) -> None:
    d = os.path.join(os.path.abspath(project), ".foreman")
    os.makedirs(d, exist_ok=True)
    obj = dict(obj)
    obj["updated_at"] = time.time()
    path = _status_path(project)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)


def design_language_text(project: str) -> str:
    p = _lang_path(project)
    if not os.path.exists(p):
        return ""
    try:
        return open(p, encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


def assess_design(project: str) -> dict[str, Any]:
    """ready for implement when approved + design_language.md non-empty."""
    project = os.path.abspath(project)
    st = load_status(project)
    lang = design_language_text(project)
    approved = st.get("status") == "approved" and bool(lang.strip())
    has_draft = os.path.exists(_handoff_path(project))
    return {
        "ok": approved,
        "approved": approved,
        "status": st.get("status") or ("pending_review" if has_draft else "missing"),
        "has_handoff": has_draft,
        "has_language_doc": bool(lang.strip()),
        "language_path": _lang_path(project),
        "handoff_path": _handoff_path(project),
        "summary": st.get("summary") or "",
        "next": (
            ["foreman execute / foreman run"]
            if approved
            else (
                ["foreman design show", "foreman design approve"]
                if has_draft or st.get("status") == "pending_review"
                else ["foreman design run", "or foreman run (runs designer first)"]
            )
        ),
    }


def record_from_handoff(project: str, obj: dict) -> dict[str, Any]:
    """After designer handoff: mark pending_review; do not write language until approve."""
    project = os.path.abspath(project)
    summary = str(obj.get("summary") or "")
    mockups = obj.get("mockups") or []
    save_status(project, {
        "status": "pending_review",
        "approved": False,
        "summary": summary,
        "mockup_count": len(mockups) if isinstance(mockups, list) else 0,
        "open_questions": obj.get("open_questions") or [],
    })
    # Write draft preview for humans
    preview = os.path.join(project, ".foreman", "design_preview.md")
    os.makedirs(os.path.dirname(preview), exist_ok=True)
    parts = [f"# Design preview (pending human approval)\n\n{summary}\n"]
    if isinstance(mockups, list):
        for m in mockups:
            if not isinstance(m, dict):
                continue
            parts.append(f"\n## {m.get('screen', 'Screen')}\n\n```\n{m.get('wireframe', '')}\n```\n")
            if m.get("notes"):
                parts.append(f"\n_{m.get('notes')}_\n")
    if obj.get("design_language_md"):
        parts.append("\n---\n\n# Draft design language\n\n")
        parts.append(str(obj["design_language_md"]))
    open(preview, "w", encoding="utf-8").write("".join(parts))
    return assess_design(project)


def approve(project: str) -> dict[str, Any]:
    project = os.path.abspath(project)
    hp = _handoff_path(project)
    if not os.path.exists(hp):
        return {"ok": False, "message": "No designer handoff. Run: foreman design run"}
    try:
        obj = json.load(open(hp))
    except (json.JSONDecodeError, OSError) as e:
        return {"ok": False, "message": f"handoff unreadable: {e}"}
    body = obj.get("design_language_md") or ""
    if not str(body).strip():
        return {"ok": False, "message": "handoff missing design_language_md"}
    lang = _lang_path(project)
    os.makedirs(os.path.dirname(lang), exist_ok=True)
    open(lang, "w", encoding="utf-8").write(str(body).rstrip() + "\n")
    save_status(project, {
        "status": "approved",
        "approved": True,
        "summary": obj.get("summary") or "",
        "approved_at": time.time(),
    })
    return {"ok": True, **assess_design(project), "message": f"Approved → {LANG_REL}"}


def reject(project: str, reason: str = "") -> dict[str, Any]:
    project = os.path.abspath(project)
    save_status(project, {
        "status": "rejected",
        "approved": False,
        "reason": reason or "human rejected",
    })
    # archive handoff so designer re-runs cleanly
    hp = _handoff_path(project)
    if os.path.exists(hp):
        try:
            os.rename(hp, hp + f".rejected.{int(time.time())}")
        except OSError:
            pass
    return {"ok": True, "status": "rejected", "message": "Rejected. Re-run: foreman design run", "reason": reason}
