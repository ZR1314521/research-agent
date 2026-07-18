from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from research_agent.capabilities.workspace import WorkspaceContext


class CodeRunnerService:
    """Execute arbitrary Python code and return stdout/stderr."""

    IMAGE_SUFFIXES = {".png", ".svg", ".pdf", ".jpg", ".jpeg", ".webp"}

    def __init__(self, session_dir: Path | WorkspaceContext):
        self.context = session_dir if isinstance(session_dir, WorkspaceContext) else WorkspaceContext.for_session(session_dir)

    def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        code = str(arguments.get("code", "")).strip()
        if not code:
            raise ValueError("run_code requires 'code' parameter")

        timeout = int(arguments.get("timeout") or 60)
        timeout = max(5, min(timeout, 300))
        before = self._image_snapshot()
        environment = dict(os.environ)
        environment.update({
            "MPLBACKEND": "Agg",
            "PYTHONUTF8": "1",
            "RESEARCH_AGENT_ARTIFACT_DIR": str(self.context.artifacts_root),
        })

        started = time.time()
        proc = subprocess.run(
            [sys.executable, "-I", "-c", code],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
            cwd=self.context.workspace_root,
            env=environment,
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

        generated = sorted(self._image_snapshot() - before)
        artifacts = {f"code_image_{index}": str(path) for index, path in enumerate(generated, 1)}
        if generated:
            lines.append(f"\n生成 {len(generated)} 个图像成果，可在当前会话成果中查看。")

        return {
            "message": "\n".join(lines),
            "artifacts": artifacts,
            "data": {
                "ok": ok, "exit_code": proc.returncode, "elapsed": elapsed,
                "stdout": stdout, "stderr": stderr, "generated_images": [str(path) for path in generated],
            },
        }

    def _image_snapshot(self) -> set[Path]:
        images: set[Path] = set()
        for path in self.context.workspace_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in self.IMAGE_SUFFIXES or path.stat().st_size <= 0:
                continue
            try:
                resolved = self.context.resolve(str(path))
            except ValueError:
                continue
            images.add(resolved)
        return images
