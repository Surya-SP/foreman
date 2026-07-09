"""Minimal git integration: per-task commits."""
from __future__ import annotations

from .config import Config
from .proc import run_command, which


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

    def commit_task(self, task_id: str, message: str) -> bool:
        if not self._ready:
            return False
        self._git("add", "-A")
        if not self._git("status", "--porcelain").stdout.strip():
            return False
        return self._git("commit", "-m", f"foreman({task_id}): {message[:72]}").ok
