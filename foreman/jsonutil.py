"""Balanced JSON object extraction (no greedy DOTALL)."""
from __future__ import annotations

import json
import re
from typing import Any


def extract_json_object(text: str) -> tuple[dict[str, Any] | None, str]:
    """Return (object, raw_substring) or (None, error)."""
    if not text or not text.strip():
        return None, "empty input"
    # Prefer fenced ```json blocks
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    candidates: list[str] = []
    if fence:
        candidates.append(fence.group(1))
    # Scan for balanced {...}
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        depth = 0
        in_str = False
        esc = False
        for j in range(i, len(text)):
            c = text[j]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[i : j + 1])
                    break
        if len(candidates) >= 8:
            break
    # Try longest first (most complete object)
    for raw in sorted(set(candidates), key=len, reverse=True):
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                return obj, raw
        except json.JSONDecodeError:
            continue
    return None, "No valid JSON object found"
