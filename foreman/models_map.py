"""Per-role model resolution for OpenCode role sessions.

Capabilities (stable) → aliases (swappable) → roles.

Alias entry: string OR {"model": "...", "description": "..."}
Capability entry: string OR {"model": "alias|id", "reasoning": "low|medium|high"|...}

Resolution order (first wins):
  1. CLI --model (global force for this run)
  2. FOREMAN_MODEL_<ROLE> env
  3. models.json (roles → capabilities → aliases)
  4. None (OpenCode default)

Reserved (unused today): overrides, profiles — shape only for future.
"""
from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from typing import Any

_DEFAULT: dict[str, Any] = {
    "version": 2,
    "aliases": {
        "smart": {
            "model": "opencode/grok-4.5",
            "description": "Frontier planning / orchestration",
        },
        "code": {
            "model": "opencode/deepseek-v4-flash",
            "description": "Fast implementation (developer, designer)",
        },
        "reason": {
            "model": "opencode/deepseek-v4-pro",
            "description": "Complex debugging / refactor",
        },
        "review": {
            "model": "opencode/qwen3-coder",
            "description": "Code review and QA strategy",
        },
        "cheap": {
            "model": "opencode/glm-5.2",
            "description": "Utility / tester / low-stakes",
        },
    },
    # string = alias or provider/model; object can set reasoning effort later
    "capabilities": {
        "orchestrator": {"model": "smart"},
        "planning": {"model": "smart", "reasoning": "medium"},
        "coding": {"model": "code", "reasoning": "low"},
        "reasoning": {"model": "reason", "reasoning": "high"},
        "review": {"model": "review", "reasoning": "medium"},
        "utility": {"model": "cheap"},
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
    "overrides": {},
    # Future: named alias sets (budget/balanced/premium). Not applied yet.
    "profiles": {},
}

_ROLE_ENV = re.compile(r"[^A-Z0-9]+")


def default_map() -> dict[str, Any]:
    return deepcopy(_DEFAULT)


def config_paths() -> list[str]:
    paths = []
    env_path = os.environ.get("FOREMAN_MODELS_PATH", "").strip()
    if env_path:
        paths.append(os.path.abspath(env_path))
    xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    paths.append(os.path.join(xdg, "foreman", "models.json"))
    here = os.path.dirname(os.path.abspath(__file__))
    paths.append(os.path.join(here, "models.json"))
    root = os.path.abspath(os.path.join(here, ".."))
    paths.append(os.path.join(root, "models.json"))
    return paths


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = deepcopy(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            # merge nested unless it's a leaf alias/capability object with "model"
            if "model" in v and not any(isinstance(x, dict) for x in v.values() if x is not v.get("model")):
                out[k] = {**out.get(k, {}), **v} if isinstance(out.get(k), dict) and "model" in (out.get(k) or {}) else v
            elif k in ("aliases", "capabilities", "roles", "overrides", "profiles"):
                out[k] = _deep_merge(out.get(k) or {}, v)
            else:
                out[k] = _deep_merge(out.get(k) or {}, v)
        else:
            out[k] = deepcopy(v)
    return out


def load_map() -> tuple[dict[str, Any], str | None]:
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
        for key in ("aliases", "capabilities", "roles", "overrides", "profiles"):
            if isinstance(user.get(key), dict):
                if key in ("aliases", "capabilities"):
                    # per-key merge so string→object upgrades work
                    base_sec = dict(merged.get(key) or {})
                    for ak, av in user[key].items():
                        if isinstance(av, dict) and isinstance(base_sec.get(ak), dict):
                            base_sec[ak] = {**base_sec[ak], **av}
                        else:
                            base_sec[ak] = av
                    merged[key] = base_sec
                else:
                    merged[key] = {**merged.get(key, {}), **user[key]}
        if "version" in user:
            merged["version"] = user["version"]
        break
    return merged, used


def _alias_entry(aliases: dict, name: str) -> dict[str, Any] | None:
    if name not in aliases:
        return None
    v = aliases[name]
    if isinstance(v, str):
        return {"model": v, "description": ""}
    if isinstance(v, dict) and v.get("model"):
        return {
            "model": str(v["model"]),
            "description": str(v.get("description") or ""),
        }
    return None


def _expand_model_ref(ref: str, aliases: dict, depth: int = 0) -> tuple[str, str | None]:
    """Expand alias chain. Returns (provider/model, last_alias_or_None)."""
    if depth > 6:
        return ref, None
    entry = _alias_entry(aliases, ref)
    if entry:
        mid = entry["model"]
        # recursive if points to another alias
        if mid in aliases and mid != ref:
            expanded, _ = _expand_model_ref(mid, aliases, depth + 1)
            return expanded, ref
        return mid, ref
    return ref, None


def _capability_spec(capabilities: dict, cap: str) -> dict[str, Any]:
    raw = capabilities.get(cap, cap)
    if isinstance(raw, str):
        return {"model": raw, "reasoning": None}
    if isinstance(raw, dict):
        return {
            "model": str(raw.get("model") or cap),
            "reasoning": raw.get("reasoning"),
        }
    return {"model": str(cap), "reasoning": None}


def apply_reasoning_suffix(model_id: str, reasoning: str | None) -> str:
    """OpenCode supports provider/model#variant for effort on some models."""
    if not reasoning or not model_id:
        return model_id
    reasoning = str(reasoning).strip()
    if not reasoning or "#" in model_id:
        return model_id
    return f"{model_id}#{reasoning}"


def resolve_model(
    role: str,
    *,
    cli_model: str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    role = (role or "").strip()
    if cli_model and str(cli_model).strip():
        return {
            "role": role,
            "model": str(cli_model).strip(),
            "capability": None,
            "source": "cli",
            "alias": None,
            "reasoning": None,
            "description": None,
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
            "reasoning": None,
            "description": None,
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
            "reasoning": None,
            "description": None,
        }

    spec = _capability_spec(capabilities, cap)
    ref = spec["model"]
    expanded, alias_used = _expand_model_ref(ref, aliases)
    desc = None
    if alias_used:
        ae = _alias_entry(aliases, alias_used)
        if ae:
            desc = ae.get("description") or None
    model_id = apply_reasoning_suffix(expanded, spec.get("reasoning"))
    return {
        "role": role,
        "model": model_id,
        "capability": cap,
        "source": "config",
        "alias": alias_used,
        "reasoning": spec.get("reasoning"),
        "description": desc,
    }


def resolve_all(cli_model: str | None = None) -> dict[str, Any]:
    cfg, path = load_map()
    roles = list((cfg.get("roles") or {}).keys())
    for r in (
        "foreman", "product_owner", "architect", "designer", "developer",
        "debugger", "refactorer", "reviewer", "qa_lead", "tester",
    ):
        if r not in roles:
            roles.append(r)
    resolved = {r: resolve_model(r, cli_model=cli_model, config=cfg) for r in roles}
    # alias catalog for UI
    alias_catalog = {}
    for name, _ in (cfg.get("aliases") or {}).items():
        e = _alias_entry(cfg.get("aliases") or {}, name)
        if e:
            alias_catalog[name] = e
    return {
        "ok": True,
        "config_path": path,
        "config": cfg,
        "aliases": alias_catalog,
        "resolved": resolved,
        "cli_model": cli_model,
        "resolution_order": [
            "CLI --model",
            "FOREMAN_MODEL_<ROLE>",
            "models.json (roles → capabilities → aliases)",
            "OpenCode default",
        ],
        "notes": [
            "profiles and overrides are reserved; not applied yet",
            "capability.reasoning appends #variant when supported by OpenCode",
        ],
    }


def write_user_config(path: str | None = None) -> str:
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
