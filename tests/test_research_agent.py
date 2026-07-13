from __future__ import annotations

import json
import http.client
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from research_agent.capabilities.rag import RagService
from research_agent.chat import ResearchChatAgent
from research_agent.config import AgentConfig
from research_agent.planner import RulePlanner
from research_agent.logging import ModelCallLogger
from research_agent.session import ChatSession
from research_agent.skill_registry import SkillRegistry
from research_agent.tools.llm_client import LLMClient, LLMResult
from research_agent.workflow import ResearchWorkflow


ROOT = Path(__file__).resolve().parents[1]


def model_text(text: str) -> LLMResult:
    return LLMResult(text, "test", "model", True, outcome="text", assistant_message={"role": "assistant", "content": text})


def model_tool(name: str, arguments: dict) -> LLMResult:
    calls = [{"id": "call-1", "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}]
    return LLMResult("", "test", "model", True, outcome="native_tool_call", tool_calls=calls, assistant_message={"role": "assistant", "tool_calls": calls})


class ResearchAgentWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = ROOT / ".test_runs" / self.id().replace(".", "_")
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.tmp.mkdir(parents=True, exist_ok=True)
        self.config = AgentConfig.load(ROOT)
        object.__setattr__(self.config, "runs_dir", self.tmp / "runs")
        object.__setattr__(self.config, "llm_api_key", "")
        self.workflow = ResearchWorkflow(self.config)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_inputs(self) -> tuple[Path, Path]:
        papers = self.tmp / "papers.json"
        papers.write_text(
            json.dumps(
                [
                    {
                        "title": "Agent workflow literature review automation",
                        "authors": ["Li Wei", "Jane Doe"],
                        "year": 2024,
                        "venue": "IEEE Access",
                        "abstract": "Agent workflow RAG screening for literature review automation.",
                        "doi": "10.1109/access.2024.1",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        data = self.tmp / "data.csv"
        data.write_text("epoch,accuracy,loss\n1,0.7,0.9\n2,0.8,0.6\n3,0.9,0.4\n", encoding="utf-8")
        return papers, data

    def test_create_upload_and_local_workflow(self) -> None:
        papers, data = self._write_inputs()
        state = self.workflow.create_run(
            topic="AI research agent literature review automation",
            keywords="agent workflow RAG screening",
            venues="IEEE",
            year_from=2022,
        )
        state = self.workflow.add_uploads(state.run_id, [str(papers), str(data)], copy=True)
        self.assertIn("upload_manifest", state.artifacts)
        state = self.workflow.start(state.run_id, sources=[], styles=["gbt7714-numeric", "ieee", "nature"])
        self.assertEqual(state.status, "completed")
        run_dir = self.workflow.run_dir(state.run_id)
        self.assertTrue((run_dir / "workflow_state.json").exists())
        self.assertTrue((run_dir / "screened_papers.json").exists())
        self.assertTrue((run_dir / "literature_matrix.csv").exists())
        self.assertTrue((run_dir / "rag_index" / "chunks.jsonl").exists())
        self.assertTrue((run_dir / "model_call_log.jsonl").exists())
        self.assertTrue((run_dir / "references_gbt7714_numeric.md").exists())


class ResearchChatAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = ROOT / ".test_runs" / self.id().replace(".", "_")
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.tmp.mkdir(parents=True, exist_ok=True)
        self.config = AgentConfig.load(ROOT)
        object.__setattr__(self.config, "runs_dir", self.tmp / "runs")
        object.__setattr__(self.config, "llm_api_key", "test-key")
        self.agent = ResearchChatAgent(self.config)

    def tearDown(self) -> None:
        self.agent.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_local_skill_registry_is_complete(self) -> None:
        registry = SkillRegistry(ROOT / "skills")
        self.assertGreaterEqual(len(registry.all()), 24)
        for skill in registry.all():
            content = (ROOT / "skills" / skill.name / "SKILL.md").read_text(encoding="utf-8")
            self.assertNotIn("TODO", content)

    def test_rule_planner_understands_three_year_search(self) -> None:
        plan = RulePlanner().plan("找近3年的CNN BCI EEG论文", ChatSession.create())
        self.assertEqual(plan.action.skill, "academic-search-multisource")
        self.assertEqual(plan.action.arguments["query"], "CNN BCI EEG")
        self.assertEqual(plan.action.arguments["year_to"] - plan.action.arguments["year_from"], 2)

    def test_rule_planner_keeps_writing_and_search_separate(self) -> None:
        writing = RulePlanner().plan("帮我写论文引言", ChatSession.create())
        self.assertEqual(writing.action.skill, "20-ml-paper-writing")
        search = RulePlanner().plan('找5篇CNN EEG论文并保存到 "D:\\results\\papers.docx"', ChatSession.create())
        self.assertEqual(search.action.skill, "academic-search-multisource")
        self.assertEqual(search.action.arguments["output_path"], "D:\\results\\papers.docx")

    def test_model_incomplete_read_uses_fallback(self) -> None:
        config = AgentConfig.load(ROOT)
        object.__setattr__(config, "llm_api_key", "fake-key")
        with patch("urllib.request.urlopen", side_effect=http.client.IncompleteRead(b"")):
            result = LLMClient(config, ModelCallLogger(self.tmp)).complete("test", "prompt", fallback="fallback")
        self.assertEqual(result.text, "fallback")
        self.assertFalse(result.used_remote_model)

    def test_follow_up_summarizes_existing_pool_without_search(self) -> None:
        session = self.agent.new_session()
        papers = self.agent.sessions.directory(session.session_id) / "screened_papers.json"
        papers.write_text(
            json.dumps(
                [
                    {
                        "title": "CNN decoding of EEG for motor imagery BCI",
                        "authors": ["Li Wei"],
                        "year": 2025,
                        "venue": "IEEE Transactions on Neural Systems",
                        "abstract": "A convolutional neural network decodes motor imagery EEG for a brain-computer interface.",
                        "doi": "10.1000/example",
                        "url": "https://example.org/paper",
                        "relevance_score": 92,
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        session.artifacts["active_papers"] = str(papers)
        self.agent.sessions.save(session)
        with patch("research_agent.tools.llm_client.LLMClient.chat", side_effect=[
            model_tool("literature-matrix-extraction", {}), model_text("文献矩阵已生成。"),
        ]):
            response = self.agent.handle(session, "这些论文都大概是什么？")
        self.assertEqual(response.skill, "literature-matrix-extraction")
        self.assertTrue(Path(response.session.artifacts["literature_matrix_md"]).exists())
        self.assertNotIn("academic-search-multisource", [event.get("skill") for event in response.session.events])

    def test_data_analysis_and_rag(self) -> None:
        session = self.agent.new_session()
        data = self.tmp / "experiment.csv"
        data.write_text("epoch,group,accuracy\n1,A,0.70\n2,A,0.75\n3,B,0.82\n4,B,0.95\n", encoding="utf-8")
        with patch("research_agent.tools.llm_client.LLMClient.chat", side_effect=[
            model_tool("experiment-data-analysis", {"path": str(data)}), model_text("实验分析完成。"),
        ]):
            response = self.agent.handle(session, f'分析实验数据 "{data}" 的异常值和趋势')
        self.assertEqual(response.skill, "experiment-data-analysis")
        self.assertTrue(Path(response.session.artifacts["analysis_report"]).exists())
        rag = RagService(self.config, self.agent.sessions.directory(session.session_id)).query(
            {"query": "accuracy trend", "top_k": 3}, response.session.artifacts
        )
        self.assertTrue(Path(rag["artifacts"]["retrieval_log"]).exists())
        self.assertTrue(rag["data"]["results"])

    def test_reference_format_from_active_pool(self) -> None:
        session = self.agent.new_session()
        papers = self.agent.sessions.directory(session.session_id) / "screened_papers.json"
        papers.write_text(
            json.dumps(
                [
                    {
                        "title": "EEG decoding with convolutional networks",
                        "authors": ["Li Wei", "Jane Doe"],
                        "year": 2025,
                        "venue": "IEEE Access",
                        "volume": "13",
                        "pages": "1-9",
                        "doi": "10.1000/example",
                    }
                ]
            ),
            encoding="utf-8",
        )
        session.artifacts["active_papers"] = str(papers)
        self.agent.sessions.save(session)
        with patch("research_agent.tools.llm_client.LLMClient.chat", return_value=model_tool(
            "reference-format-gbt7714", {"styles": ["gbt7714-numeric", "ieee"]},
        )):
            response = self.agent.handle(session, "把这些参考文献转成GB/T 7714和IEEE格式")
        self.assertEqual(response.skill, "reference-format-gbt7714")
        self.assertTrue(Path(response.session.artifacts["citation_check_report"]).exists())
        self.assertTrue(Path(response.session.artifacts["references_ieee"]).exists())


if __name__ == "__main__":
    unittest.main()
