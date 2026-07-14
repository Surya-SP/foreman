"""Minimal git integration: scoped per-task commits + secret guard."""
from __future__ import annotations

import os
import re

from .config import Config
from .proc import run_command, which

_SKIP_NAMES = {".env", ".env.local", "credentials.json", "service-account.json", "id_rsa", "id_ed25519"}
_SKIP_PARTS = (".env", "secrets/", "credentials", ".pem", "google-services.json")
# Content patterns in staged files
_SECRET_CONTENT = re.compile(
    r"(?i)(api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}"
    r"|secret[_-]?key\s*[:=]"
    r"|BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY"
    r"|AKIA[0-9A-Z]{16}"
    r"|password\s*[:=]\s*['\"][^'\"]{8,})"
)


class Vcs:
    def __init__(self, config: Config) -> None:
        self.cwd = config.project_path
        self._ready = self._init()
        self.last_error = ""

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

    def _secret_scan_staged(self) -> str | None:
        """Return error message if staged paths look like secrets."""
        st = self._git("diff", "--cached", "--name-only")
        names = [n for n in (st.stdout or "").splitlines() if n.strip()]
        for n in names:
            if not self._safe_path(n):
                return f"refusing commit: secret-like path staged: {n}"
            fp = os.path.join(self.cwd, n)
            if not os.path.isfile(fp):
                continue
            try:
                # only scan small text files
                if os.path.getsize(fp) > 200_000:
                    continue
                raw = open(fp, "rb").read(50_000)
                if b"\0" in raw:
                    continue
                text = raw.decode("utf-8", errors="ignore")
                if _SECRET_CONTENT.search(text):
                    return f"refusing commit: secret-like content in {n}"
            except OSError:
                continue
        return None

    def commit_task(self, task_id: str, message: str, files: list[str] | None = None) -> bool:
        """Commit task changes. Prefer explicit files; never blind secrets."""
        self.last_error = ""
        if not self._ready:
            self.last_error = "not a git repo"
            return False
        if files:
            paths = [f for f in files if f and self._safe_path(str(f))]
            if not paths:
                self.last_error = "no safe files to stage"
                return False
            self._git("add", "--", *paths)
        else:
            self._git("add", "-u")
            for d in ("lib", "test", "integration_test", "tasks", "pubspec.yaml", "pubspec.lock"):
                if os.path.exists(os.path.join(self.cwd, d)):
                    self._git("add", "--", d)
        if not self._git("status", "--porcelain").stdout.strip():
            self.last_error = "nothing to commit"
            return False
        bad = self._secret_scan_staged()
        if bad:
            self.last_error = bad
            self._git("reset", "HEAD")
            return False
        ok = self._git("commit", "-m", f"foreman({task_id}): {message[:72]}").ok
        if not ok:
            self.last_error = "git commit failed"
        return ok
