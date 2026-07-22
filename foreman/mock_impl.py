"""Deterministic mock implementations for prove/CI (no LLM).

Writes real Dart that matches a fixed design primary and the todo template
task graph. Used only when execute --mock / prove runs.
"""
from __future__ import annotations

import os
from typing import Any

PRIMARY = "0xFF2196F3"
PRIMARY_HEX = "2196F3"


def _pkg_name(project: str) -> str:
    pub = os.path.join(project, "pubspec.yaml")
    if os.path.exists(pub):
        try:
            for line in open(pub, encoding="utf-8", errors="ignore"):
                if line.startswith("name:"):
                    return line.split(":", 1)[1].strip() or "prove_app"
        except OSError:
            pass
    return "prove_app"


def _w(project: str, rel: str, body: str) -> str:
    path = os.path.join(project, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write(body)
    return rel


def apply_developer(project: str, task_id: str, desc: str = "") -> list[str]:
    """Write/update files for one task. Returns relative paths changed."""
    project = os.path.abspath(project)
    changed: list[str] = []
    blob = f"{task_id} {desc}".lower()

    # Always ensure package + entry exist for flutter projects
    pub = os.path.join(project, "pubspec.yaml")
    if not os.path.exists(pub):
        changed.append(_w(project, "pubspec.yaml",
            "name: prove_app\nversion: 0.0.1\nenvironment:\n  sdk: '>=3.0.0 <4.0.0'\n"
            "dependencies:\n  flutter:\n    sdk: flutter\n  shared_preferences: ^2.2.0\n"
            "dev_dependencies:\n  flutter_test:\n    sdk: flutter\n"
            "flutter:\n  uses-material-design: true\n"))

    if task_id in ("scaffold",) or "scaffold" in blob or "materialapp" in blob:
        # Scaffold is self-contained so analyze passes before later tasks exist.
        changed.append(_w(project, "lib/main.dart", f"""import 'package:flutter/material.dart';
import 'app.dart';

void main() {{
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const ProveApp());
}}
"""))
        changed.append(_w(project, "lib/app.dart", f"""import 'package:flutter/material.dart';

class ProveApp extends StatelessWidget {{
  const ProveApp({{super.key}});

  @override
  Widget build(BuildContext context) {{
    return MaterialApp(
      title: 'Todos',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color({PRIMARY})),
        useMaterial3: true,
      ),
      home: const Scaffold(
        body: Center(child: Text('Todos')),
      ),
    );
  }}
}}
"""))

    if task_id in ("model",) or "model" in blob or "json" in blob:
        changed.append(_w(project, "lib/models/todo.dart", """class Todo {
  Todo({required this.id, required this.title, this.done = false});
  final String id;
  final String title;
  final bool done;

  Todo copyWith({String? id, String? title, bool? done}) => Todo(
        id: id ?? this.id,
        title: title ?? this.title,
        done: done ?? this.done,
      );

  Map<String, dynamic> toJson() => {'id': id, 'title': title, 'done': done};

  factory Todo.fromJson(Map<String, dynamic> j) => Todo(
        id: j['id'] as String,
        title: j['title'] as String,
        done: j['done'] as bool? ?? false,
      );
}
"""))

    if task_id in ("storage",) or "storage" in blob or "repository" in blob or "sharedpreferences" in blob:
        # ensure model exists
        if not os.path.exists(os.path.join(project, "lib/models/todo.dart")):
            changed.extend(apply_developer(project, "model"))
        changed.append(_w(project, "lib/storage/todo_repository.dart", """import 'dart:convert';
import '../models/todo.dart';

/// In-memory + optional prefs-shaped API for prove/mock (no plugin required for analyze).
class TodoRepository {
  static final List<Todo> _mem = [];

  Future<List<Todo>> getAll() async => List.unmodifiable(_mem);

  Future<void> add(Todo t) async {
    _mem.add(t);
  }

  Future<void> update(Todo t) async {
    final i = _mem.indexWhere((e) => e.id == t.id);
    if (i >= 0) _mem[i] = t;
  }

  Future<void> delete(String id) async {
    _mem.removeWhere((e) => e.id == id);
  }

  // JSON helpers for unit tests
  static String encodeList(List<Todo> items) =>
      jsonEncode(items.map((e) => e.toJson()).toList());

  static List<Todo> decodeList(String raw) {
    final list = jsonDecode(raw) as List<dynamic>;
    return list.map((e) => Todo.fromJson(e as Map<String, dynamic>)).toList();
  }
}
"""))

    if task_id in ("list_ui", "add_ui", "toggle", "delete") or any(
        x in blob for x in ("list", "addtodo", "toggle", "delete", "swipe", "todolistscreen")
    ):
        if not os.path.exists(os.path.join(project, "lib/app.dart")):
            changed.extend(apply_developer(project, "scaffold"))
        if not os.path.exists(os.path.join(project, "lib/models/todo.dart")):
            changed.extend(apply_developer(project, "model"))
        if not os.path.exists(os.path.join(project, "lib/storage/todo_repository.dart")):
            changed.extend(apply_developer(project, "storage"))
        changed.append(_w(project, "lib/screens/todo_list_screen.dart", f"""import 'package:flutter/material.dart';
import '../models/todo.dart';
import '../storage/todo_repository.dart';

class TodoListScreen extends StatefulWidget {{
  const TodoListScreen({{super.key}});

  @override
  State<TodoListScreen> createState() => _TodoListScreenState();
}}

class _TodoListScreenState extends State<TodoListScreen> {{
  final _repo = TodoRepository();
  List<Todo> _items = [];

  @override
  void initState() {{
    super.initState();
    _reload();
  }}

  Future<void> _reload() async {{
    final items = await _repo.getAll();
    if (mounted) setState(() => _items = items);
  }}

  Future<void> _add() async {{
    await _repo.add(Todo(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      title: 'New todo',
    ));
    await _reload();
  }}

  Future<void> _toggle(Todo t) async {{
    await _repo.update(t.copyWith(done: !t.done));
    await _reload();
  }}

  Future<void> _delete(Todo t) async {{
    await _repo.delete(t.id);
    await _reload();
  }}

  @override
  Widget build(BuildContext context) {{
    return Scaffold(
      appBar: AppBar(title: const Text('Todos')),
      body: _items.isEmpty
          ? const Center(child: Text('No todos yet'))
          : ListView.builder(
              itemCount: _items.length,
              itemBuilder: (context, i) {{
                final t = _items[i];
                return ListTile(
                  title: Text(
                    t.title,
                    style: TextStyle(
                      decoration:
                          t.done ? TextDecoration.lineThrough : null,
                    ),
                  ),
                  leading: Checkbox(
                    value: t.done,
                    onChanged: (_) => _toggle(t),
                  ),
                  trailing: IconButton(
                    icon: const Icon(Icons.delete_outline),
                    onPressed: () => _delete(t),
                  ),
                );
              }},
            ),
      floatingActionButton: FloatingActionButton(
        onPressed: _add,
        backgroundColor: const Color({PRIMARY}),
        child: const Icon(Icons.add, color: Colors.white),
      ),
    );
  }}
}}
"""))
        # Wire home to list when list exists
        changed.append(_w(project, "lib/app.dart", f"""import 'package:flutter/material.dart';
import 'screens/todo_list_screen.dart';

class ProveApp extends StatelessWidget {{
  const ProveApp({{super.key}});

  @override
  Widget build(BuildContext context) {{
    return MaterialApp(
      title: 'Todos',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color({PRIMARY})),
        useMaterial3: true,
      ),
      home: const TodoListScreen(),
    );
  }}
}}
"""))

    if not changed:
        changed.extend(apply_developer(project, "scaffold"))

    # Always leave a per-task marker so git commit is non-empty
    marker = _w(
        project,
        f"lib/generated/task_{task_id}.dart",
        f"// foreman mock task: {task_id}\nconst String kTask_{task_id} = '{task_id}';\n",
    )
    if marker not in changed:
        changed.append(marker)

    # dedupe preserve order
    seen = set()
    out = []
    for c in changed:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def apply_tester(project: str, task_id: str) -> list[str]:
    project = os.path.abspath(project)
    if not os.path.exists(os.path.join(project, "lib/models/todo.dart")):
        apply_developer(project, "model")
    pkg = _pkg_name(project)
    return [_w(project, "test/todo_model_test.dart", f"""import 'package:flutter_test/flutter_test.dart';
import 'package:{pkg}/models/todo.dart';

void main() {{
  test('Todo json round-trip', () {{
    final t = Todo(id: '1', title: 'a', done: true);
    final t2 = Todo.fromJson(t.toJson());
    expect(t2.id, '1');
    expect(t2.title, 'a');
    expect(t2.done, isTrue);
  }});
}}
""")]


def mock_handoff_payload(role: str, task_id: str, files: list[str] | None = None) -> dict[str, Any]:
    """Minimal schema-valid handoff for mock roles after code write."""
    files = files or ["lib/main.dart"]
    if role == "architect":
        return {
            "role": "architect",
            "approach": f"Implement {task_id} with shadcn_flutter kit tokens and design primary",
            "files": [{"path": f, "purpose": task_id} for f in files],
            "key_apis": ["ShadcnApp", "Button", "Card"],
            "state_shape": "local repository",
            "edge_cases": ["empty list"],
            "test_plan": ["unit test model"],
            "risks": [],
            "design_drift": "none",
        }
    if role == "developer":
        return {
            "role": "developer",
            "files_changed": files,
            "summary": f"Implemented {task_id}",
            "decisions": ["Used Flutter SDK widgets"],
            "yagni_notes": [],
            "blockers": [],
            "needs_review": True,
        }
    if role == "tester":
        return {
            "role": "tester",
            "test_files": files,
            "all_pass": True,
            "summary": "mock tests written",
        }
    if role == "qa_lead":
        return {"role": "qa_lead", "test_strategy": f"Unit + widget for {task_id}"}
    if role == "reviewer":
        return {"role": "reviewer", "findings": [], "verdict": "APPROVED"}
    if role == "refactorer":
        return {"role": "refactorer", "fixes_applied": []}
    if role == "debugger":
        return {"role": "debugger", "root_cause": "n/a", "fix": "n/a", "files_changed": files}
    if role == "designer":
        return {
            "role": "designer",
            "summary": "Calm utility todo system",
            "personality": "calm utility",
            "platforms": ["ios", "android"],
            "mockups": [{
                "screen": "HomeScreen",
                "goal": "Manage todos",
                "primary_cta": "Add",
                "wireframe": "AppBar\nList\nFAB",
                "notes": "single primary FAB",
            }],
            "design_language_md": (
                f"# Design Language — Todos\n\n## 1. Personality & principles\nCalm utility\n\n"
                f"## 2. UI kit\nshadcn_flutter\n\n"
                f"## 3. Color\n- Primary: #{PRIMARY_HEX}\n- On primary: #FFFFFF\n"
                f"- Surface: #FFFBFE\n- On surface: #1C1B1F\n- Error: #B3261E\n\n"
                f"## 4. Typography\nType scale\n\n## 5. Space & layout\n4 8 12 16 24\n\n"
                f"## 6. Shape & elevation\n12 radius\n\n"
                f"## 7. Components\nShadcnApp, Button(primary), Card\n\n"
                f"## 8. Navigation\nSingle screen\n\n## 9. Motion\n200ms\n\n"
                f"## 10. Content & empty/loading/error\nEmpty: No todos yet\n\n"
                f"## 11. Accessibility\n48dp\n\n## 12. Do / Don't\nNo purple slop\n\n"
                f"## 13. Screen specs\nHomeScreen\n"
            ),
            "token_index": {
                "primary": f"#{PRIMARY_HEX}",
                "on_primary": "#FFFFFF",
                "primary_container": "#BBDEFB",
                "surface": "#FFFBFE",
                "on_surface": "#1C1B1F",
                "error": "#B3261E",
                "outline": "#79747E",
            },
            "anti_slop_checklist": {
                "no_generic_purple_gradient": True,
                "single_primary_cta_per_screen": True,
                "semantic_color_roles": True,
                "contrast_aa_text": True,
                "empty_loading_error_defined": True,
                "min_touch_48": True,
            },
            "open_questions": [],
            "status": "pending_review",
        }
    return {"role": role, "summary": f"mock {role}"}
