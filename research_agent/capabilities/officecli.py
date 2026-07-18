from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from research_agent.capabilities.workspace import WorkspaceContext


def _officecli_path() -> str | None:
    local = Path(__file__).resolve().parents[2] / "officecli.exe"
    if local.exists():
        return str(local)
    path = shutil.which("officecli")
    return path


class OfficeCLIService:
    """AI-friendly CLI for .docx, .xlsx, .pptx — single binary, no Office required."""

    def __init__(self, session_dir: Path | WorkspaceContext):
        self.context = session_dir if isinstance(session_dir, WorkspaceContext) else WorkspaceContext.for_session(session_dir)

    def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        command = str(arguments.get("command") or "").strip()
        if not command:
            raise ValueError("officecli requires a command")
        binary = _officecli_path()
        if not binary:
            raise RuntimeError("officecli not found")

        resolved_file: Path | None = None
        if arguments.get("file"):
            resolved_file = self.context.resolve(str(arguments["file"]))
        args = [binary, "--json", command]
        for key in ("file", "path", "parent", "type", "selector", "target_format"):
            val = arguments.get(key)
            if val:
                args.append(str(resolved_file) if key == "file" and resolved_file else str(val))

        if "props" in arguments and isinstance(arguments["props"], dict):
            for k, v in arguments["props"].items():
                args.extend(["--prop", f"{k}={v}"])

        if "commands" in arguments:
            args.extend(["--commands", json.dumps(arguments["commands"], ensure_ascii=False)])

        try:
            proc = subprocess.run(
                args, capture_output=True, timeout=120, encoding="utf-8", errors="replace",
                cwd=self.context.workspace_root,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("officecli timed out")

        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"officecli exited {proc.returncode}")

        artifacts = {}
        if resolved_file and resolved_file.exists() and resolved_file.is_file():
            artifacts["office_document"] = str(resolved_file)
        return {
            "message": proc.stdout.strip() or "Office 文档操作完成。",
            "artifacts": artifacts,
            "data": {"command": command, "file": str(resolved_file) if resolved_file else ""},
        }
