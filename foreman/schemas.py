"""JSON schemas for sub-agent outputs. Contract-checked by handoff.py."""
from __future__ import annotations

# Required top-level keys per role. Extra keys allowed.
ROLE_SCHEMAS: dict[str, list[str]] = {
    "product_owner": ["role", "tasks"],
    "architect":     ["role", "approach", "files"],
    "developer":     ["role", "files_changed"],
    "qa_lead":       ["role", "test_strategy"],
    "tester":        ["role", "test_files", "all_pass"],
    "reviewer":      ["role", "findings", "verdict"],
    "refactorer":    ["role", "fixes_applied"],
    "debugger":      ["role", "root_cause", "fix"],
}


def check(role: str, obj: dict) -> list[str]:
    """Return list of validation errors (empty = valid)."""
    if not isinstance(obj, dict):
        return ["output is not a JSON object"]
    required = ROLE_SCHEMAS.get(role, [])
    missing = [k for k in required if k not in obj]
    errors = [f"missing required key: {k}" for k in missing]
    if "role" in obj and obj["role"] != role:
        errors.append(f"role mismatch: expected '{role}', got '{obj.get('role')}'")
    return errors
