"""Minimal configuration.

Tools use 3 fields: project_dir, project_path, memory_dir. Everything else
was YAGNI. Kept as a dataclass for stable attribute access.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


@dataclass
class Config:
    project_dir: str = "."
    framework: str = "flutter"

    @property
    def project_path(self) -> str:
        return os.path.abspath(self.project_dir)

    @property
    def memory_dir(self) -> str:
        return os.path.join(self.project_path, ".foreman")


def load_config() -> Config:
    return Config()
