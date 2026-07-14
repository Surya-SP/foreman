"""Minimal git integration: scoped per-task commits."""
from __future__ import annotations

import os

from .config import Config
from .proc import run_command, which

_SKIP_NAMES = {".env", ".env.local", "credentials.json", "service-account.json"}
_SKIP_PARTS = (".env", "secrets/", "credentials")


class Vcs:
    def __init__(self, config: Config) -> None:
        self.cwd = config.project_path
        self._ready = self._init()

    def _git(self, *args: str, timeout: int = 60):
        return run_command(["git", *args], cwd=self.cwd, timeout=timeout, heartbeat=False)

    def _init(self) -> bool:
        if not which("git"):
            return False
        return self._git("rev-parse", "--is-inside-work-tree").ok

    @property
    def ready(self) -> bool:
        return self._ready

    def _safe_path(self, p: str) -> bool:
        base = os.path.basename(p)
        if base in _SKIP_NAMES:
            return False
        if any(s in p for s in _SKIP_PARTS):
            return False
        return True

    def commit_task(self, task_id: str, message: str, files: list[str] | None = None) -> bool:
        """Commit task changes. Prefer explicit files; never blind secrets."""
        if not self._ready:
            return False
        if files:
            paths = [f for f in files if f and self._safe_path(str(f))]
            if not paths:
                return False
            self._git("add", "--", *paths)
        else:
            # Tracked updates + app source trees (not git add -A of whole repo)
            self._git("add", "-u")
            for d in ("lib", "test", "integration_test", "tasks", "pubspec.yaml", "pubspec.lock"):
                if os.path.exists(os.path.join(self.cwd, d)):
                    self._git("add", "--", d)
        if not self._git("status", "--porcelain").stdout.strip():
            return False
        return self._git("commit", "-m", f"foreman({task_id}): {message[:72]}").ok
