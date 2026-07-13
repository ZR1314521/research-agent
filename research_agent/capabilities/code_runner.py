from __future__ import annotations

import subprocess
import sys
import time
from typing import Any


class CodeRunnerService:
    """Execute arbitrary Python code and return stdout/stderr."""

    def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        code = str(arguments.get("code", "")).strip()
        if not code:
            raise ValueError("run_code requires 'code' parameter")

        timeout = int(arguments.get("timeout") or 60)
        timeout = max(5, min(timeout, 300))

        started = time.time()
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        elapsed = time.time() - started

        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        ok = proc.returncode == 0

        lines = []
        if ok and stdout:
            lines.append(f"Code executed successfully ({elapsed:.1f}s)")
            lines.append(f"\n{stdout}")
        elif ok and not stdout:
            lines.append(f"Code executed successfully with no output ({elapsed:.1f}s)")
        else:
            lines.append(f"Code failed with exit code {proc.returncode} ({elapsed:.1f}s)")
            if stderr:
                lines.append(f"\n{stderr}")
            if stdout:
                lines.append(f"\n{stdout}")

        return {
            "message": "\n".join(lines),
            "artifacts": {},
            "data": {"ok": ok, "exit_code": proc.returncode, "elapsed": elapsed, "stdout": stdout, "stderr": stderr},
        }
