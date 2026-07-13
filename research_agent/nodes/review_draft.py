from __future__ import annotations

from pathlib import Path

from research_agent.logging import ModelCallLogger
from research_agent.context import ContextManager
from research_agent.nodes.base import BaseNode
from research_agent.state import RunState
from research_agent.tools.llm_client import LLMClient


class ReviewDraftNode(BaseNode):
    name = "review_draft"

    def run(self, state: RunState) -> RunState:
        state.mark_running(self.name)
        logger = ModelCallLogger(self.run_dir)
        client = LLMClient(self.config, logger)
        evidence = []
        for key in ("summary_notes", "literature_matrix_md", "rag_answer"):
            path = state.artifacts.get(key)
            if path and Path(path).exists():
                evidence.append(Path(path).read_text(encoding="utf-8", errors="ignore"))
        evidence_text = ContextManager(self.run_dir, self.config.context_window).fit_text(
            "\n\n".join(evidence) or "No evidence available.",
            label="legacy-review-evidence",
            occupied={"topic": state.topic, "keywords": state.keywords},
            reserve_tokens=self.config.context_window // 3,
        )
        prompt = "\n\n".join(
            [
                f"Topic: {state.topic}",
                f"Keywords: {state.keywords}",
                "Create a literature review outline and first-draft framework grounded only in the evidence below.",
                evidence_text,
            ]
        )
        fallback = self._fallback_outline(state, evidence)
        result = client.complete("review_draft", prompt, fallback=fallback)
        out = self.run_dir / "review_framework.md"
        out.write_text(result.text, encoding="utf-8")
        state.add_artifact("review_framework", out)
        state.add_artifact("model_call_log", self.run_dir / "model_call_log.jsonl")
        state.mark_completed(self.name, "Review draft framework generated")
        return state

    def _fallback_outline(self, state: RunState, evidence: list[str]) -> str:
        return "\n".join(
            [
                "# Literature Review Framework",
                "",
                f"Topic: {state.topic}",
                "",
                "## 1. Research Background",
                "Summarize the problem setting and why the topic matters.",
                "",
                "## 2. Current Methods",
                "Use `literature_matrix.csv` and `summary_notes.md` to group methods.",
                "",
                "## 3. Innovations and Findings",
                "List evidence-backed innovations only. Mark items requiring full-text reading.",
                "",
                "## 4. Limitations and Gaps",
                "Separate documented limitations from hypotheses.",
                "",
                "## 5. Drafting Notes",
                "LLM API key not configured or remote call unavailable; this is a deterministic local framework.",
            ]
        )
