from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

from research_agent.config import AgentConfig
from research_agent.nodes import (
    ExperimentAnalysisNode,
    LiteratureSearchNode,
    MatrixExtractNode,
    RagBuildNode,
    RagQueryNode,
    RecursiveScreenNode,
    ReferenceFormatNode,
    ReviewDraftNode,
    UploadNode,
)
from research_agent.state import RunState, StepStatus


class ResearchWorkflow:
    def __init__(self, config: AgentConfig | None = None):
        self.config = config or AgentConfig.load()
        self.config.runs_dir.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        return self.config.runs_dir / run_id

    def create_run(
        self,
        *,
        topic: str,
        keywords: str = "",
        venues: str = "",
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> RunState:
        state = RunState.create(topic, keywords, venues, year_from, year_to)
        state.save(self.run_dir(state.run_id))
        return state

    def load_run(self, run_id: str) -> RunState:
        return RunState.load(self.run_dir(run_id) / "workflow_state.json")

    def save_run(self, state: RunState) -> RunState:
        state.save(self.run_dir(state.run_id))
        return state

    def add_uploads(self, run_id: str, files: list[str], copy: bool = True) -> RunState:
        state = self.load_run(run_id)
        run_dir = self.run_dir(run_id)
        state = UploadNode(self.config, run_dir, files=files, copy=copy).run(state)
        return self.save_run(state)

    def start(
        self,
        run_id: str,
        *,
        sources: list[str] | None = None,
        styles: list[str] | None = None,
        checkpoint_after_screening: bool = False,
        progress: Callable[[str, str], None] | None = None,
    ) -> RunState:
        state = self.load_run(run_id)
        run_dir = self.run_dir(run_id)
        def run_node(node, state: RunState) -> RunState:
            if node.name in state.completed_steps:
                return state
            if progress:
                progress("start", node.name)
            state = node.run(state)
            state.save(run_dir)
            if progress:
                progress("done", node.name)
            return state

        nodes = [
            LiteratureSearchNode(self.config, run_dir, sources=sources),
            RecursiveScreenNode(self.config, run_dir),
        ]
        try:
            for node in nodes:
                state = run_node(node, state)
            if checkpoint_after_screening:
                state.add_checkpoint("recursive_screen", "Confirm screened paper pool before extraction.")
                return self.save_run(state)
            for node in [
                MatrixExtractNode(self.config, run_dir),
                RagBuildNode(self.config, run_dir),
                RagQueryNode(self.config, run_dir, query=f"{state.topic} {state.keywords} literature review framework"),
                ReviewDraftNode(self.config, run_dir),
                ExperimentAnalysisNode(self.config, run_dir),
                ReferenceFormatNode(self.config, run_dir, styles=styles),
            ]:
                state = run_node(node, state)
            state.status = StepStatus.COMPLETED
            state.current_step = "final_review"
            state.mark_completed("final_review", "Workflow completed")
            if progress:
                progress("done", "final_review")
            return self.save_run(state)
        except Exception as exc:
            state.mark_failed(state.current_step, str(exc))
            if progress:
                progress("failed", state.current_step)
            return self.save_run(state)

    def resume(self, run_id: str, decision: str = "", progress: Callable[[str, str], None] | None = None) -> RunState:
        state = self.load_run(run_id)
        if decision:
            state.add_decision(state.current_step, decision)
        state.status = StepStatus.RUNNING
        state.save(self.run_dir(run_id))
        return self.start(run_id, progress=progress)

    def artifacts(self, run_id: str) -> dict[str, str]:
        return self.load_run(run_id).artifacts

    def reset_run(self, run_id: str) -> None:
        run_dir = self.run_dir(run_id)
        if run_dir.exists():
            shutil.rmtree(run_dir)
