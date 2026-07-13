from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from research_agent.config import AgentConfig
from research_agent.state import RunState


class NodeError(RuntimeError):
    pass


class BaseNode:
    name = "base"

    def __init__(self, config: AgentConfig, run_dir: Path):
        self.config = config
        self.run_dir = run_dir

    def script(self, name: str) -> Path:
        path = self.config.scripts_dir / name
        if not path.exists():
            raise NodeError(f"Missing script: {path}")
        return path

    def run_script(self, args: list[str]) -> str:
        result = subprocess.run(
            [sys.executable, *args],
            cwd=self.config.root_dir,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            raise NodeError((result.stderr or result.stdout or "script failed").strip())
        return result.stdout.strip()

    def run(self, state: RunState) -> RunState:
        raise NotImplementedError
