from __future__ import annotations

import json
from pathlib import Path

from research_agent.nodes.base import BaseNode
from research_agent.state import RunState


class UploadNode(BaseNode):
    name = "upload"

    def __init__(self, config, run_dir: Path, files: list[str] | None = None, copy: bool = True):
        super().__init__(config, run_dir)
        self.files = files or []
        self.copy = copy

    def run(self, state: RunState) -> RunState:
        state.mark_running(self.name)
        if not self.files:
            manifest = {"run_dir": str(self.run_dir), "upload_dir": str(self.run_dir / "uploads"), "files": []}
            path = self.run_dir / "upload_manifest.json"
            path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            state.add_artifact("upload_manifest", path)
            state.mark_completed(self.name, "No uploaded files registered")
            return state
        args = [str(self.script("prepare_uploads.py")), *self.files, "--run-dir", str(self.run_dir)]
        if self.copy:
            args.append("--copy")
        self.run_script(args)
        path = self.run_dir / "upload_manifest.json"
        state.add_artifact("upload_manifest", path)
        state.mark_completed(self.name, f"Registered {len(self.files)} uploaded file(s)")
        return state
