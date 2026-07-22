#!/usr/bin/env python3
"""Fill a role prompt with project context. Output the prompt for `task` tool.

Usage:
  spawn.py --role architect --project . --task-id t3
  spawn.py --role developer --project . --task-id t3 --load-from t3.architect
  spawn.py --role debugger --project . --task-id t3 --error "$VALIDATE_OUT" --save

Flags:
  --role ROLE           architect|developer|reviewer|tester|debugger|refactorer|product_owner|qa_lead
  --task-id ID          Task identifier (looks up state, saves outputs)
  --task-desc TEXT      Task description (overrides state lookup)
  --acceptance TEXT     Acceptance criteria
  --plan TEXT           Prior role JSON (inline)
  --load-from KEY       Load prior role JSON from .foreman/handoffs/<task_id>.<KEY>.json
  --error TEXT          Validation error (for debugger)
  --diff TEXT           Git diff (for reviewer)
  --save                Save filled prompt + role output slot to handoffs
  --section NAME        Filter design.md section
"""
import json, os, re, subprocess, sys, time
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
sys.path.insert(0, _ROOT)

from foreman.config import Config
from foreman.log import log
from foreman import memory as mem

_start = time.time()

ROLE_FILES = {
    "architect": "architect.txt", "developer": "implementer.txt",
    "reviewer": "reviewer.txt", "tester": "tester.txt", "debugger": "debugger.txt",
    "refactorer": "refactorer.txt", "product_owner": "product_owner.txt",
    "qa_lead": "qa_lead.txt", "designer": "designer.txt",
}
# Only compute placeholders the role actually uses.
ROLE_NEEDS = {
    "architect": {"task_description", "acceptance_criteria", "sdk", "packages", "lib_files",
                  "project_memory", "design", "design_language", "ui_kit", "repo_memory"},
    "developer": {"task_description", "acceptance_criteria", "architect_plan", "sdk", "packages",
                  "project_dir", "design_language", "ui_kit", "repo_memory"},
    "reviewer":  {"task_description", "acceptance_criteria", "diff", "design_language", "ui_kit",
                  "repo_memory"},
    "tester":    {"task_description", "acceptance_criteria", "changed_files", "project_dir", "test_plan",
                  "repo_memory"},
    "debugger":  {"task_description", "changed_files", "failed_steps", "validation_error", "repo_memory"},
    "refactorer":{"task_description", "review_findings", "changed_files", "project_dir",
                  "design_language", "ui_kit", "repo_memory"},
    "product_owner": {"prd", "design", "project_memory", "repo_memory"},
    "qa_lead":   {"task_description", "acceptance_criteria", "changed_files", "design",
                  "design_language", "ui_kit", "repo_memory"},
    "designer":  {"prd", "design", "project_dir", "ui_kit", "repo_memory"},
}

def _arg(name, default=None):
    return next((sys.argv[i+1] for i,a in enumerate(sys.argv) if a==name), default)

def _err(msg, code=1):
    json.dump({"ok": False, "message": msg}, sys.stdout)
    log(os.path.join(target, ".foreman"), "spawn.py", code, int((time.time()-_start)*1000))
    sys.exit(code)

target = os.path.abspath(_arg("--project") or os.environ.get("FOREMAN_PROJECT") or ".")
role = _arg("--role")
task_id = _arg("--task-id") or ""

if not role or role not in ROLE_FILES:
    _err(f"Invalid --role. Valid: {', '.join(sorted(ROLE_FILES))}")

foreman_home = os.environ.get("FOREMAN_HOME") or _ROOT
role_file = ROLE_FILES[role]
prompt_path = os.path.join(foreman_home, "prompts", "roles", role_file)
if not os.path.exists(prompt_path):
    _err(f"Prompt template not found for role '{role}' at {prompt_path}")

try:
    template = open(prompt_path).read()
except OSError as e:
    _err(f"Could not read prompt: {e}")

needs = ROLE_NEEDS.get(role, set())
handoff_dir = os.path.join(target, ".foreman", "handoffs")
os.makedirs(handoff_dir, exist_ok=True)

# ---- Load prior role output if requested ------------------------------------
loaded_plan = ""
load_from = _arg("--load-from")
if load_from:
    hp = os.path.join(handoff_dir, f"{task_id}.{load_from}.json")
    if os.path.exists(hp):
        try:
            loaded_plan = open(hp).read()
        except OSError:
            pass

# ---- Task lookup from state ------------------------------------------------
task_state = {}
if task_id:
    sp = os.path.join(target, ".foreman", "tasks.json")
    if os.path.exists(sp):
        try:
            task_state = json.load(open(sp)).get(task_id, {})
        except (json.JSONDecodeError, OSError):
            pass

# ---- Run a foreman tool via subprocess (no shell) --------------------------
def _run_tool(tool: str, *args: str) -> dict:
    script = os.path.join(foreman_home, "foreman", "tools", tool)
    try:
        r = subprocess.run([sys.executable, script, "--project", target, *args],
                           capture_output=True, text=True, timeout=60)
        return json.loads(r.stdout) if r.stdout else {}
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return {}

# ---- Gather ONLY what this role needs --------------------------------------
values: dict[str, str] = {}

if "sdk" in needs or "packages" in needs or "lib_files" in needs:
    info = _run_tool("project_info.py")
    values["sdk"] = json.dumps(info.get("sdk", {}))
    values["packages"] = json.dumps(info.get("packages", []))
    values["lib_files"] = json.dumps((info.get("source_files") or [])[:40])
    values["changed_files"] = json.dumps((info.get("source_files") or [])[:40])
elif "changed_files" in needs:
    values["changed_files"] = json.dumps(task_state.get("files", []))

if "prd" in needs or "design" in needs:
    plan_args = []
    section = _arg("--section")
    if section:
        plan_args += ["--section", section]
    # Prefer truncated plan for token budget
    plan_args += ["--lines", "40"]
    plan = _run_tool("plan.py", *plan_args)
    values["prd"] = json.dumps(plan.get("prd", {}))
    values["design"] = json.dumps(plan.get("design", {}))

if "design_language" in needs:
    from foreman.design_gate import design_language_text
    dl = design_language_text(target)
    if dl.strip():
        # Cap for token budget
        values["design_language"] = dl if len(dl) < 6000 else dl[:5800] + "\n…[truncated]"
    else:
        values["design_language"] = (
            "(no approved design language yet — follow tasks/design.md; "
            "human should run: foreman design approve after designer review)"
        )

if "ui_kit" in needs:
    from foreman.ui_kit import ui_kit_block, seed_ui_kit
    # Ensure kit docs exist (no network in spawn; package add skipped)
    seed_ui_kit(target, fetch_llms=False, add_package=False)
    values["ui_kit"] = ui_kit_block(target)

if "project_memory" in needs:
    state_path = os.path.join(target, ".foreman", "tasks.json")
    done = []
    if os.path.exists(state_path):
        try:
            all_tasks = json.load(open(state_path))
            done = [{"id": k, "desc": v.get("description", "")[:80]}
                    for k, v in all_tasks.items() if v.get("status") == "done"][-8:]
        except (json.JSONDecodeError, OSError):
            pass
    values["project_memory"] = json.dumps(done)

# Caps on large injects (handoff / error / diff)
_raw_error = _arg("--error")
_raw_diff = _arg("--diff")
_caps = mem.inject_caps(
    loaded_plan=loaded_plan,
    error=_raw_error or "",
    diff=_raw_diff or "",
)
loaded_plan = _caps["loaded_plan"]
if _raw_error:
    error_text = _caps["error"] or "(empty error)"
else:
    error_text = "(no error provided)"
if _raw_diff:
    diff_text = _caps["diff"] or "(empty diff)"
else:
    diff_text = "(run `git diff HEAD~1` for the diff)"

values["project_dir"] = target
values["task_description"] = _arg("--task-desc") or task_state.get("description") or f"Task {task_id or '(unspecified)'}"
values["acceptance_criteria"] = _arg("--acceptance") or task_state.get("acceptance") or "(not specified)"
values["architect_plan"] = _arg("--plan") or loaded_plan or "(none)"
values["review_findings"] = loaded_plan or "(none)"
values["test_plan"] = "(see architect plan)"
values["diff"] = diff_text
values["validation_error"] = error_text
values["failed_steps"] = error_text

# Repo memory graph: retrieve only matching facts (no hallucination source)
if "repo_memory" in needs:
    task_files = list(task_state.get("files") or [])
    query = " ".join([
        values.get("task_description") or "",
        values.get("acceptance_criteria") or "",
        " ".join(task_files),
    ])
    retrieved = mem.retrieve(
        target,
        role=role,
        task_id=task_id or "",
        query=query,
        files=task_files,
        limit=10,
    )
    values["repo_memory"] = mem.format_memory_block(retrieved)
else:
    values["repo_memory"] = ""

# ---- Fill template ----------------------------------------------------------
filled = template
# Mustache conditionals: {{#var}}...{{/var}} — drop if empty
def _cond(m):
    var, body = m.group(1), m.group(2)
    v = values.get(var, "")
    return body if (v and v not in ("(none)", "[]", "{}")) else ""
filled = re.sub(r"\{\{#(\w+)\}\}(.*?)\{\{/\1\}\}", _cond, filled, flags=re.DOTALL)
# Drop empty repo memory section before placeholder fill
if not values.get("repo_memory"):
    filled = re.sub(
        r"\n## Repo memory \(facts only\)\n\n\{\{repo_memory\}\}\n?",
        "\n",
        filled,
    )
if not values.get("design_language") or values.get("design_language", "").startswith("(no approved"):
    # keep placeholder text so agents still see the note
    pass
for k, v in values.items():
    filled = filled.replace("{{" + k + "}}", v if v is not None else "")
# Mandatory design-language compliance for implementers
if role in ("architect", "developer", "reviewer", "refactorer", "qa_lead"):
    filled += (
        "\n\n## Design language (STRICT)\n\n"
        "Follow `tasks/design_language.md` when present (injected above as design_language). "
        "Do not invent colors, type scales, or component patterns that conflict with it. "
        "If design_language is missing/unapproved, stop and tell Tech Lead to run "
        "`foreman design run` → human `foreman design approve`.\n"
        "UI kit is **shadcn_flutter** — read docs/UI_SPEC.md + docs/shadcn_flutter_kit.md "
        "before UI; never invent component APIs.\n"
    )
missing = re.findall(r"\{\{(\w+)\}\}", filled)

# ---- Optional: append self-handoff instruction ------------------------------
# When --self-handoff is passed, the sub-agent is instructed to persist its
# JSON output by running `foreman handoff` itself (via its bash tool), so the
# Tech Lead doesn't have to.
if "--self-handoff" in sys.argv and task_id:
    filled += (
        "\n\n## Self-handoff (mandatory final step)\n\n"
        f"When you finish, save your JSON output by running from the project root:\n\n"
        f"```bash\n"
        f"cat <<'FOREMAN_EOF' | foreman handoff {task_id} {role}\n"
        f"<paste your JSON block here>\n"
        f"FOREMAN_EOF\n"
        f"```\n\n"
        f"If the schema check fails, fix the JSON and re-run. Do NOT use --force.\n"
    )

# ---- Save prompt (optional) -------------------------------------------------
if "--save" in sys.argv and task_id:
    open(os.path.join(handoff_dir, f"{task_id}.{role}.prompt.txt"), "w").write(filled)

# ---- Minimal output ---------------------------------------------------------
if "--estimate-tokens" in sys.argv:
    result = {"ok": True, "role": role, "task_id": task_id,
              "estimated_tokens": len(filled) // 4, "bytes": len(filled)}
else:
    result = {"ok": True, "role": role, "task_id": task_id, "prompt": filled}
    if missing:
        result["missing"] = missing
from foreman import ui
tok = result.get("estimated_tokens")
if tok is None and "prompt" in result:
    tok = len(result["prompt"]) // 4
ui.spawn_view(role, task_id, True, tokens=tok)
json.dump(result, sys.stdout, indent=2)
print()
log(os.path.join(target, ".foreman"), "spawn.py", 0, int((time.time()-_start)*1000),
    extra={"role": role, "task_id": task_id, "prompt_bytes": len(filled)})
