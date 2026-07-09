"""Subprocess helpers with streaming capture, timeout and ANSI cleanup.

All external commands (flutter, git, dart) go through ``run_command``
so behaviour (timeout, kill, heartbeat, capture) is consistent.
"""
from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import threading
import time

from .models import ExecResult

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text or "")


def run_command(
    cmd: list[str],
    *,
    cwd: str | None = None,
    timeout: int | None = None,
    label: str = "cmd",
    heartbeat: bool = True,
    stream: bool = False,
    env: dict[str, str] | None = None,
    display_filter=None,
) -> ExecResult:
    """Run ``cmd`` capturing combined output, enforcing ``timeout``.

    When ``stream`` is True the child's output is echoed live to the terminal as
    it arrives. When False a background heartbeat prints elapsed seconds so long
    runs do not look frozen.
    """
    if stream:
        heartbeat = False
    start = time.time()
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=cwd,
            bufsize=1,
            env={**os.environ, **(env or {})},
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        return ExecResult(ok=False, stderr=str(exc), returncode=127, duration=0.0)

    lines: list[str] = []

    def _reader() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.append(line)
            if stream:
                shown = line
                if display_filter is not None:
                    try:
                        shown = display_filter(line)
                    except Exception:
                        shown = line
                if shown:
                    sys.stdout.write("   │ " + shown if not shown.startswith("   │") else shown)
                    sys.stdout.flush()

    reader = threading.Thread(target=_reader, daemon=True)
    reader.start()

    if stream:
        sys.stdout.write(f"   ┌─ {label} (live) ───────────────\n")
        sys.stdout.flush()

    timed_out = False
    last_beat = start
    while True:
        if proc.poll() is not None:
            break
        now = time.time()
        if timeout is not None and now - start > timeout:
            timed_out = True
            _kill_tree(proc)
            break
        if heartbeat and now - last_beat >= 15:
            elapsed = int(now - start)
            sys.stdout.write(f"\r   ⏳ {label}: {elapsed}s elapsed…")
            sys.stdout.flush()
            last_beat = now
        time.sleep(0.2)

    reader.join(timeout=3)
    if heartbeat:
        sys.stdout.write("\r" + " " * 40 + "\r")
        sys.stdout.flush()
    if stream:
        sys.stdout.write("   └────────────────────────────────\n")
        sys.stdout.flush()

    output = strip_ansi("".join(lines)).strip()
    duration = time.time() - start
    returncode = proc.returncode
    ok = (not timed_out) and returncode == 0
    return ExecResult(
        ok=ok,
        stdout=output,
        stderr="Timeout: command exceeded time limit" if timed_out else "",
        returncode=returncode,
        timed_out=timed_out,
        duration=duration,
    )


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill the process and its children. Works on Unix and Windows."""
    try:
        if sys.platform == "win32":
            proc.kill()
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            if sys.platform == "win32":
                proc.kill()
            else:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass


def which(binary: str) -> bool:
    from shutil import which as _which

    return _which(binary) is not None
