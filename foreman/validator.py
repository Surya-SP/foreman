"""Flutter validation pipeline: pub get -> dart fix -> format -> analyze -> test [-> coverage]."""
from __future__ import annotations

import glob
import os

from .config import Config
from .models import ValidationResult, ValidationStep
from .proc import run_command, which


def which_flutter() -> bool:
    return which("flutter") is not None


def _has_tests(project: str) -> bool:
    return bool(glob.glob(os.path.join(project, "test", "**", "*_test.dart"), recursive=True))


def _coverage_pct(project: str) -> float | None:
    """Parse line coverage from coverage/lcov.info (0..100). None if unparseable."""
    lcov = os.path.join(project, "coverage", "lcov.info")
    if not os.path.exists(lcov):
        return None
    found = hit = 0
    try:
        for line in open(lcov):
            if line.startswith("LF:"): found += int(line[3:].strip() or 0)
            elif line.startswith("LH:"): hit += int(line[3:].strip() or 0)
    except (OSError, ValueError):
        return None
    return (hit / found * 100.0) if found else None


def validate(config: Config, *, coverage: bool = False, min_coverage: float = 0.0) -> ValidationResult:
    project = config.project_path
    steps: list[ValidationStep] = []

    if config.framework != "flutter":
        return ValidationResult(ok=True, steps=[ValidationStep("validate", ok=True, skipped=True)])

    if not os.path.exists(os.path.join(project, "pubspec.yaml")):
        return ValidationResult(ok=False, steps=[ValidationStep("project-check", ok=False,
                                                                 output=f"No pubspec.yaml in {project}")])

    # Preflight: missing SDK is environment, not app bug (don't thrash debugger)
    if not which_flutter():
        return ValidationResult(ok=False, steps=[ValidationStep(
            "sdk-preflight", ok=False,
            output="flutter not on PATH — install Flutter SDK; this is not an app defect",
        )])

    pipeline = [
        (["flutter", "pub", "get"], "flutter pub get", 300, True),
        (["dart", "fix", "--apply"], "dart fix --apply", 120, False),
        (["dart", "format", "--set-exit-if-changed", "."], "dart format", 120, True),
        (["flutter", "analyze"], "flutter analyze", 180, True),
    ]
    for cmd, name, timeout, hard in pipeline:
        res = run_command(cmd, cwd=project, timeout=timeout, heartbeat=False)
        steps.append(ValidationStep(name, ok=res.ok if hard else True,
                                    output=_tail(res.combined), skipped=(not res.ok and not hard)))
        if hard and not res.ok:
            return ValidationResult(ok=False, steps=steps)

    if _has_tests(project):
        test_cmd = ["flutter", "test"]
        if coverage: test_cmd.append("--coverage")
        res = run_command(test_cmd, cwd=project, timeout=300, heartbeat=False)
        steps.append(ValidationStep("flutter test", ok=res.ok, output=_tail(res.combined)))
        if not res.ok:
            return ValidationResult(ok=False, steps=steps)

        if coverage:
            pct = _coverage_pct(project)
            ok_cov = pct is not None and pct >= min_coverage
            steps.append(ValidationStep(
                "coverage",
                ok=ok_cov,
                output=(f"line coverage {pct:.1f}% (min {min_coverage:.1f}%)" if pct is not None
                        else "no coverage data")
            ))
            if not ok_cov:
                return ValidationResult(ok=False, steps=steps)
    else:
        steps.append(ValidationStep("flutter test", ok=True, skipped=True))

    return ValidationResult(ok=True, steps=steps)


def _tail(text: str, lines: int = 20) -> str:
    return "\n".join((text or "").splitlines()[-lines:])
