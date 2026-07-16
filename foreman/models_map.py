"""Per-role model resolution for OpenCode role sessions.

Capabilities (stable) → aliases/provider IDs (swappable) → roles.

Resolution order (first wins):
  1. CLI --model (global force for this run)
  2. FOREMAN_MODEL_<ROLE> env
  3. models.json (roles → capabilities → aliases)
  4. None (OpenCode session default; agent frontmatter not used by Foreman)

No dynamic task routing yet; `overrides` reserved for later.
"""
from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from typing import Any

# Default map shipped with Foreman. User may override via:
#   $XDG_CONFIG_HOME/foreman/models.json
#   or FOREMAN_MODELS_PATH
_DEFAULT: dict[str, Any] = {
    "version": 1,
    "aliases": {
        "smart": "opencode/grok-4.5",
        "code": "opencode/deepseek-v4-flash",
        "reason": "opencode/deepseek-v4-pro",
        "review": "opencode/qwen3-coder",
        "cheap": "opencode/glm-5.2",
    },
    "capabilities": {
        "orchestrator": "smart",
        "planning": "smart",
        "coding": "code",
        "reasoning": "reason",
        "review": "review",
        "utility": "cheap",
    },
    "roles": {
        "foreman": "orchestrator",
        "product_owner": "planning",
        "architect": "planning",
        "designer": "coding",
        "developer": "coding",
        "debugger": "reasoning",
        "refactorer": "reasoning",
        "reviewer": "review",
        "qa_lead": "review",
        "tester": "utility",
    },
    # Reserved for future task-based routing (unused today)
    "overrides": {},
}

_ROLE_ENV = re.compile(r"[^A-Z0-9]+")


def default_map() -> dict[str, Any]:
    return deepcopy(_DEFAULT)


def config_paths() -> list[str]:
    """Search order for models.json (first existing file wins)."""
    paths = []
    env_path = os.environ.get("FOREMAN_MODELS_PATH", "").strip()
    if env_path:
        paths.append(os.path.abspath(env_path))
    xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    paths.append(os.path.join(xdg, "foreman", "models.json"))
    # shipped default next to package
    here = os.path.dirname(os.path.abspath(__file__))
    paths.append(os.path.join(here, "models.json"))
    # repo root fallback
    root = os.path.abspath(os.path.join(here, ".."))
    paths.append(os.path.join(root, "models.json"))
    return paths


def load_map() -> tuple[dict[str, Any], str | None]:
    """Return (map, path_used). path_used is None if pure built-in defaults."""
    merged = default_map()
    used = None
    for p in config_paths():
        if not os.path.isfile(p):
            continue
        try:
            user = json.load(open(p, encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(user, dict):
            continue
        used = p
        for key in ("aliases", "capabilities", "roles", "overrides"):
            if isinstance(user.get(key), dict):
                merged[key] = {**merged.get(key, {}), **user[key]}
        if "version" in user:
            merged["version"] = user["version"]
        break  # first existing file wins (after merge onto defaults)
    return merged, used


def _expand_alias(name: str, aliases: dict[str, str], depth: int = 0) -> str:
    if depth > 5:
        return name
    if name in aliases:
        return _expand_alias(aliases[name], aliases, depth + 1)
    return name


def resolve_model(
    role: str,
    *,
    cli_model: str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve provider/model for a role.

    Returns:
      {
        "role": str,
        "model": str | None,   # None → OpenCode default
        "capability": str | None,
        "source": "cli" | "env" | "config" | "default",
        "alias": str | None,
      }
    """
    role = (role or "").strip()
    if cli_model and str(cli_model).strip():
        return {
            "role": role,
            "model": str(cli_model).strip(),
            "capability": None,
            "source": "cli",
            "alias": None,
        }

    env_key = "FOREMAN_MODEL_" + _ROLE_ENV.sub("_", role.upper()).strip("_")
    env_val = os.environ.get(env_key, "").strip()
    if env_val:
        return {
            "role": role,
            "model": env_val,
            "capability": None,
            "source": "env",
            "alias": None,
            "env": env_key,
        }

    cfg = config if config is not None else load_map()[0]
    aliases = cfg.get("aliases") or {}
    capabilities = cfg.get("capabilities") or {}
    roles = cfg.get("roles") or {}

    cap = roles.get(role)
    if not cap:
        return {
            "role": role,
            "model": None,
            "capability": None,
            "source": "default",
            "alias": None,
        }

    raw = capabilities.get(cap, cap)
    raw = str(raw)
    expanded = _expand_alias(raw, {str(k): str(v) for k, v in aliases.items()})
    alias_used = raw if raw in aliases else None
    return {
        "role": role,
        "model": expanded,
        "capability": cap,
        "source": "config",
        "alias": alias_used,
    }


def resolve_all(cli_model: str | None = None) -> dict[str, Any]:
    cfg, path = load_map()
    roles = list((cfg.get("roles") or {}).keys())
    # include known roles even if map incomplete
    for r in (
        "foreman", "product_owner", "architect", "designer", "developer",
        "debugger", "refactorer", "reviewer", "qa_lead", "tester",
    ):
        if r not in roles:
            roles.append(r)
    resolved = {r: resolve_model(r, cli_model=cli_model, config=cfg) for r in roles}
    return {
        "ok": True,
        "config_path": path,
        "config": cfg,
        "resolved": resolved,
        "cli_model": cli_model,
        "resolution_order": [
            "CLI --model",
            "FOREMAN_MODEL_<ROLE>",
            "models.json (roles → capabilities → aliases)",
            "OpenCode default",
        ],
    }


def write_user_config(path: str | None = None) -> str:
    """Write default map to user config path if missing. Returns path."""
    if not path:
        xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
        path = os.path.join(xdg, "foreman", "models.json")
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default_map(), f, indent=2)
            f.write("\n")
    return path
