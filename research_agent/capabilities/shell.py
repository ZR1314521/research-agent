from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from research_agent.capabilities.workspace import WorkspaceContext


class ShellService:
    def __init__(self, session_dir: Path | WorkspaceContext):
        self.context = session_dir if isinstance(session_dir, WorkspaceContext) else WorkspaceContext.for_session(session_dir)

    def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        cmd = str(arguments.get("command", "")).strip()
        if not cmd:
            raise ValueError("shell requires a command")
        # Use PowerShell on Windows to avoid cmd.exe quirks like
        # interactive `date` / `time` prompts.
        if sys.platform == "win32":
            cmd = f'powershell -NoProfile -Command "[Console]::OutputEncoding=[Text.Encoding]::UTF8; {cmd}"'
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=60, encoding="utf-8", errors="replace",
            cwd=self.context.workspace_root,
        )
        output = (proc.stdout.strip() + "\n" + proc.stderr.strip()).strip()
        return {
            "message": output[:3000] or "command completed",
            "artifacts": {},
            "data": {"exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr, "cwd": str(self.context.workspace_root)},
        }
