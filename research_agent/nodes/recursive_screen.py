from __future__ import annotations

from pathlib import Path

from research_agent.nodes.base import BaseNode, NodeError
from research_agent.state import RunState


class RecursiveScreenNode(BaseNode):
    name = "recursive_screen"

    def __init__(self, config, run_dir: Path, threshold: int = 60, rounds: int = 3, target: int = 30):
        super().__init__(config, run_dir)
        self.threshold = threshold
        self.rounds = rounds
        self.target = target

    def run(self, state: RunState) -> RunState:
        state.mark_running(self.name)
        raw_papers = state.artifacts.get("raw_papers")
        if not raw_papers:
            raise NodeError("No raw papers artifact available")
        args = [
            str(self.script("recursive_search.py")),
            raw_papers,
            "--topic",
            state.topic,
            "--keywords",
            state.keywords,
            "--venues",
            state.venues,
            "--rounds",
            str(self.rounds),
            "--threshold",
            str(self.threshold),
            "--target",
            str(self.target),
            "--out-dir",
            str(self.run_dir),
        ]
        if state.year_from:
            args.extend(["--year-from", str(state.year_from)])
        if state.year_to:
            args.extend(["--year-to", str(state.year_to)])
        self.run_script(args)
        state.add_artifact("screened_papers", self.run_dir / "screened_papers.json")
        state.add_artifact("excluded_papers", self.run_dir / "excluded_papers.json")
        state.add_artifact("recursive_search_plan", self.run_dir / "recursive_search_plan.json")
        state.add_artifact("screening_log", self.run_dir / "screening_log.md")
        state.mark_completed(self.name, "Recursive screening completed")
        return state
