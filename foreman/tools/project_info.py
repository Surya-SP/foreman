#!/usr/bin/env python3
"""Inspect project. Prints JSON. Detects flutter/python/node/rust/go.

Flags:
  --summary       Only counts + git (token-cheap)
  --filter PATH   Scope to subdirectory
  --since REF     Only files changed since git ref (latest-commit, HEAD~3)
  --lines N       Truncate file list to N entries
  --brief         One-line summary of framework + file count
"""
import json, os, re, subprocess, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..")))

from foreman.sdk import detect_sdk
from foreman import memory as mem

def _arg(name, default=None):
    return next((sys.argv[i+1] for i,a in enumerate(sys.argv) if a==name), default)

target = os.path.abspath(_arg("--project") or os.environ.get("FOREMAN_PROJECT") or ".")
no_cache = "--no-cache" in sys.argv

FRAMEWORKS = [
    ("flutter", "pubspec.yaml", (".dart",)),
    ("python", "pyproject.toml", (".py",)),
    ("node", "package.json", (".ts", ".tsx", ".js", ".jsx")),
    ("rust", "Cargo.toml", (".rs",)),
    ("go", "go.mod", (".go",)),
]

def _framework(path):
    for name, marker, exts in FRAMEWORKS:
        if os.path.exists(os.path.join(path, marker)):
            return name, exts
    return "unknown", (".py", ".js", ".ts", ".dart", ".rs", ".go")

def _pubspec_deps(path):
    p = os.path.join(path, "pubspec.yaml")
    if not os.path.exists(p): return []
    deps, in_deps = [], False
    for line in open(p):
        if re.match(r"^(dependencies|dev_dependencies):", line):
            in_deps = True; continue
        if in_deps:
            if re.match(r"^\S", line): in_deps = False; continue
            m = re.match(r"^  ([a-zA-Z0-9_]+):", line)
            if m: deps.append(m.group(1))
    return sorted(set(deps))

def _source_files(path, exts, subdir=None):
    base = os.path.join(path, subdir) if subdir else path
    if not os.path.isdir(base): return []
    out = []
    for root, _d, names in os.walk(base):
        if "/.git/" in root or "/build/" in root or "/.dart_tool/" in root:
            continue
        for n in names:
            if any(n.endswith(e) for e in exts):
                out.append(os.path.relpath(os.path.join(root, n), path))
    return sorted(out)

def _git(target):
    if not os.path.isdir(os.path.join(target, ".git")):
        return {"repo": False}
    try:
        run = lambda a: subprocess.run(["git", *a], capture_output=True, text=True, timeout=5, cwd=target)
        return {"repo": True,
                "branch": run(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip(),
                "dirty": bool(run(["status", "--porcelain"]).stdout.strip()),
                "recent": run(["log", "--oneline", "-3"]).stdout.strip()}
    except Exception:
        return {"repo": True, "error": "git failed"}

def _changed(path, ref):
    if ref == "latest-commit": ref = "HEAD~1"
    try:
        out = subprocess.run(["git", "diff", "--name-only", ref], capture_output=True, text=True, timeout=5, cwd=path)
        return [f for f in out.stdout.strip().splitlines() if f]
    except Exception:
        return []

framework, exts = _framework(target)
since = _arg("--since")
subdir = _arg("--filter")
lines = _arg("--lines")
lines = int(lines) if lines else None

if "--brief" in sys.argv:
    n = len(_source_files(target, exts))
    g = _git(target)
    print(f"{framework} · {n} files · {g.get('branch','no-git')}{' (dirty)' if g.get('dirty') else ''}")
    sys.exit(0)

result = {"ok": True, "framework": framework, "project_dir": target}

# Watch pubspec + (flutter) for cache invalidation; source list uses walk so
# also watch project root mtime via pubspec + optional lib dir.
_watch = [
    os.path.join(target, m)
    for _n, m, _e in FRAMEWORKS
    if os.path.exists(os.path.join(target, m))
]
lib_dir = os.path.join(target, "lib")
if os.path.isdir(lib_dir):
    _watch.append(lib_dir)
_key = ["summary" if "--summary" in sys.argv else "full", since or "", subdir or "", str(lines or "")]

if not no_cache and "--brief" not in sys.argv:
    hit = mem.tool_cache_get(target, "project_info", _key, _watch)
    if hit is not None:
        hit = dict(hit)
        hit["_cache"] = "hit"
        json.dump(hit, sys.stdout, indent=2)
        sys.exit(0)

if "--summary" in sys.argv:
    result["sdk"] = detect_sdk() if framework == "flutter" else {}
    if framework == "flutter":
        result["packages_count"] = len(_pubspec_deps(target))
    result["source_file_count"] = len(_source_files(target, exts))
    result["git"] = _git(target)
    result["_cache"] = "miss"
    if not no_cache:
        try:
            mem.tool_cache_set(target, "project_info", _key, _watch, result)
        except OSError:
            pass
    json.dump(result, sys.stdout, indent=2)
    sys.exit(0)

result["sdk"] = detect_sdk() if framework == "flutter" else {}
if framework == "flutter":
    result["packages"] = _pubspec_deps(target)

if since:
    result["changed_files"] = _changed(target, since)
else:
    files = _source_files(target, exts, subdir)
    result["source_file_count"] = len(files)
    result["source_files"] = files[:lines] if lines else files
    result["git"] = _git(target)

result["_cache"] = "miss"
if not no_cache:
    try:
        mem.tool_cache_set(target, "project_info", _key, _watch, result)
    except OSError:
        pass
json.dump(result, sys.stdout, indent=2)
