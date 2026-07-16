#!/usr/bin/env python3
"""Show / init per-role OpenCode model map.

  models_cmd.py
  models_cmd.py --init          # write ~/.config/foreman/models.json if missing
  models_cmd.py --model X       # show resolution with CLI force
"""
import json, os, sys, time
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
sys.path.insert(0, _ROOT)

from foreman.log import log
from foreman.models_map import resolve_all, write_user_config, config_paths
from foreman import ui

_start = time.time()

def _arg(name, default=None):
    return next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == name), default)

cli_model = _arg("--model")
do_init = "--init" in sys.argv

if do_init:
    path = write_user_config()
    out = {"ok": True, "wrote": path, "paths": config_paths()}
else:
    out = resolve_all(cli_model=cli_model)

if ui.is_pretty() and not do_init:
    ui.block(
        "Role → capability → model",
        command="foreman models",
        detail=f"config: {out.get('config_path') or '(built-in defaults)'}",
    )
    for role, meta in sorted((out.get("resolved") or {}).items()):
        m = meta.get("model") or "(OpenCode default)"
        cap = meta.get("capability") or "—"
        src = meta.get("source") or "?"
        print(f"  {role:16} {cap:12} → {m}  [{src}]", file=sys.stderr)
    print(file=sys.stderr)

json.dump(out, sys.stdout, indent=2)
print()
log(os.path.join(os.environ.get("FOREMAN_PROJECT") or ".", ".foreman"),
    "models_cmd.py", 0, int((time.time() - _start) * 1000))
sys.exit(0)
