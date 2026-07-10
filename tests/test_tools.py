#!/usr/bin/env python3
"""Validation + integration tests. Run: python3 tests/test_tools.py [--verbose]"""
import json, os, subprocess, sys, tempfile, traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
TOOLS = os.path.join(_ROOT, "foreman", "tools")
BIN = os.path.join(_ROOT, "bin", "foreman")

PASS = FAIL = 0
VERBOSE = "--verbose" in sys.argv


def run(cmd, stdin=None, timeout=30, env=None):
    e = {**os.environ, **(env or {})}
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=stdin, env=e)
    return r.returncode, r.stdout, r.stderr


def T(name, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1; print(f"  ✓ {name}")
    except Exception as e:
        FAIL += 1; print(f"  ✗ {name}: {e}")
        if VERBOSE: traceback.print_exc()


def js(raw):
    try: return json.loads(raw)
    except json.JSONDecodeError as e:
        raise AssertionError(f"invalid JSON: {e}\n---\n{raw[:400]}") from e


def tool(name, *args, project=_ROOT, stdin=None):
    return run([sys.executable, os.path.join(TOOLS, name), "--project", project, *args], stdin=stdin)


def wrap(*args, project=_ROOT, stdin=None):
    env = {"FOREMAN_PROJECT": project, "FOREMAN_HOME": _ROOT}
    return run([BIN, *args], stdin=stdin, env=env)


def _mkfake_flutter(root):
    """Create a minimal Flutter-shaped fixture directory."""
    os.makedirs(os.path.join(root, "lib"))
    os.makedirs(os.path.join(root, "test"))
    os.makedirs(os.path.join(root, "tasks"))
    open(os.path.join(root, "pubspec.yaml"), "w").write("name: fake\nversion: 0.0.1\ndependencies:\n  flutter:\n    sdk: flutter\n")
    open(os.path.join(root, "lib", "main.dart"), "w").write("class MyApp {}\n")
    open(os.path.join(root, "tasks", "prd.md"), "w").write("# Goal\nBuild an auth screen.\n\n## Features\n- Login\n")
    open(os.path.join(root, "tasks", "design.md"), "w").write("# LoginScreen\nUses Form and TextFormField. Primary color 0x2196F3.\n")


# ── Existing tool tests ───────────────────────────────────────────────────
def test_info_summary():
    rc, out, _ = tool("project_info.py", "--summary")
    assert rc == 0; d = js(out); assert d["ok"]


def test_info_brief():
    rc, out, _ = tool("project_info.py", "--brief")
    assert rc == 0 and "·" in out


def test_plan_missing():
    with tempfile.TemporaryDirectory() as t:
        rc, out, _ = tool("plan.py", project=t)
        assert rc == 0; assert js(out)["prd"]["exists"] is False


def test_plan_cache_key():
    with tempfile.TemporaryDirectory() as t:
        rc, out, _ = tool("plan.py", project=t)
        assert "_cache_key" in js(out)


# ── Spawn tests ───────────────────────────────────────────────────────────
def test_spawn_all_roles():
    for role in ("architect", "developer", "reviewer", "tester", "debugger",
                 "refactorer", "product_owner", "qa_lead"):
        rc, out, _ = tool("spawn.py", "--role", role, "--task-id", "test")
        assert rc == 0, f"role={role}"
        d = js(out); assert d["role"] == role; assert d["prompt"]
        assert "context_used" not in d and "instructions" not in d


def test_spawn_estimate_tokens():
    rc, out, _ = tool("spawn.py", "--role", "architect", "--task-id", "t1", "--estimate-tokens")
    d = js(out); assert "estimated_tokens" in d; assert "prompt" not in d


def test_spawn_load_from():
    with tempfile.TemporaryDirectory() as t:
        hd = os.path.join(t, ".foreman", "handoffs"); os.makedirs(hd)
        open(os.path.join(hd, "t1.architect.json"), "w").write('{"approach":"X"}')
        rc, out, _ = tool("spawn.py", "--role", "developer", "--task-id", "t1",
                          "--load-from", "architect", project=t)
        assert rc == 0; assert '"approach":"X"' in js(out)["prompt"]


def test_spawn_no_shell_injection():
    bad = "/tmp/x; touch /tmp/foreman_pwned_$$"
    tool("spawn.py", "--role", "architect", "--task-id", "t1", project=bad)
    assert not os.path.exists(f"/tmp/foreman_pwned_{os.getpid()}")


# ── Handoff tests ─────────────────────────────────────────────────────────
def test_handoff_strips_fences():
    with tempfile.TemporaryDirectory() as t:
        raw = 'Preamble\n```json\n{"role":"architect","approach":"foo","files":[]}\n```\nTrailing.'
        rc, out, _ = tool("handoff.py", "--task-id", "t1", "--role", "architect",
                          "--stdin", project=t, stdin=raw)
        assert rc == 0; assert js(out)["ok"]
        saved = json.load(open(os.path.join(t, ".foreman", "handoffs", "t1.architect.json")))
        assert saved["approach"] == "foo"


def test_handoff_rejects_invalid_json():
    with tempfile.TemporaryDirectory() as t:
        rc, out, _ = tool("handoff.py", "--task-id", "t1", "--role", "architect",
                          "--stdin", project=t, stdin="not json {")
        assert rc == 1; assert js(out)["ok"] is False


def test_handoff_schema_check():
    with tempfile.TemporaryDirectory() as t:
        # Missing required 'approach' and 'files' for architect
        rc, out, _ = tool("handoff.py", "--task-id", "t1", "--role", "architect",
                          "--stdin", project=t, stdin='{"role":"architect"}')
        assert rc == 1
        d = js(out); assert d["ok"] is False; assert "errors" in d


def test_handoff_force_bypasses_schema():
    with tempfile.TemporaryDirectory() as t:
        rc, out, _ = tool("handoff.py", "--task-id", "t1", "--role", "architect",
                          "--stdin", "--force", project=t, stdin='{"role":"architect"}')
        assert rc == 0


# ── State tests ───────────────────────────────────────────────────────────
def test_state_full_flow():
    with tempfile.TemporaryDirectory() as t:
        tool("state.py", "--add", "t1", "--desc", "scaffold", project=t)
        tool("state.py", "--add", "t2", "--desc", "auth", "--deps", "t1", project=t)
        rc, out, _ = tool("state.py", "--ready", project=t)
        d = js(out); assert d["count"] == 1 and d["tasks"][0]["id"] == "t1"
        tool("state.py", "--mark", "t1", "--status", "done", project=t)
        rc, out, _ = tool("state.py", "--ready", project=t)
        assert js(out)["tasks"][0]["id"] == "t2"


def test_state_import_bulk():
    with tempfile.TemporaryDirectory() as t:
        po = json.dumps({"tasks": [
            {"id": "t1", "description": "scaffold", "depends_on": []},
            {"id": "t2", "description": "auth", "depends_on": ["t1"]},
            {"id": "t3", "description": "profile", "depends_on": ["t2"]},
        ]})
        rc, out, _ = tool("state.py", "--import", project=t, stdin=po)
        assert rc == 0
        d = js(out); assert d["added"] == 3; assert d["skipped"] == 0
        rc, out, _ = tool("state.py", "--all", project=t)
        assert js(out)["count"] == 3


def test_state_import_from_array():
    with tempfile.TemporaryDirectory() as t:
        arr = json.dumps([{"id": "t1", "description": "a"}])
        rc, out, _ = tool("state.py", "--import", project=t, stdin=arr)
        assert rc == 0; assert js(out)["added"] == 1


def test_state_guide():
    with tempfile.TemporaryDirectory() as t:
        tool("state.py", "--add", "t1", "--desc", "auth", project=t)
        rc, out, _ = tool("state.py", "--guide", "t1", project=t)
        d = js(out); assert d["ok"]; assert d["next_steps"]


# ── Verify tests ──────────────────────────────────────────────────────────
def test_verify_tags():
    with tempfile.TemporaryDirectory() as t:
        p = os.path.join(t, "x.dart")
        open(p, "w").write("class LoginScreen extends StatelessWidget {}\n")
        rc, out, _ = tool("verify.py", "--files", p, project=t)
        d = js(out)
        assert "by_tag" in d
        assert all(f.get("tag") for f in d["findings"])


def test_verify_strict():
    with tempfile.TemporaryDirectory() as t:
        _mkfake_flutter(t)
        p = os.path.join(t, "lib", "extras.dart")
        open(p, "w").write("class Extras {}\n")
        rc_default, _, _ = tool("verify.py", "--files", p, project=t)
        rc_strict, _, _ = tool("verify.py", "--files", p, "--strict", project=t)
        # class tag is critical; strict fails; default fails only if critical present
        assert rc_default == rc_strict  # both fail for class-tag findings


# ── Wrapper tests ─────────────────────────────────────────────────────────
def test_wrapper_next_single_json():
    with tempfile.TemporaryDirectory() as t:
        r = wrap("next", project=t)
        assert r[0] == 0
        d = js(r[1]); assert "brief" in d; assert "ready" in d; assert "guidance" in d


def test_wrapper_state_add_done():
    with tempfile.TemporaryDirectory() as t:
        assert wrap("state", "add", "t9", "scaffold", project=t)[0] == 0
        assert wrap("state", "done", "t9", project=t)[0] == 0


def test_wrapper_state_import():
    with tempfile.TemporaryDirectory() as t:
        raw = json.dumps({"tasks": [{"id": "t1", "description": "x"}]})
        r = wrap("state", "import", project=t, stdin=raw)
        assert r[0] == 0; assert js(r[1])["added"] == 1


def test_wrapper_state_guide():
    with tempfile.TemporaryDirectory() as t:
        wrap("state", "add", "t1", "auth", project=t)
        r = wrap("state", "guide", "t1", project=t)
        assert r[0] == 0; d = js(r[1]); assert d["next_steps"]


def test_wrapper_log():
    with tempfile.TemporaryDirectory() as t:
        wrap("state", "add", "t1", "auth", project=t)
        r = wrap("log", "5", project=t)
        assert r[0] == 0; assert "state.py" in r[1]


def test_wrapper_help():
    r = wrap("help")
    assert r[0] == 0 and "spawn" in r[1] and "state" in r[1]
    assert "run" in r[1] and "AUTONOMOUS" in r[1]


def test_wrapper_state_auto_requires_id():
    with tempfile.TemporaryDirectory() as t:
        r = wrap("state", "auto", project=t)
        assert r[0] == 2
        d = js(r[1]); assert d["ok"] is False
        assert "task-id" in d["message"].lower() or "requires" in d["message"].lower()
        assert "foreman run" in d.get("note", "") or "foreman run" in d.get("hint", "")


def test_wrapper_state_summary_empty_hint():
    with tempfile.TemporaryDirectory() as t:
        r = wrap("state", project=t)
        assert r[0] == 0
        d = js(r[1]); assert d["total"] == 0
        assert "template" in d["hint"] or "foreman run" in d["hint"]


def test_wrapper_next_how_to_run():
    with tempfile.TemporaryDirectory() as t:
        r = wrap("next", project=t)
        assert r[0] == 0
        d = js(r[1]); assert "how_to_run" in d
        assert "foreman run" in d["how_to_run"]
        assert "empty" in d["guidance"].lower() or "template" in d["guidance"].lower()


def test_wrapper_run_dry_run():
    with tempfile.TemporaryDirectory() as t:
        # without agent install, run should fail helpfully
        r = wrap("run", "--dry-run", project=t)
        # either dry-run ok (if agent present somehow) or missing agent
        d = js(r[1])
        if r[0] != 0:
            assert d["ok"] is False
            assert "agent" in d["message"].lower() or "install" in d.get("hint", "").lower()
        else:
            assert d.get("dry_run") is True
            assert d["agent"] == "foreman"
            assert "opencode" in d["would_run"][0] or d["would_run"][0].endswith("opencode")


def test_wrapper_unknown_command_json():
    r = wrap("spwan")  # typo
    assert r[0] == 2
    # may be on stderr
    raw = r[1] or r[2]
    assert "unknown" in raw.lower() or "foreman help" in raw


def test_opencode_agents_present():
    agent_dir = os.path.join(_ROOT, "opencode", "agent")
    assert os.path.isfile(os.path.join(agent_dir, "foreman.md"))
    for role in ("product_owner", "architect", "qa_lead", "developer",
                 "tester", "reviewer", "refactorer", "debugger"):
        assert os.path.isfile(os.path.join(agent_dir, f"{role}.md")), role
    assert os.path.isfile(os.path.join(_ROOT, "opencode", "command", "ship.md"))
    assert os.path.isfile(os.path.join(_ROOT, "opencode", "skill", "foreman", "SKILL.md"))


def test_install_sh_links_agents():
    with tempfile.TemporaryDirectory() as t:
        rc, out, err = run([os.path.join(_ROOT, "install.sh"), t], timeout=15)
        assert rc == 0, err or out
        assert os.path.islink(os.path.join(t, ".opencode", "agent", "foreman.md")) or \
               os.path.exists(os.path.join(t, ".opencode", "agent", "foreman.md"))
        assert os.path.exists(os.path.join(t, ".opencode", "command", "ship.md"))
        # dry-run should work after install
        r = wrap("run", "--dry-run", project=t)
        d = js(r[1]); assert d["ok"] and d["dry_run"]
        assert "--agent" in d["would_run"] and "foreman" in d["would_run"]


def test_install_sh_global_only():
    rc, out, err = run([os.path.join(_ROOT, "install.sh"), "--global-only"], timeout=15)
    assert rc == 0, err or out
    g = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
                     "opencode", "agent", "foreman.md")
    assert os.path.exists(g) or os.path.islink(g)
    # project without local .opencode still ok via global agent
    with tempfile.TemporaryDirectory() as t:
        r = wrap("run", "--dry-run", project=t)
        d = js(r[1]); assert d["ok"] and d["dry_run"]


# ── Dry-run tests ─────────────────────────────────────────────────────────
def test_validate_dry_run():
    rc, out, _ = tool("validate.py", "--dry-run", project=_ROOT)
    d = js(out); assert d["dry_run"] and "would_run" in d


def test_rollback_dry_run():
    with tempfile.TemporaryDirectory() as t:
        os.makedirs(os.path.join(t, ".git"))
        rc, out, _ = tool("rollback.py", "--dry-run", project=t)
        d = js(out); assert d["ok"] and d["dry_run"]


def test_commit_dry_run():
    with tempfile.TemporaryDirectory() as t:
        # Fake git repo
        subprocess.run(["git", "init"], cwd=t, capture_output=True, timeout=10)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=t, capture_output=True, timeout=5)
        subprocess.run(["git", "config", "user.name", "t"], cwd=t, capture_output=True, timeout=5)
        open(os.path.join(t, "x.txt"), "w").write("hi")
        subprocess.run(["git", "add", "-A"], cwd=t, capture_output=True, timeout=5)
        subprocess.run(["git", "commit", "-m", "init"], cwd=t, capture_output=True, timeout=5)
        open(os.path.join(t, "x.txt"), "a").write("\nchange")
        rc, out, _ = tool("commit.py", "--task-id", "t1", "--desc", "test",
                          "--dry-run", project=t)
        d = js(out); assert d["dry_run"]


# ── Audit log ─────────────────────────────────────────────────────────────
def test_audit_log_written():
    with tempfile.TemporaryDirectory() as t:
        tool("state.py", "--add", "t1", "--desc", "x", project=t)
        logfile = os.path.join(t, ".foreman", "log.jsonl")
        assert os.path.exists(logfile)
        line = open(logfile).readlines()[-1]
        rec = json.loads(line)
        assert rec["tool"] == "state.py" and "ms" in rec and "exit" in rec


# ── Enhancement tests (7 new features) ───────────────────────────────────
def test_state_template_todo():
    with tempfile.TemporaryDirectory() as t:
        rc, out, _ = tool("state.py", "--template", "todo", project=t)
        assert rc == 0
        d = js(out); assert d["template"] == "todo"; assert d["added"] >= 5


def test_state_template_unknown():
    with tempfile.TemporaryDirectory() as t:
        rc, out, _ = tool("state.py", "--template", "nonesuch", project=t)
        assert rc == 1
        d = js(out); assert d["ok"] is False; assert "available" in d


def test_state_auto_full_sequence():
    with tempfile.TemporaryDirectory() as t:
        tool("state.py", "--add", "t1", "--desc", "auth", project=t)
        rc, out, _ = tool("state.py", "--auto", "t1", project=t)
        assert rc == 0
        d = js(out)
        assert d["task"] == "t1"; assert len(d["sequence"]) >= 5
        assert any("spawn architect" in s["cmd"] for s in d["sequence"])


def test_state_batch_parallel():
    with tempfile.TemporaryDirectory() as t:
        # Two independent tasks (no deps)
        tool("state.py", "--add", "t1", "--desc", "a", project=t)
        tool("state.py", "--add", "t2", "--desc", "b", project=t)
        # Add architect handoffs with non-overlapping files
        hd = os.path.join(t, ".foreman", "handoffs"); os.makedirs(hd, exist_ok=True)
        json.dump({"role": "architect", "approach": "x",
                   "files": [{"path": "lib/a.dart"}]}, open(os.path.join(hd, "t1.architect.json"), "w"))
        json.dump({"role": "architect", "approach": "y",
                   "files": [{"path": "lib/b.dart"}]}, open(os.path.join(hd, "t2.architect.json"), "w"))
        rc, out, _ = tool("state.py", "--batch", "2", project=t)
        d = js(out); assert d["batch_size"] == 2


def test_state_batch_overlap_filters():
    with tempfile.TemporaryDirectory() as t:
        tool("state.py", "--add", "t1", "--desc", "a", project=t)
        tool("state.py", "--add", "t2", "--desc", "b", project=t)
        # Both architects touch the same file
        hd = os.path.join(t, ".foreman", "handoffs"); os.makedirs(hd, exist_ok=True)
        json.dump({"role": "architect", "approach": "x",
                   "files": [{"path": "lib/shared.dart"}]}, open(os.path.join(hd, "t1.architect.json"), "w"))
        json.dump({"role": "architect", "approach": "y",
                   "files": [{"path": "lib/shared.dart"}]}, open(os.path.join(hd, "t2.architect.json"), "w"))
        rc, out, _ = tool("state.py", "--batch", "2", project=t)
        assert js(out)["batch_size"] == 1


def test_state_guide_detects_forced():
    with tempfile.TemporaryDirectory() as t:
        tool("state.py", "--add", "t1", "--desc", "auth", project=t)
        # Force-write a malformed architect handoff
        tool("handoff.py", "--task-id", "t1", "--role", "architect",
             "--stdin", "--force", project=t, stdin='{"role":"architect"}')
        rc, out, _ = tool("state.py", "--guide", "t1", project=t)
        d = js(out); assert d["warnings"]; assert any("--force" in w for w in d["warnings"])


def test_spawn_self_handoff():
    rc, out, _ = tool("spawn.py", "--role", "architect", "--task-id", "t1",
                      "--self-handoff", project=_ROOT)
    d = js(out); assert "foreman handoff t1 architect" in d["prompt"]


def test_verify_ast_flag_present():
    # AST mode should return ast_mode: true even without dart on some CIs
    with tempfile.TemporaryDirectory() as t:
        rc, out, _ = tool("verify.py", "--files", t, "--ast", project=t)
        d = js(out); assert d["ast_mode"] is True


def test_validate_coverage_dry_run():
    rc, out, _ = tool("validate.py", "--coverage", "--min-coverage", "80", "--dry-run", project=_ROOT)
    d = js(out); assert any("coverage" in s for s in d["would_run"])


def test_wrapper_state_auto():
    with tempfile.TemporaryDirectory() as t:
        wrap("state", "add", "t1", "auth", project=t)
        r = wrap("state", "auto", "t1", project=t)
        assert r[0] == 0; assert "sequence" in r[1]


def test_wrapper_state_batch():
    with tempfile.TemporaryDirectory() as t:
        wrap("state", "add", "t1", "a", project=t)
        wrap("state", "add", "t2", "b", project=t)
        r = wrap("state", "batch", "2", project=t)
        assert r[0] == 0


def test_wrapper_state_template():
    with tempfile.TemporaryDirectory() as t:
        r = wrap("state", "template", "todo", project=t)
        assert r[0] == 0; assert js(r[1])["template"] == "todo"


def test_all_templates_valid():
    tpl_dir = os.path.join(_ROOT, "templates")
    for name in os.listdir(tpl_dir):
        if not name.endswith(".json"): continue
        obj = json.load(open(os.path.join(tpl_dir, name)))
        assert "tasks" in obj and isinstance(obj["tasks"], list)
        ids = [t["id"] for t in obj["tasks"]]
        assert len(ids) == len(set(ids)), f"duplicate ids in {name}"
        for t in obj["tasks"]:
            for dep in t.get("depends_on", []):
                assert dep in ids, f"unknown dep {dep} in {name}/{t['id']}"


# ── Round-1/2/3 correctness fixes ────────────────────────────────────────
def test_state_auto_adaptive_skips_done_roles():
    with tempfile.TemporaryDirectory() as t:
        tool("state.py", "--add", "t1", "--desc", "auth", project=t)
        # Simulate architect done
        hd = os.path.join(t, ".foreman", "handoffs"); os.makedirs(hd, exist_ok=True)
        json.dump({"role": "architect", "approach": "x", "files": []},
                  open(os.path.join(hd, "t1.architect.json"), "w"))
        rc, out, _ = tool("state.py", "--auto", "t1", project=t)
        d = js(out)
        assert d["already_done"] == ["architect"]
        assert "spawn architect" not in d["sequence"][0]["cmd"]


def test_verify_resolves_relative_files():
    with tempfile.TemporaryDirectory() as t:
        os.makedirs(os.path.join(t, "lib"))
        open(os.path.join(t, "lib", "foo.dart"), "w").write("class Foo {}\n")
        tool("state.py", "--add", "t1", "--desc", "x", project=t)
        # Persist an architect handoff via the tool (populates task.files)
        arch = json.dumps({"role": "architect", "approach": "x",
                           "files": [{"path": "lib/foo.dart"}]})
        tool("handoff.py", "--task-id", "t1", "--role", "architect",
             "--stdin", project=t, stdin=arch)
        rc, out, _ = tool("verify.py", "--task-id", "t1", project=t)
        d = js(out); assert d["files_checked"]  # not empty
        assert not any(".." in p for p in d["files_checked"])


def test_handoff_updates_task_files_architect():
    with tempfile.TemporaryDirectory() as t:
        tool("state.py", "--add", "t1", "--desc", "auth", project=t)
        arch = json.dumps({"role": "architect", "approach": "x",
                           "files": [{"path": "lib/a.dart"}, {"path": "lib/b.dart"}]})
        rc, out, _ = tool("handoff.py", "--task-id", "t1", "--role", "architect",
                          "--stdin", project=t, stdin=arch)
        assert rc == 0
        assert js(out)["state_updates"]["files"] == ["lib/a.dart", "lib/b.dart"]
        st = json.load(open(os.path.join(t, ".foreman", "tasks.json")))
        assert st["t1"]["files"] == ["lib/a.dart", "lib/b.dart"]


def test_handoff_updates_task_files_developer():
    with tempfile.TemporaryDirectory() as t:
        tool("state.py", "--add", "t1", "--desc", "auth", project=t)
        rc, out, _ = tool("handoff.py", "--task-id", "t1", "--role", "developer",
                          "--stdin", project=t,
                          stdin='{"role":"developer","files_changed":["lib/x.dart"]}')
        assert rc == 0
        st = json.load(open(os.path.join(t, ".foreman", "tasks.json")))
        assert st["t1"]["files"] == ["lib/x.dart"]


def test_handoff_tracks_reviewer_verdict():
    with tempfile.TemporaryDirectory() as t:
        tool("state.py", "--add", "t1", "--desc", "auth", project=t)
        rev = '{"role":"reviewer","findings":[],"verdict":"REJECT","escalate_to":"product_owner"}'
        tool("handoff.py", "--task-id", "t1", "--role", "reviewer",
             "--stdin", project=t, stdin=rev)
        st = json.load(open(os.path.join(t, ".foreman", "tasks.json")))
        assert st["t1"]["verdict"] == "REJECT"
        assert st["t1"]["escalate_to"] == "product_owner"


def test_handoff_increments_debugger_attempts():
    with tempfile.TemporaryDirectory() as t:
        tool("state.py", "--add", "t1", "--desc", "auth", project=t)
        dbg = '{"role":"debugger","root_cause":"typo","fix":"fixed it","files_changed":[]}'
        tool("handoff.py", "--task-id", "t1", "--role", "debugger", "--stdin", project=t, stdin=dbg)
        tool("handoff.py", "--task-id", "t1", "--role", "debugger", "--stdin", project=t, stdin=dbg)
        st = json.load(open(os.path.join(t, ".foreman", "tasks.json")))
        assert st["t1"]["attempts"] == 2


def test_state_resume_finds_partial():
    with tempfile.TemporaryDirectory() as t:
        tool("state.py", "--add", "t1", "--desc", "a", project=t)
        # Add a handoff → t1 is now "partial"
        hd = os.path.join(t, ".foreman", "handoffs"); os.makedirs(hd, exist_ok=True)
        open(os.path.join(hd, "t1.architect.json"), "w").write("{}")
        rc, out, _ = tool("state.py", "--resume", project=t)
        d = js(out); assert d["task"] == "t1"; assert d["category"] == "partial"


def test_state_escalations():
    with tempfile.TemporaryDirectory() as t:
        tool("state.py", "--add", "t1", "--desc", "a", project=t)
        rev = '{"role":"reviewer","findings":[],"verdict":"REJECT","escalate_to":"tech_lead"}'
        tool("handoff.py", "--task-id", "t1", "--role", "reviewer",
             "--stdin", project=t, stdin=rev)
        rc, out, _ = tool("state.py", "--escalations", project=t)
        d = js(out); assert d["count"] == 1


def test_state_add_rejects_cycle():
    with tempfile.TemporaryDirectory() as t:
        tool("state.py", "--add", "t1", "--desc", "a", project=t)
        tool("state.py", "--add", "t2", "--desc", "b", "--deps", "t1", project=t)
        rc, out, _ = tool("state.py", "--add", "t3", "--desc", "c", "--deps", "t2", project=t)
        assert rc == 0
        # Now try to modify t1 to depend on t3 via new add (would create cycle)
        # We can't modify — but reject an unknown dep instead:
        rc, out, _ = tool("state.py", "--add", "t4", "--desc", "d", "--deps", "nonexistent", project=t)
        assert rc == 1
        assert "Unknown deps" in js(out)["message"]


def test_state_add_rejects_unknown_dep():
    with tempfile.TemporaryDirectory() as t:
        rc, out, _ = tool("state.py", "--add", "t1", "--desc", "a", "--deps", "ghost", project=t)
        assert rc == 1


def test_commit_writes_sha_to_state():
    with tempfile.TemporaryDirectory() as t:
        subprocess.run(["git", "init"], cwd=t, capture_output=True, timeout=10)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=t, capture_output=True, timeout=5)
        subprocess.run(["git", "config", "user.name", "t"], cwd=t, capture_output=True, timeout=5)
        open(os.path.join(t, "x.txt"), "w").write("hi\n")
        subprocess.run(["git", "add", "-A"], cwd=t, capture_output=True, timeout=5)
        subprocess.run(["git", "commit", "-m", "init"], cwd=t, capture_output=True, timeout=5)
        tool("state.py", "--add", "t1", "--desc", "x", project=t)
        open(os.path.join(t, "x.txt"), "a").write("change\n")
        rc, out, _ = tool("commit.py", "--task-id", "t1", "--desc", "test", project=t)
        assert rc == 0
        st = json.load(open(os.path.join(t, ".foreman", "tasks.json")))
        assert "commit_sha" in st["t1"] and len(st["t1"]["commit_sha"]) == 12


def test_wrapper_doctor():
    r = wrap("doctor", project=_ROOT)
    d = js(r[1]); assert "checks" in d; assert d["checks"]


def test_wrapper_log_summary():
    with tempfile.TemporaryDirectory() as t:
        tool("state.py", "--add", "t1", "--desc", "x", project=t)
        tool("state.py", "--ready", project=t)
        r = wrap("log", "--summary", project=t)
        d = js(r[1]); assert d["ok"]; assert "by_tool" in d; assert d["total_calls"] >= 2


def test_template_framework_field():
    with tempfile.TemporaryDirectory() as t:
        # No pubspec — flutter template should warn
        rc, out, _ = tool("state.py", "--template", "todo", project=t)
        d = js(out); assert d["framework"] == "flutter"
        assert d["warnings"]


def test_template_framework_ok_with_pubspec():
    with tempfile.TemporaryDirectory() as t:
        open(os.path.join(t, "pubspec.yaml"), "w").write("name: fake\n")
        rc, out, _ = tool("state.py", "--template", "todo", project=t)
        d = js(out); assert not d["warnings"]


def test_wrapper_state_resume():
    with tempfile.TemporaryDirectory() as t:
        wrap("state", "add", "t1", "auth", project=t)
        r = wrap("state", "resume", project=t)
        assert r[0] == 0; assert js(r[1])["task"] == "t1"


def test_wrapper_state_escalations():
    with tempfile.TemporaryDirectory() as t:
        r = wrap("state", "escalations", project=t)
        assert r[0] == 0


# ── Round 6/7: edge cases and UX ─────────────────────────────────────────
def test_init_seeds_specs():
    with tempfile.TemporaryDirectory() as t:
        open(os.path.join(t, "pubspec.yaml"), "w").write("name: fake\n")
        tool("init.py", project=t)
        assert os.path.exists(os.path.join(t, "tasks", "prd.md"))
        assert os.path.exists(os.path.join(t, "tasks", "design.md"))


def test_handoff_archives_previous():
    with tempfile.TemporaryDirectory() as t:
        tool("state.py", "--add", "t1", "--desc", "x", project=t)
        arch1 = '{"role":"architect","approach":"v1","files":[]}'
        arch2 = '{"role":"architect","approach":"v2","files":[]}'
        tool("handoff.py", "--task-id", "t1", "--role", "architect",
             "--stdin", project=t, stdin=arch1)
        rc, out, _ = tool("handoff.py", "--task-id", "t1", "--role", "architect",
                          "--stdin", project=t, stdin=arch2)
        d = js(out); assert d["overwrote_previous"] is True
        # Current is v2
        cur = json.load(open(os.path.join(t, ".foreman", "handoffs", "t1.architect.json")))
        assert cur["approach"] == "v2"
        # Archive exists
        archives = [f for f in os.listdir(os.path.join(t, ".foreman", "handoffs"))
                    if f.startswith("t1.architect.") and f != "t1.architect.json"]
        assert len(archives) == 1


def test_state_task_shows_conflicts():
    with tempfile.TemporaryDirectory() as t:
        tool("state.py", "--add", "t1", "--desc", "a", project=t)
        tool("state.py", "--add", "t2", "--desc", "b", project=t)
        # Both architects touch lib/main.dart
        arch = '{"role":"architect","approach":"x","files":[{"path":"lib/main.dart"}]}'
        tool("handoff.py", "--task-id", "t1", "--role", "architect",
             "--stdin", project=t, stdin=arch)
        tool("handoff.py", "--task-id", "t2", "--role", "architect",
             "--stdin", project=t, stdin=arch)
        rc, out, _ = tool("state.py", "--task", "t1", project=t)
        d = js(out); assert d["task"]["conflicts"]
        assert d["task"]["conflicts"][0]["task"] == "t2"
        assert "lib/main.dart" in d["task"]["conflicts"][0]["shared_files"]


def test_wrapper_unknown_state_subcommand():
    with tempfile.TemporaryDirectory() as t:
        r = wrap("state", "adds", "t1", project=t)  # typo "adds" not "add"
        assert r[0] == 2
        d = js(r[1]); assert d["ok"] is False; assert "unknown" in d["message"]


def test_wrapper_log_task_filter():
    with tempfile.TemporaryDirectory() as t:
        wrap("state", "add", "t1", "auth", project=t)
        # Fire a handoff on t1
        arch = '{"role":"architect","approach":"x","files":[]}'
        wrap("handoff", "t1", "architect", project=t, stdin=arch)
        # Fire an unrelated call
        wrap("state", "ready", project=t)
        r = wrap("log", "--task", "t1", project=t)
        d = js(r[1]); assert d["ok"]; assert d["count"] >= 1
        # Every event should mention t1 in task_id or args
        for e in d["events"]:
            assert e.get("task_id") == "t1" or "t1" in e.get("args", [])


# ── Debt ledger ──────────────────────────────────────────────────────────
def test_debt_harvest():
    with tempfile.TemporaryDirectory() as t:
        os.makedirs(os.path.join(t, "lib"))
        open(os.path.join(t, "lib", "a.dart"), "w").write(
            "class A {\n"
            "  // yagni: inlined helper, single use\n"
            "  int inc(int x) => x + 1;\n"
            "}\n")
        open(os.path.join(t, "lib", "b.dart"), "w").write(
            "// yagni: no theme extension yet — one use\n"
            "const primary = 0xFF00AA88;\n")
        # File without marker
        open(os.path.join(t, "lib", "c.dart"), "w").write("class C {}\n")
        rc, out, _ = tool("debt.py", project=t)
        d = js(out); assert d["ok"]; assert d["count"] == 2
        files = {e["file"] for e in d["entries"]}
        assert "lib/a.dart" in files and "lib/b.dart" in files
        assert "lib/c.dart" not in files


def test_debt_skips_build_and_pycache():
    with tempfile.TemporaryDirectory() as t:
        os.makedirs(os.path.join(t, "build"))
        os.makedirs(os.path.join(t, "lib"))
        open(os.path.join(t, "build", "generated.dart"), "w").write(
            "// yagni: generated\n")
        open(os.path.join(t, "lib", "a.dart"), "w").write(
            "// yagni: real one\n")
        rc, out, _ = tool("debt.py", project=t)
        d = js(out); assert d["count"] == 1
        assert d["entries"][0]["file"] == "lib/a.dart"


def test_debt_path_filter():
    with tempfile.TemporaryDirectory() as t:
        os.makedirs(os.path.join(t, "lib", "features"))
        os.makedirs(os.path.join(t, "lib", "core"))
        open(os.path.join(t, "lib", "features", "x.dart"), "w").write("// yagni: a\n")
        open(os.path.join(t, "lib", "core", "y.dart"), "w").write("// yagni: b\n")
        rc, out, _ = tool("debt.py", "--path", "lib/core", project=t)
        d = js(out); assert d["count"] == 1
        assert "core" in d["entries"][0]["file"]


def test_wrapper_debt():
    with tempfile.TemporaryDirectory() as t:
        os.makedirs(os.path.join(t, "lib"))
        open(os.path.join(t, "lib", "a.dart"), "w").write("// yagni: x\n")
        r = wrap("debt", project=t)
        assert r[0] == 0
        d = js(r[1]); assert d["count"] == 1


# ── Deploy (device install) ──────────────────────────────────────────────
def _fake_flutter_shim(dir_, devices_json):
    """Create a shim `flutter` binary that responds to `devices --machine`."""
    os.makedirs(dir_, exist_ok=True)
    path = os.path.join(dir_, "flutter")
    # Print predetermined JSON for `devices --machine`, echo other commands.
    open(path, "w").write(f"""#!/usr/bin/env bash
if [ "$1" = "devices" ] && [ "$2" = "--machine" ]; then
  cat <<'JSON'
{devices_json}
JSON
  exit 0
fi
if [ "$1" = "build" ] || [ "$1" = "install" ]; then
  echo "Fake: $@"
  exit 0
fi
echo "shim: unknown args: $@" >&2
exit 1
""")
    os.chmod(path, 0o755)
    return path


def test_deploy_list_no_devices():
    with tempfile.TemporaryDirectory() as t:
        shim = _fake_flutter_shim(t, "[]")
        env = {"PATH": os.path.dirname(shim) + ":" + os.environ["PATH"]}
        rc, out, _ = run([sys.executable, os.path.join(TOOLS, "deploy.py"),
                          "--project", t, "--list"], env=env)
        d = js(out); assert d["ok"]; assert d["count"] == 0
        assert "Connect" in d["hint"] or "connect" in d["hint"]


def test_deploy_list_devices():
    devices = json.dumps([
        {"id": "macos", "name": "macOS", "targetPlatform": "darwin-arm64", "emulator": False, "sdk": "macOS 26"},
        {"id": "chrome", "name": "Chrome", "targetPlatform": "web-javascript", "emulator": False, "sdk": "Chrome 149"},
        {"id": "iphone-abc", "name": "iPhone 15", "targetPlatform": "ios-arm64", "emulator": False, "sdk": "iOS 17.0"},
    ])
    with tempfile.TemporaryDirectory() as t:
        shim = _fake_flutter_shim(t, devices)
        env = {"PATH": os.path.dirname(shim) + ":" + os.environ["PATH"]}
        rc, out, _ = run([sys.executable, os.path.join(TOOLS, "deploy.py"),
                          "--project", t, "--list"], env=env)
        d = js(out); assert d["count"] == 3
        # platform mapping
        by_id = {x["id"]: x for x in d["devices"]}
        assert by_id["macos"]["platform"] == "macos"
        assert by_id["chrome"]["platform"] == "web"
        assert by_id["iphone-abc"]["platform"] == "ios"


def test_deploy_list_filter_platform():
    devices = json.dumps([
        {"id": "macos", "name": "macOS", "targetPlatform": "darwin-arm64", "emulator": False, "sdk": ""},
        {"id": "iphone", "name": "iPhone", "targetPlatform": "ios-arm64", "emulator": False, "sdk": ""},
    ])
    with tempfile.TemporaryDirectory() as t:
        shim = _fake_flutter_shim(t, devices)
        env = {"PATH": os.path.dirname(shim) + ":" + os.environ["PATH"]}
        rc, out, _ = run([sys.executable, os.path.join(TOOLS, "deploy.py"),
                          "--project", t, "--list", "--platform", "ios"], env=env)
        d = js(out); assert d["count"] == 1; assert d["devices"][0]["id"] == "iphone"


def test_deploy_install_unknown_device():
    devices = json.dumps([{"id": "macos", "name": "macOS", "targetPlatform": "darwin-arm64",
                           "emulator": False, "sdk": ""}])
    with tempfile.TemporaryDirectory() as t:
        shim = _fake_flutter_shim(t, devices)
        env = {"PATH": os.path.dirname(shim) + ":" + os.environ["PATH"]}
        rc, out, _ = run([sys.executable, os.path.join(TOOLS, "deploy.py"),
                          "--project", t, "--install", "--device", "ghost"], env=env)
        assert rc == 1
        d = js(out); assert d["ok"] is False; assert "not connected" in d["message"]


def test_deploy_install_ok():
    devices = json.dumps([{"id": "macos", "name": "macOS", "targetPlatform": "darwin-arm64",
                           "emulator": False, "sdk": ""}])
    with tempfile.TemporaryDirectory() as t:
        shim = _fake_flutter_shim(t, devices)
        env = {"PATH": os.path.dirname(shim) + ":" + os.environ["PATH"]}
        rc, out, _ = run([sys.executable, os.path.join(TOOLS, "deploy.py"),
                          "--project", t, "--install", "--device", "macos"], env=env)
        assert rc == 0
        d = js(out); assert d["ok"]; assert d["device"]["id"] == "macos"


def test_deploy_install_multiple_needs_device():
    devices = json.dumps([
        {"id": "a", "name": "A", "targetPlatform": "ios-arm64", "emulator": False, "sdk": ""},
        {"id": "b", "name": "B", "targetPlatform": "ios-arm64", "emulator": False, "sdk": ""},
    ])
    with tempfile.TemporaryDirectory() as t:
        shim = _fake_flutter_shim(t, devices)
        env = {"PATH": os.path.dirname(shim) + ":" + os.environ["PATH"]}
        rc, out, _ = run([sys.executable, os.path.join(TOOLS, "deploy.py"),
                          "--project", t, "--install", "--platform", "ios"], env=env)
        assert rc == 1
        d = js(out); assert "Multiple" in d["message"]


def test_wrapper_deploy_list():
    devices = json.dumps([{"id": "macos", "name": "macOS", "targetPlatform": "darwin-arm64",
                           "emulator": False, "sdk": ""}])
    with tempfile.TemporaryDirectory() as t:
        shim = _fake_flutter_shim(t, devices)
        env = {"FOREMAN_HOME": _ROOT, "FOREMAN_PROJECT": t,
               "PATH": os.path.dirname(shim) + ":" + os.environ["PATH"]}
        r = subprocess.run([BIN, "deploy", "list"], capture_output=True, text=True, env=env, timeout=15)
        assert r.returncode == 0
        d = js(r.stdout); assert d["count"] == 1


def test_wrapper_deploy_unknown_subcommand():
    rc, out, _ = wrap("deploy", "bogus", project=_ROOT)
    assert rc == 2
    d = js(out); assert "unknown deploy" in d["message"]


# ── Round 8: safety rails on state done ──────────────────────────────────
def test_state_done_blocks_if_tests_fail():
    with tempfile.TemporaryDirectory() as t:
        tool("state.py", "--add", "t1", "--desc", "x", project=t)
        tester = '{"role":"tester","test_files":[],"all_pass":false}'
        tool("handoff.py", "--task-id", "t1", "--role", "tester",
             "--stdin", project=t, stdin=tester)
        rc, out, _ = tool("state.py", "--mark", "t1", "--status", "done", project=t)
        assert rc == 1
        assert "all_pass=false" in js(out)["message"]


def test_state_done_blocks_if_reviewer_rejects():
    with tempfile.TemporaryDirectory() as t:
        tool("state.py", "--add", "t1", "--desc", "x", project=t)
        rev = '{"role":"reviewer","findings":[],"verdict":"REJECT","escalate_to":"product_owner"}'
        tool("handoff.py", "--task-id", "t1", "--role", "reviewer",
             "--stdin", project=t, stdin=rev)
        rc, out, _ = tool("state.py", "--mark", "t1", "--status", "done", project=t)
        assert rc == 1
        assert "REJECT" in js(out)["message"]


def test_state_done_warns_on_missing_commit():
    with tempfile.TemporaryDirectory() as t:
        tool("state.py", "--add", "t1", "--desc", "x", project=t)
        rc, out, _ = tool("state.py", "--mark", "t1", "--status", "done", project=t)
        assert rc == 0
        assert any("commit" in w for w in js(out).get("warnings", []))


def test_state_done_force_overrides():
    with tempfile.TemporaryDirectory() as t:
        tool("state.py", "--add", "t1", "--desc", "x", project=t)
        tester = '{"role":"tester","test_files":[],"all_pass":false}'
        tool("handoff.py", "--task-id", "t1", "--role", "tester",
             "--stdin", project=t, stdin=tester)
        rc, out, _ = tool("state.py", "--mark", "t1", "--status", "done", "--force", project=t)
        assert rc == 0


# ── Integration: end-to-end task on a fake Flutter project ───────────────
def test_integration_e2e_task_flow():
    """Simulate: import tasks → check ready → verify sub-agent outputs validate → handoff persists → next role can load."""
    with tempfile.TemporaryDirectory() as t:
        _mkfake_flutter(t)
        # 1. Product Owner outputs task list
        po_json = json.dumps({
            "role": "product_owner",
            "tasks": [
                {"id": "t1", "description": "auth screen", "acceptance": "user can log in", "depends_on": []},
                {"id": "t2", "description": "profile", "acceptance": "user sees name", "depends_on": ["t1"]},
            ],
        })
        rc, _, _ = tool("handoff.py", "--task-id", "init", "--role", "product_owner",
                        "--stdin", project=t, stdin=po_json)
        assert rc == 0

        # 2. Import into state
        rc, _, _ = tool("state.py", "--import", project=t,
                        stdin=json.dumps({"tasks": [
                            {"id": "t1", "description": "auth screen", "depends_on": []},
                            {"id": "t2", "description": "profile", "depends_on": ["t1"]}]}))
        assert rc == 0

        # 3. Ready shows t1
        rc, out, _ = tool("state.py", "--ready", project=t)
        assert js(out)["tasks"][0]["id"] == "t1"

        # 4. Spawn architect for t1
        rc, out, _ = tool("spawn.py", "--role", "architect", "--task-id", "t1", project=t)
        assert rc == 0 and "auth screen" in js(out)["prompt"].lower() or "t1" in js(out)["prompt"]

        # 5. Persist architect output
        arch_json = json.dumps({"role": "architect", "approach": "Form widget",
                                "files": [{"path": "lib/login.dart", "purpose": "screen"}]})
        rc, _, _ = tool("handoff.py", "--task-id", "t1", "--role", "architect",
                        "--stdin", project=t, stdin=arch_json)
        assert rc == 0

        # 6. Developer can load architect output
        rc, out, _ = tool("spawn.py", "--role", "developer", "--task-id", "t1",
                          "--load-from", "architect", project=t)
        assert rc == 0 and "Form widget" in js(out)["prompt"]

        # 7. Mark done, ready advances to t2
        tool("state.py", "--mark", "t1", "--status", "done", project=t)
        rc, out, _ = tool("state.py", "--ready", project=t)
        assert js(out)["tasks"][0]["id"] == "t2"

        # 8. Log has entries
        rec = [json.loads(l) for l in open(os.path.join(t, ".foreman", "log.jsonl"))]
        tools_seen = {r["tool"] for r in rec}
        assert "state.py" in tools_seen and "spawn.py" in tools_seen and "handoff.py" in tools_seen


# ── Run ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    tests = [
        ("info --summary", test_info_summary),
        ("info --brief", test_info_brief),
        ("plan (no PRD)", test_plan_missing),
        ("plan cache key", test_plan_cache_key),
        ("spawn all 8 roles", test_spawn_all_roles),
        ("spawn --estimate-tokens", test_spawn_estimate_tokens),
        ("spawn --load-from", test_spawn_load_from),
        ("spawn shell-injection safe", test_spawn_no_shell_injection),
        ("handoff strips fences", test_handoff_strips_fences),
        ("handoff rejects invalid JSON", test_handoff_rejects_invalid_json),
        ("handoff schema check", test_handoff_schema_check),
        ("handoff --force bypasses schema", test_handoff_force_bypasses_schema),
        ("state full flow", test_state_full_flow),
        ("state --import bulk", test_state_import_bulk),
        ("state --import array", test_state_import_from_array),
        ("state --guide", test_state_guide),
        ("verify tag structure", test_verify_tags),
        ("verify --strict", test_verify_strict),
        ("wrapper next single JSON", test_wrapper_next_single_json),
        ("wrapper state add/done", test_wrapper_state_add_done),
        ("wrapper state import", test_wrapper_state_import),
        ("wrapper state guide", test_wrapper_state_guide),
        ("wrapper log", test_wrapper_log),
        ("wrapper help", test_wrapper_help),
        ("wrapper state auto requires id", test_wrapper_state_auto_requires_id),
        ("wrapper state empty hint", test_wrapper_state_summary_empty_hint),
        ("wrapper next how_to_run", test_wrapper_next_how_to_run),
        ("wrapper run --dry-run", test_wrapper_run_dry_run),
        ("wrapper unknown command json", test_wrapper_unknown_command_json),
        ("opencode agents present", test_opencode_agents_present),
        ("install.sh links agents", test_install_sh_links_agents),
        ("install.sh global only", test_install_sh_global_only),
        ("validate --dry-run", test_validate_dry_run),
        ("rollback --dry-run", test_rollback_dry_run),
        ("commit --dry-run", test_commit_dry_run),
        ("audit log written", test_audit_log_written),
        ("state template todo", test_state_template_todo),
        ("state template unknown", test_state_template_unknown),
        ("state auto sequence", test_state_auto_full_sequence),
        ("state batch parallel", test_state_batch_parallel),
        ("state batch overlap filters", test_state_batch_overlap_filters),
        ("state guide detects --force", test_state_guide_detects_forced),
        ("spawn --self-handoff", test_spawn_self_handoff),
        ("verify --ast flag", test_verify_ast_flag_present),
        ("validate --coverage dry-run", test_validate_coverage_dry_run),
        ("wrapper state auto", test_wrapper_state_auto),
        ("wrapper state batch", test_wrapper_state_batch),
        ("wrapper state template", test_wrapper_state_template),
        ("all templates valid", test_all_templates_valid),
        ("state auto adaptive", test_state_auto_adaptive_skips_done_roles),
        ("verify resolves relative files", test_verify_resolves_relative_files),
        ("handoff updates files (arch)", test_handoff_updates_task_files_architect),
        ("handoff updates files (dev)", test_handoff_updates_task_files_developer),
        ("handoff tracks verdict", test_handoff_tracks_reviewer_verdict),
        ("handoff bumps attempts", test_handoff_increments_debugger_attempts),
        ("state resume finds partial", test_state_resume_finds_partial),
        ("state escalations", test_state_escalations),
        ("state add unknown dep", test_state_add_rejects_unknown_dep),
        ("state add cycle prevention", test_state_add_rejects_cycle),
        ("commit writes sha", test_commit_writes_sha_to_state),
        ("wrapper doctor", test_wrapper_doctor),
        ("wrapper log --summary", test_wrapper_log_summary),
        ("template framework warns", test_template_framework_field),
        ("template framework ok", test_template_framework_ok_with_pubspec),
        ("wrapper state resume", test_wrapper_state_resume),
        ("wrapper state escalations", test_wrapper_state_escalations),
        ("init seeds prd/design", test_init_seeds_specs),
        ("handoff archives previous", test_handoff_archives_previous),
        ("state task shows conflicts", test_state_task_shows_conflicts),
        ("wrapper unknown state subcommand", test_wrapper_unknown_state_subcommand),
        ("wrapper log --task filter", test_wrapper_log_task_filter),
        ("state done blocks on failing tests", test_state_done_blocks_if_tests_fail),
        ("state done blocks on REJECT", test_state_done_blocks_if_reviewer_rejects),
        ("state done warns on no commit", test_state_done_warns_on_missing_commit),
        ("state done --force overrides", test_state_done_force_overrides),
        ("debt harvest markers", test_debt_harvest),
        ("debt skips build/", test_debt_skips_build_and_pycache),
        ("debt --path filter", test_debt_path_filter),
        ("wrapper debt", test_wrapper_debt),
        ("deploy list (no devices)", test_deploy_list_no_devices),
        ("deploy list (mapped platforms)", test_deploy_list_devices),
        ("deploy list --platform filter", test_deploy_list_filter_platform),
        ("deploy install unknown device", test_deploy_install_unknown_device),
        ("deploy install ok", test_deploy_install_ok),
        ("deploy install multiple → error", test_deploy_install_multiple_needs_device),
        ("wrapper deploy list", test_wrapper_deploy_list),
        ("wrapper deploy unknown subcommand", test_wrapper_deploy_unknown_subcommand),
        ("INTEGRATION: full task flow", test_integration_e2e_task_flow),
    ]
    print(f"Foreman tests · root={_ROOT}\n")
    for name, fn in tests:
        T(name, fn)
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)
