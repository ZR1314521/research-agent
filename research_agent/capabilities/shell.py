from __future__ import annotations

import subprocess
import sys
from typing import Any


class ShellService:
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
        )
        output = (proc.stdout.strip() + "\n" + proc.stderr.strip()).strip()
        return {
            "message": output[:3000] or "command completed",
            "artifacts": {},
            "data": {"exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr},
        }
