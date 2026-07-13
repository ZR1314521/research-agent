from __future__ import annotations

import json
from pathlib import Path

from research_agent.nodes.base import BaseNode, NodeError
from research_agent.state import RunState


class ReferenceFormatNode(BaseNode):
    name = "reference_format"

    def __init__(self, config, run_dir: Path, styles: list[str] | None = None):
        super().__init__(config, run_dir)
        self.styles = styles or ["gbt7714-numeric", "ieee", "nature", "apa"]

    def run(self, state: RunState) -> RunState:
        state.mark_running(self.name)
        refs = self._find_reference_input(state)
        if not refs:
            raise NodeError("No reference input found")
        args = [
            str(self.script("format_references_strict.py")),
            refs,
            "--profiles",
            str(self.config.rules_dir / "style_profiles.json"),
            "--out-dir",
            str(self.run_dir),
        ]
        for style in self.styles:
            args.extend(["--style", style])
        self.run_script(args)
        state.add_artifact("citation_check_report", self.run_dir / "citation_check_report.md")
        state.add_artifact("references_bib", self.run_dir / "references.bib")
        for style in self.styles:
            state.add_artifact(f"references_{style}", self.run_dir / f"references_{style.replace('-', '_')}.md")
        state.mark_completed(self.name, f"Formatted references in {len(self.styles)} style(s)")
        return state

    def _find_reference_input(self, state: RunState) -> str:
        manifest_path = state.artifacts.get("upload_manifest")
        if manifest_path:
            manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            for item in manifest.get("files", []):
                if item.get("category") == "references" and item.get("extension") == ".json":
                    return item["stored_path"]
        if "screened_papers" in state.artifacts:
            return state.artifacts["screened_papers"]
        return ""
