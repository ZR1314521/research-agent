from __future__ import annotations

from pathlib import Path

from research_agent.nodes.base import BaseNode
from research_agent.state import RunState


class RagBuildNode(BaseNode):
    name = "rag_build"

    def run(self, state: RunState) -> RunState:
        state.mark_running(self.name)
        inputs = [str(self.config.rules_dir)]
        for key in ("screened_papers", "literature_matrix_csv", "summary_notes"):
            if key in state.artifacts:
                inputs.append(state.artifacts[key])
        index_dir = self.run_dir / "rag_index"
        self.run_script([str(self.script("build_rag_index.py")), *inputs, "--out-dir", str(index_dir)])
        state.add_artifact("rag_index", index_dir)
        state.add_artifact("rag_chunks", index_dir / "chunks.jsonl")
        state.mark_completed(self.name, "RAG index built")
        return state


class RagQueryNode(BaseNode):
    name = "rag_query"

    def __init__(self, config, run_dir: Path, query: str):
        super().__init__(config, run_dir)
        self.query = query

    def run(self, state: RunState) -> RunState:
        state.mark_running(self.name)
        index_dir = state.artifacts.get("rag_index") or str(self.run_dir / "rag_index")
        out = self.run_dir / "rag_answer.md"
        self.run_script([
            str(self.script("query_rag.py")),
            "--index-dir",
            str(index_dir),
            "--query",
            self.query,
            "--out",
            str(out),
        ])
        state.add_artifact("rag_answer", out)
        state.add_artifact("retrieval_log", Path(index_dir) / "retrieval_log.jsonl")
        state.mark_completed(self.name, "RAG query completed")
        return state
