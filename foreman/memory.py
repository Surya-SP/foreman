"""Drift-proof project memory: decisions, graph, tool cache, retrieval.

Rules (hard):
- Only store facts extracted from handoff JSON keys or tool/rg output.
- Every node cites source path + content_hash. No free-text inventing.
- Retrieval is keyword/file/task match against stored nodes only.
- Tool cache keys include input mtimes; stale mtime = miss.
- All injected strings are hard-capped (token budget).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from typing import Any

# ── Hard caps (chars) ───────────────────────────────────────────────────────
MAX_ERROR = 4000
MAX_DIFF = 8000
MAX_HANDOFF_INJECT = 6000
MAX_MEMORY_BLOCK = 2800
MAX_DECISION = 500
MAX_REASONING = 800
MAX_NODE_TEXT = 600
MAX_FINDING = 300
MAX_GRAPH_NODES = 400
MAX_DECISIONS_FILE = 300  # lines kept in decisions.jsonl
MAX_RG_HITS = 40
MAX_RG_LINE = 200
CACHE_MAX_ENTRIES = 64

GRAPH_NAME = "graph.json"
DECISIONS_NAME = "decisions.jsonl"
CACHE_NAME = "tool_cache.json"
META_NAME = "meta.json"


def memory_dir(project: str) -> str:
    d = os.path.join(os.path.abspath(project), ".foreman", "memory")
    os.makedirs(d, exist_ok=True)
    return d


def truncate(s: str | None, n: int) -> str:
    if s is None:
        return ""
    s = str(s)
    if len(s) <= n:
        return s
    return s[: max(0, n - 20)] + f"\n…[truncated {len(s)} chars]"


def content_hash(data: Any) -> str:
    raw = data if isinstance(data, (bytes, bytearray)) else json.dumps(
        data, sort_keys=True, default=str
    ).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def _read_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    try:
        return json.load(open(path))
    except (json.JSONDecodeError, OSError):
        return default


def _write_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2, default=str)
    os.replace(tmp, path)


def _graph_path(project: str) -> str:
    return os.path.join(memory_dir(project), GRAPH_NAME)


def _decisions_path(project: str) -> str:
    return os.path.join(memory_dir(project), DECISIONS_NAME)


def _cache_path(project: str) -> str:
    return os.path.join(memory_dir(project), CACHE_NAME)


def load_graph(project: str) -> dict:
    g = _read_json(_graph_path(project), {"version": 1, "nodes": {}, "edges": []})
    if "nodes" not in g:
        g["nodes"] = {}
    if "edges" not in g:
        g["edges"] = []
    return g


def save_graph(project: str, graph: dict) -> None:
    nodes = graph.get("nodes") or {}
    if len(nodes) > MAX_GRAPH_NODES:
        # Drop oldest by ts
        ordered = sorted(nodes.items(), key=lambda kv: float(kv[1].get("ts") or 0))
        drop = len(nodes) - MAX_GRAPH_NODES
        for nid, _ in ordered[:drop]:
            nodes.pop(nid, None)
        graph["nodes"] = nodes
        graph["edges"] = [
            e for e in graph.get("edges", [])
            if e.get("from") in nodes and e.get("to") in nodes
        ]
    graph["updated_at"] = time.time()
    _write_json(_graph_path(project), graph)


# ── ripgrep ─────────────────────────────────────────────────────────────────

def find_rg() -> str | None:
    return shutil.which("rg") or shutil.which("ripgrep")


def ensure_rg() -> dict:
    """Locate rg. Does not install (install.sh does). Returns status dict."""
    path = find_rg()
    if path:
        try:
            v = subprocess.run(
                [path, "--version"], capture_output=True, text=True, timeout=5
            )
            ver = (v.stdout or v.stderr or "").splitlines()[0] if v.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            ver = ""
        return {"ok": True, "path": path, "version": ver}
    return {
        "ok": False,
        "path": None,
        "message": "ripgrep (rg) not found",
        "hint": "brew install ripgrep  |  apt install ripgrep  |  re-run ./install.sh",
    }


def rg_search(
    project: str,
    pattern: str,
    glob: str | None = None,
    max_hits: int = MAX_RG_HITS,
) -> dict:
    """Search codebase with rg. Returns only file:line:text hits (factual)."""
    rg = find_rg()
    if not rg:
        return {"ok": False, "hits": [], "message": "rg not installed", **ensure_rg()}
    if not pattern or not pattern.strip():
        return {"ok": False, "hits": [], "message": "empty pattern"}
    cmd = [
        rg, "--json", "--max-count", "5", "-m", str(max_hits),
        "--hidden", "--glob", "!.git", "--glob", "!build", "--glob", "!.dart_tool",
        "--glob", "!.foreman", "--glob", "!node_modules",
    ]
    if glob:
        cmd += ["--glob", glob]
    cmd += ["--", pattern, os.path.abspath(project)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "hits": [], "message": str(e)}
    hits = []
    for line in (r.stdout or "").splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") != "match":
            continue
        data = ev.get("data") or {}
        path = (data.get("path") or {}).get("text") or ""
        line_no = (data.get("line_number") or 0)
        text = (data.get("lines") or {}).get("text") or ""
        text = truncate(text.rstrip("\n"), MAX_RG_LINE)
        rel = os.path.relpath(path, project) if path.startswith(project) else path
        hits.append({"file": rel, "line": line_no, "text": text})
        if len(hits) >= max_hits:
            break
    return {"ok": True, "hits": hits, "count": len(hits), "pattern": pattern, "rg": rg}


# ── Tool cache (mtime-proof) ────────────────────────────────────────────────

def _paths_fingerprint(paths: list[str]) -> str:
    parts = []
    for p in paths:
        try:
            st = os.stat(p)
            parts.append(f"{p}:{st.st_mtime_ns}:{st.st_size}")
        except OSError:
            parts.append(f"{p}:missing")
    return content_hash("|".join(parts))


def tool_cache_get(project: str, tool: str, key_parts: list[str], watch_paths: list[str]) -> Any | None:
    cache = _read_json(_cache_path(project), {})
    fp = _paths_fingerprint(watch_paths)
    k = content_hash([tool, *key_parts, fp])
    ent = cache.get(k)
    if not ent:
        return None
    if ent.get("fp") != fp:
        return None
    return ent.get("value")


def tool_cache_set(
    project: str, tool: str, key_parts: list[str], watch_paths: list[str], value: Any
) -> None:
    cache = _read_json(_cache_path(project), {})
    fp = _paths_fingerprint(watch_paths)
    k = content_hash([tool, *key_parts, fp])
    cache[k] = {"fp": fp, "tool": tool, "ts": time.time(), "value": value}
    if len(cache) > CACHE_MAX_ENTRIES:
        # drop oldest
        items = sorted(cache.items(), key=lambda kv: float(kv[1].get("ts") or 0))
        for old_k, _ in items[: len(cache) - CACHE_MAX_ENTRIES]:
            cache.pop(old_k, None)
    _write_json(_cache_path(project), cache)


def tool_cache_clear(project: str) -> dict:
    path = _cache_path(project)
    if os.path.exists(path):
        os.remove(path)
    return {"ok": True, "cleared": True}


# ── Decision + graph recording ──────────────────────────────────────────────

def _node_id(kind: str, source: str, text: str) -> str:
    return content_hash(f"{kind}|{source}|{text}")


def _add_node(graph: dict, node: dict) -> str:
    nid = node["id"]
    graph.setdefault("nodes", {})[nid] = node
    return nid


def _add_edge(graph: dict, frm: str, to: str, rel: str) -> None:
    edges = graph.setdefault("edges", [])
    e = {"from": frm, "to": to, "rel": rel}
    if e not in edges:
        edges.append(e)


def _append_decision(project: str, rec: dict) -> None:
    path = _decisions_path(project)
    with open(path, "a") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    try:
        with open(path) as f:
            lines = f.readlines()
        if len(lines) > MAX_DECISIONS_FILE:
            with open(path, "w") as f:
                f.writelines(lines[-MAX_DECISIONS_FILE:])
    except OSError:
        pass


def _extract_decisions(role: str, obj: dict) -> list[dict]:
    """Pull only schema-backed decision-like fields. No paraphrasing."""
    out: list[dict] = []
    if role == "developer":
        for d in obj.get("decisions") or []:
            if isinstance(d, str) and d.strip():
                out.append({"text": truncate(d, MAX_DECISION), "field": "decisions"})
        for d in obj.get("yagni_notes") or []:
            if isinstance(d, str) and d.strip():
                out.append({"text": truncate(d, MAX_DECISION), "field": "yagni_notes"})
        if obj.get("summary"):
            out.append({"text": truncate(str(obj["summary"]), MAX_DECISION), "field": "summary"})
    elif role == "architect":
        if obj.get("approach"):
            out.append({"text": truncate(str(obj["approach"]), MAX_DECISION), "field": "approach"})
        if obj.get("design_drift") and str(obj.get("design_drift")).lower() not in ("none", ""):
            out.append({
                "text": truncate(f"design_drift: {obj['design_drift']}", MAX_DECISION),
                "field": "design_drift",
            })
        if obj.get("state_shape"):
            out.append({
                "text": truncate(str(obj["state_shape"]), MAX_DECISION),
                "field": "state_shape",
            })
    elif role == "debugger":
        if obj.get("root_cause"):
            out.append({
                "text": truncate(str(obj["root_cause"]), MAX_DECISION),
                "field": "root_cause",
            })
        if obj.get("fix"):
            out.append({"text": truncate(str(obj["fix"]), MAX_DECISION), "field": "fix"})
    elif role == "reviewer":
        if obj.get("verdict"):
            out.append({"text": truncate(f"verdict={obj['verdict']}", MAX_DECISION), "field": "verdict"})
        for fnd in (obj.get("findings") or [])[:8]:
            if isinstance(fnd, dict):
                t = fnd.get("message") or fnd.get("issue") or json.dumps(fnd, default=str)
            else:
                t = str(fnd)
            out.append({"text": truncate(t, MAX_FINDING), "field": "findings"})
    elif role == "tester":
        out.append({
            "text": truncate(f"all_pass={obj.get('all_pass')}", MAX_DECISION),
            "field": "all_pass",
        })
    elif role == "qa_lead":
        if obj.get("test_strategy"):
            out.append({
                "text": truncate(str(obj["test_strategy"]), MAX_DECISION),
                "field": "test_strategy",
            })
    elif role == "refactorer":
        for fx in (obj.get("fixes_applied") or [])[:10]:
            out.append({"text": truncate(str(fx), MAX_DECISION), "field": "fixes_applied"})
    elif role == "product_owner":
        for q in (obj.get("open_questions") or [])[:5]:
            out.append({"text": truncate(str(q), MAX_DECISION), "field": "open_questions"})
        for c in (obj.get("scope_cuts") or [])[:5]:
            out.append({"text": truncate(str(c), MAX_DECISION), "field": "scope_cuts"})
    return out


def _files_from_obj(role: str, obj: dict) -> list[str]:
    files: list[str] = []
    if role == "architect":
        for f in obj.get("files") or []:
            p = f.get("path") if isinstance(f, dict) else f
            if p:
                files.append(str(p))
    elif role in ("developer", "debugger", "refactorer"):
        key = "files_changed" if role != "refactorer" else "files_changed"
        for p in obj.get(key) or obj.get("files") or []:
            if isinstance(p, str):
                files.append(p)
            elif isinstance(p, dict) and p.get("path"):
                files.append(str(p["path"]))
    elif role == "tester":
        for p in obj.get("test_files") or []:
            files.append(str(p))
    return files[:40]


def record_handoff(project: str, task_id: str, role: str, obj: dict, handoff_path: str) -> dict:
    """Ingest a validated handoff into graph + decisions.jsonl. Factual only."""
    if not isinstance(obj, dict):
        return {"ok": False, "message": "obj not dict"}
    project = os.path.abspath(project)
    ch = content_hash(obj)
    source = {
        "type": "handoff",
        "path": os.path.relpath(handoff_path, project) if handoff_path.startswith(project)
        else handoff_path,
        "role": role,
        "task_id": task_id,
        "content_hash": ch,
    }
    files = _files_from_obj(role, obj)
    graph = load_graph(project)
    ts = time.time()
    handoff_nid = _node_id("handoff", source["path"], ch)
    _add_node(graph, {
        "id": handoff_nid,
        "kind": "handoff",
        "text": truncate(f"{role} handoff for {task_id}", MAX_NODE_TEXT),
        "source": source,
        "task_id": task_id,
        "role": role,
        "files": files,
        "ts": ts,
        "content_hash": ch,
    })
    recorded = 0
    for dec in _extract_decisions(role, obj):
        text = dec["text"]
        nid = _node_id("decision", source["path"] + dec["field"], text)
        _add_node(graph, {
            "id": nid,
            "kind": "decision",
            "text": text,
            "field": dec["field"],
            "source": source,
            "task_id": task_id,
            "role": role,
            "files": files,
            "ts": ts,
            "content_hash": content_hash(text),
        })
        _add_edge(graph, handoff_nid, nid, "asserts")
        _append_decision(project, {
            "ts": ts,
            "task_id": task_id,
            "role": role,
            "field": dec["field"],
            "text": text,
            "files": files,
            "source": source,
            "node_id": nid,
        })
        recorded += 1
        for fp in files:
            fid = _node_id("file", fp, fp)
            _add_node(graph, {
                "id": fid,
                "kind": "file",
                "text": fp,
                "source": source,
                "task_id": task_id,
                "files": [fp],
                "ts": ts,
                "content_hash": content_hash(fp),
            })
            _add_edge(graph, nid, fid, "touches")

    # Task node link
    tid_node = _node_id("task", task_id, task_id)
    _add_node(graph, {
        "id": tid_node,
        "kind": "task",
        "text": task_id,
        "source": source,
        "task_id": task_id,
        "files": files,
        "ts": ts,
        "content_hash": content_hash(task_id),
    })
    _add_edge(graph, tid_node, handoff_nid, "produced")

    save_graph(project, graph)
    meta = _read_json(os.path.join(memory_dir(project), META_NAME), {})
    meta["last_handoff"] = {"task_id": task_id, "role": role, "ts": ts, "hash": ch}
    meta["nodes"] = len(graph.get("nodes") or {})
    _write_json(os.path.join(memory_dir(project), META_NAME), meta)
    return {"ok": True, "decisions_recorded": recorded, "node_id": handoff_nid, "content_hash": ch}


def rebuild_from_handoffs(project: str) -> dict:
    """Rebuild graph from existing .foreman/handoffs/*.json (skip archives with extra dots)."""
    project = os.path.abspath(project)
    hdir = os.path.join(project, ".foreman", "handoffs")
    # reset graph + decisions
    _write_json(_graph_path(project), {"version": 1, "nodes": {}, "edges": []})
    dp = _decisions_path(project)
    if os.path.exists(dp):
        os.remove(dp)
    if not os.path.isdir(hdir):
        return {"ok": True, "ingested": 0, "message": "no handoffs dir"}
    n = 0
    errors = []
    for name in sorted(os.listdir(hdir)):
        if not name.endswith(".json") or name.startswith("."):
            continue
        # current handoffs: <task>.<role>.json  (exactly 2 dots in basename parts)
        parts = name[:-5].split(".")
        if len(parts) != 2:
            continue  # skip timestamped archives task.role.ts.json
        task_id, role = parts[0], parts[1]
        path = os.path.join(hdir, name)
        try:
            obj = json.load(open(path))
        except (json.JSONDecodeError, OSError) as e:
            errors.append({"file": name, "error": str(e)})
            continue
        if not isinstance(obj, dict):
            continue
        record_handoff(project, task_id, role, obj, path)
        n += 1
    return {"ok": True, "ingested": n, "errors": errors, "nodes": len(load_graph(project).get("nodes") or {})}


# ── Retrieval (keyword only — no LLM) ───────────────────────────────────────

_TOKEN = re.compile(r"[a-zA-Z0-9_./-]{2,}")


def _tokens(s: str) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(s or "")}


def retrieve(
    project: str,
    *,
    role: str = "",
    task_id: str = "",
    query: str = "",
    files: list[str] | None = None,
    limit: int = 12,
) -> dict:
    """Return relevant memory nodes for a role/task. Factual store only."""
    project = os.path.abspath(project)
    graph = load_graph(project)
    nodes = list((graph.get("nodes") or {}).values())
    files = files or []
    qtok = _tokens(query) | _tokens(task_id) | _tokens(" ".join(files))
    # Role-specific bias: prefer decision kinds
    prefer_fields = {
        "architect": {"approach", "design_drift", "state_shape", "summary", "decisions"},
        "developer": {"approach", "decisions", "yagni_notes", "state_shape", "summary"},
        "debugger": {"root_cause", "fix", "findings", "verdict"},
        "reviewer": {"decisions", "yagni_notes", "approach", "summary"},
        "tester": {"test_strategy", "all_pass"},
        "qa_lead": {"approach", "test_strategy"},
        "refactorer": {"findings", "verdict", "yagni_notes"},
        "product_owner": {"scope_cuts", "open_questions"},
    }.get(role, set())

    scored: list[tuple[float, dict]] = []
    for node in nodes:
        if node.get("kind") not in ("decision", "handoff", "file"):
            if node.get("kind") != "task":
                continue
        score = 0.0
        ntask = node.get("task_id") or ""
        if task_id and ntask == task_id:
            score += 5.0
        nfiles = set(node.get("files") or [])
        if files and nfiles & set(files):
            score += 3.0 * len(nfiles & set(files))
        text = str(node.get("text") or "")
        ntok = _tokens(text) | _tokens(ntask) | _tokens(" ".join(nfiles))
        overlap = len(qtok & ntok)
        score += float(overlap)
        field = node.get("field") or ""
        if field in prefer_fields:
            score += 1.5
        if node.get("kind") == "decision":
            score += 0.5
        if score > 0:
            scored.append((score, node))

    scored.sort(key=lambda x: (-x[0], -float(x[1].get("ts") or 0)))
    picked = [n for _, n in scored[:limit]]

    # Always include last decisions for same task even if score low
    if task_id:
        same = [
            n for n in nodes
            if n.get("task_id") == task_id and n.get("kind") == "decision"
        ]
        same.sort(key=lambda n: -float(n.get("ts") or 0))
        for n in same[:4]:
            if n not in picked:
                picked.append(n)

    return {
        "ok": True,
        "count": len(picked),
        "items": [
            {
                "kind": n.get("kind"),
                "text": n.get("text"),
                "field": n.get("field"),
                "task_id": n.get("task_id"),
                "role": n.get("role") or (n.get("source") or {}).get("role"),
                "files": n.get("files") or [],
                "source": n.get("source"),
                "content_hash": n.get("content_hash"),
            }
            for n in picked[:limit]
        ],
    }


def format_memory_block(retrieved: dict) -> str:
    """Compact, labeled facts for prompt injection. Empty if nothing stored."""
    items = retrieved.get("items") or []
    if not items:
        return ""
    lines = [
        "FACTS FROM .foreman/memory (disk only — do not invent beyond these):",
    ]
    for it in items:
        src = it.get("source") or {}
        cite = f"{src.get('path', '?')}#{src.get('content_hash', '')[:8]}"
        lines.append(
            f"- [{it.get('kind')}/{it.get('field') or it.get('role') or '-'}] "
            f"{truncate(it.get('text'), 220)} "
            f"(task={it.get('task_id') or '-'} src={cite})"
        )
    block = "\n".join(lines)
    return truncate(block, MAX_MEMORY_BLOCK)


def list_decisions(project: str, task_id: str | None = None, limit: int = 30) -> dict:
    path = _decisions_path(project)
    if not os.path.exists(path):
        return {"ok": True, "decisions": [], "count": 0}
    rows = []
    try:
        for line in open(path):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if task_id and rec.get("task_id") != task_id:
                continue
            rows.append(rec)
    except OSError:
        return {"ok": False, "decisions": [], "message": "read failed"}
    rows = rows[-limit:]
    return {"ok": True, "decisions": rows, "count": len(rows)}


def stats(project: str) -> dict:
    project = os.path.abspath(project)
    g = load_graph(project)
    nodes = g.get("nodes") or {}
    by_kind: dict[str, int] = {}
    for n in nodes.values():
        k = n.get("kind") or "?"
        by_kind[k] = by_kind.get(k, 0) + 1
    dec = list_decisions(project, limit=MAX_DECISIONS_FILE)
    cache = _read_json(_cache_path(project), {})
    rg = ensure_rg()
    return {
        "ok": True,
        "project": project,
        "nodes": len(nodes),
        "edges": len(g.get("edges") or []),
        "by_kind": by_kind,
        "decisions": dec.get("count", 0),
        "tool_cache_entries": len(cache),
        "rg": rg,
        "paths": {
            "graph": _graph_path(project),
            "decisions": _decisions_path(project),
            "cache": _cache_path(project),
        },
    }


def inject_caps(
    *,
    loaded_plan: str = "",
    error: str = "",
    diff: str = "",
) -> dict[str, str]:
    """Apply hard caps to spawn inject fields."""
    return {
        "loaded_plan": truncate(loaded_plan, MAX_HANDOFF_INJECT),
        "error": truncate(error, MAX_ERROR),
        "diff": truncate(diff, MAX_DIFF),
    }
