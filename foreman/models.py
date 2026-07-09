"""Data models. Only ValidationResult/Step and ExecResult are used."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExecResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    timed_out: bool = False
    duration: float = 0.0

    @property
    def combined(self) -> str:
        return "\n".join(p for p in (self.stdout, self.stderr) if p)


@dataclass
class ValidationStep:
    name: str
    ok: bool
    output: str = ""
    skipped: bool = False


@dataclass
class ValidationResult:
    ok: bool
    steps: list[ValidationStep] = field(default_factory=list)

    @property
    def summary(self) -> str:
        lines: list[str] = []
        for s in self.steps:
            if s.skipped:
                continue
            lines.append(f"[{'PASS' if s.ok else 'FAIL'}] {s.name}")
            if not s.ok and s.output.strip():
                lines.append(s.output.strip())
        return "\n".join(lines).strip()
