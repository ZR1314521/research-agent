from __future__ import annotations

from pathlib import Path

from research_agent.nodes.base import BaseNode
from research_agent.state import RunState


class CheckpointNode(BaseNode):
    name = "checkpoint"

    def __init__(self, config, run_dir: Path, step: str, prompt: str):
        super().__init__(config, run_dir)
        self.step = step
        self.prompt = prompt

    def run(self, state: RunState) -> RunState:
        state.add_checkpoint(self.step, self.prompt)
        return state
