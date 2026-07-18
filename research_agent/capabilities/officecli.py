from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _officecli_path() -> str | None:
    local = Path(__file__).resolve().parents[2] / "officecli.exe"
    if local.exists():
        return str(local)
    path = shutil.which("officecli")
    return path


class OfficeCLIService:
    """AI-friendly CLI for .docx, .xlsx, .pptx — single binary, no Office required."""

    def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        command = str(arguments.get("command") or "").strip()
        if not command:
            raise ValueError("officecli requires a command")
        binary = _officecli_path()
        if not binary:
            raise RuntimeError("officecli not found")

        args = [binary, "--json", command]
        for key in ("file", "path", "parent", "type", "selector", "target_format"):
            val = arguments.get(key)
            if val:
                args.append(str(val))

        if "props" in arguments and isinstance(arguments["props"], dict):
            for k, v in arguments["props"].items():
                args.extend(["--prop", f"{k}={v}"])

        if "commands" in arguments:
            args.extend(["--commands", json.dumps(arguments["commands"], ensure_ascii=False)])

        try:
            proc = subprocess.run(args, capture_output=True, timeout=120, encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            raise RuntimeError("officecli timed out")

        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"officecli exited {proc.returncode}")

        return {"message": proc.stdout.strip() or "done", "artifacts": {}, "data": {}}
