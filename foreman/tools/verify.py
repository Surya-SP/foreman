#!/usr/bin/env python3
"""Design-drift check. Findings tagged: class|method|route|import|color|missing_test.

Flags:
  --task-id ID   Read files list from .foreman/tasks.json
  --files ...    Verify specific files/directories
  --strict       Fail on ANY finding (default: only critical tags fail)
  --lines N      Truncate output
"""
import json, os, re, shutil, subprocess, sys, time
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..")))

from foreman.log import log

_start = time.time()

# Which tags trip failure by default (non-strict).
CRITICAL_TAGS = {"class", "route", "color", "missing_test", "analyzer_error"}


def _ast_analyze(project_dir):
    """Run dart analyze --format=json. Return list of {file, line, severity, code, message}.

    Returns [] if dart is not available or analyze fails to parse.
    """
    if not shutil.which("dart"):
        return None
    try:
        r = subprocess.run(["dart", "analyze", "--format=json"],
                           cwd=project_dir, capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, OSError):
        return None
    # dart analyze --format=json exits non-zero when it finds problems but still emits JSON.
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        diagnostics = payload.get("diagnostics", [])
        out = []
        for d in diagnostics:
            loc = d.get("location", {})
            out.append({
                "file": loc.get("file", ""),
                "line": loc.get("range", {}).get("start", {}).get("line"),
                "severity": d.get("severity", "INFO"),
                "code": d.get("code", ""),
                "message": d.get("problemMessage", "")[:180],
            })
        return out
    return []

def _arg(name, default=None):
    return next((sys.argv[i+1] for i,a in enumerate(sys.argv) if a==name), default)

target = os.path.abspath(_arg("--project") or os.environ.get("FOREMAN_PROJECT") or ".")
task_id = _arg("--task-id")
strict = "--strict" in sys.argv
ast_mode = "--ast" in sys.argv or "--ast-only" in sys.argv
ast_only = "--ast-only" in sys.argv

file_args = []
if "--files" in sys.argv:
    i = sys.argv.index("--files")
    file_args = [f for f in sys.argv[i+1:] if not f.startswith("--")]

def _out(obj, code):
    json.dump(obj, sys.stdout, indent=2)
    log(os.path.join(target, ".foreman"), "verify.py", code, int((time.time()-_start)*1000))
    sys.exit(code)

design_path = os.path.join(target, "tasks", "design.md")
design = open(design_path).read() if os.path.exists(design_path) else ""

def _in_design(pattern):
    return bool(re.search(pattern, design, re.IGNORECASE))

files = list(file_args)
if not files and task_id:
    sp = os.path.join(target, ".foreman", "tasks.json")
    if os.path.exists(sp):
        try:
            files = json.load(open(sp)).get(task_id, {}).get("files", [])
        except (json.JSONDecodeError, OSError): pass
    # Also try developer handoff which stores files_changed
    hp = os.path.join(target, ".foreman", "handoffs", f"{task_id}.developer.json")
    if os.path.exists(hp):
        try:
            files.extend(json.load(open(hp)).get("files_changed", []))
        except (json.JSONDecodeError, OSError): pass
if not files:
    lib = os.path.join(target, "lib")
    files = [lib] if os.path.isdir(lib) else []

# Resolve relative paths against the project, not CWD.
files = [f if os.path.isabs(f) else os.path.join(target, f) for f in files]
files = list(dict.fromkeys(files))  # dedupe, preserve order

def _test_exists(filepath):
    rel = os.path.relpath(filepath, target)
    if not rel.startswith(("lib/", "lib\\")): return True
    stem = os.path.splitext(rel)[0].replace("lib/", "").replace("lib\\", "")
    candidates = [
        os.path.join(target, "test", stem + "_test.dart"),
        os.path.join(target, "test", os.path.dirname(stem), os.path.basename(stem) + "_test.dart"),
    ]
    return any(os.path.exists(p) for p in candidates)

def _scan(filepath):
    if not os.path.isfile(filepath):
        return {"path": filepath, "exists": False, "findings": [{"tag": "missing", "message": "File not found"}]}
    try:
        content = open(filepath).read()
    except OSError:
        return {"path": filepath, "exists": False, "findings": [{"tag": "missing", "message": "Read error"}]}

    rel = os.path.relpath(filepath, target)
    findings = []

    for cls in re.findall(r"class\s+(\w+)", content):
        if cls in ("MyApp", "MyHomePage"): continue
        if not _in_design(re.escape(cls)):
            findings.append({"tag": "class", "message": f"Class '{cls}' not in design.md"})

    for fn in re.findall(r"(?:Future<[^>]+>|void|Widget|String|int|bool|double)\s+(\w+)\s*\(", content):
        if fn.startswith("_") or fn in ("build","initState","dispose","setState","createState","didChangeDependencies","toString","hashCode","operator"):
            continue
        if not _in_design(re.escape(fn)):
            findings.append({"tag": "method", "message": f"Method '{fn}' not in design.md"})

    for route in re.findall(r"['\"]/([\w/-]+)['\"]", content):
        if not _in_design(route):
            findings.append({"tag": "route", "message": f"Route '/{route}' not in design.md"})

    for imp in re.findall(r"import\s+'package:([\w_]+)/", content):
        if not _in_design(re.escape(imp)):
            findings.append({"tag": "import", "message": f"Package '{imp}' not in design.md"})

    colors = re.findall(r"Color\(0x([0-9a-fA-F]+)\)", content)
    if colors and design:
        design_colors = set(re.findall(r"(?:Primary|Secondary|Error|Background|Surface).*?([0-9a-fA-F]{6,8})", design, re.IGNORECASE))
        for c in colors:
            if design_colors and not any(c.upper() in d.upper() for d in design_colors):
                findings.append({"tag": "color", "message": f"Color 0x{c} not in design.md"})

    if rel.startswith(("lib/", "lib\\")) and not _test_exists(filepath):
        if not any(x in rel for x in ("main.dart", "generated", ".g.dart", ".freezed.dart")):
            findings.append({"tag": "missing_test", "message": f"No test file for {rel}"})

    return {"path": rel, "exists": True, "findings": findings}

scanned = []
for f in files:
    if os.path.isfile(f) and f.endswith(".dart"):
        scanned.append(_scan(f))
    elif os.path.isdir(f):
        for base, _d, names in os.walk(f):
            if "/build/" in base or "/.dart_tool/" in base: continue
            for n in names:
                if n.endswith(".dart") and not n.endswith((".g.dart", ".freezed.dart")):
                    scanned.append(_scan(os.path.join(base, n)))

all_findings = [] if ast_only else [f for s in scanned for f in s.get("findings", [])]
ast_diagnostics = None
if ast_mode:
    ast_diagnostics = _ast_analyze(target)
    if ast_diagnostics is None:
        ast_diagnostics = []  # dart not available or parse failure — regex-only fallback
    for d in ast_diagnostics:
        sev = (d.get("severity") or "").upper()
        if sev in ("ERROR", "WARNING"):
            all_findings.append({
                "tag": "analyzer_error" if sev == "ERROR" else "analyzer_warning",
                "file": d.get("file", ""),
                "line": d.get("line"),
                "message": f"[{d.get('code','')}] {d.get('message','')}",
            })

critical = [f for f in all_findings if f["tag"] in CRITICAL_TAGS]
by_tag = {}
for f in all_findings:
    by_tag[f["tag"]] = by_tag.get(f["tag"], 0) + 1

fail = len(all_findings) > 0 if strict else len(critical) > 0
result = {
    "ok": not fail,
    "task_id": task_id or "",
    "design_exists": bool(design),
    "files_checked": [s["path"] for s in scanned if s.get("exists")],
    "total_findings": len(all_findings),
    "critical_findings": len(critical),
    "by_tag": by_tag,
    "findings": all_findings[:30],
    "ast_mode": ast_mode,
    "ast_diagnostics_count": len(ast_diagnostics) if ast_diagnostics is not None else 0,
}
_out(result, 0 if not fail else 1)
