from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


class GitService:
    """Run git commands inside the project root or session directory."""

    def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        command = str(arguments.get("command", "")).strip()
        if not command:
            raise ValueError("git requires a command")

        cwd = Path(arguments.get("cwd") or ".")
        cwd.mkdir(parents=True, exist_ok=True)

        # Ensure git repo exists
        if not (cwd / ".git").exists():
            subprocess.run(["git", "init"], cwd=cwd, capture_output=True)

        args = command.split()
        proc = subprocess.run(
            ["git"] + args, cwd=cwd,
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        output = (proc.stdout.strip() + "\n" + proc.stderr.strip()).strip()
        return {
            "message": output[:3000] or "git command completed",
            "artifacts": {},
            "data": {"exit_code": proc.returncode, "output": output, "cwd": str(cwd)},
        }
