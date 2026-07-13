from __future__ import annotations

import io
import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from research_agent.config import AgentConfig
from research_agent.core.agent import AgentLoop
from research_agent.core.contracts import ContractError, register_artifacts, validate_result_quality
from research_agent.core.prompt_runtime import PromptRuntime
from research_agent.chat import ResearchChatAgent
from research_agent.capabilities.files import FileService
from research_agent.capabilities.references import ReferenceService
from research_agent.capabilities.writing import WritingService
from research_agent.session import ChatSession, SessionStore
from research_agent.skill_registry import SkillRegistry
from research_agent.tools.llm_client import LLMResult
from research_agent.tools.llm_client import LLMClient
from research_agent.logging import ModelCallLogger


ROOT = Path(__file__).resolve().parents[1]


def text_response(text: str) -> LLMResult:
    return LLMResult(
        text, "test", "test", True, outcome="text",
        assistant_message={"role": "assistant", "content": text},
    )


def tool_response(name: str, arguments: dict, call_id: str = "call-1") -> LLMResult:
    calls = [{
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
    }]
    return LLMResult(
        "", "test", "test", True, outcome="native_tool_call",
        tool_calls=calls,
        assistant_message={"role": "assistant", "content": None, "tool_calls": calls},
    )


class AgentCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = ROOT / ".test_runs" / self.id().replace(".", "_")
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.tmp.mkdir(parents=True, exist_ok=True)
        self.config = AgentConfig.load(ROOT)
        object.__setattr__(self.config, "runs_dir", self.tmp / "runs")
        object.__setattr__(self.config, "llm_api_key", "test-key")
        self.registry = SkillRegistry(self.config.skills_dir)
        self.sessions = SessionStore(self.config.runs_dir)
        self.session = self.sessions.create()

    def tearDown(self) -> None:
        self.sessions.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_model_decides_conversation_without_hardcoded_reply(self) -> None:
        loop = AgentLoop(
            self.config,
            self.registry,
            self.sessions,
            self.sessions.directory(self.session.session_id),
        )
        with patch.object(
            loop.client,
            "chat",
            return_value=text_response("我是科研智能体，可以帮你处理文献和实验数据。"),
        ):
            result = loop.run(self.session, "你是谁")
        self.assertIn("科研智能体", result.message)
        self.assertEqual(result.skill, "")
        self.assertEqual(self.session.events[-1]["event"], "finished")

    def test_chat_uses_agent_loop_when_model_is_configured(self) -> None:
        agent = ResearchChatAgent(self.config)
        self.addCleanup(agent.close)
        session = agent.new_session()
        with patch(
            "research_agent.tools.llm_client.LLMClient.chat",
            return_value=text_response("模型驱动的自然回答。"),
        ):
            response = agent.handle(session, "你是谁")
        self.assertEqual(response.message, "模型驱动的自然回答。")
        self.assertEqual(response.skill, "")

    def test_tool_observation_is_replanned(self) -> None:
        loop = AgentLoop(
            self.config,
            self.registry,
            self.sessions,
            self.sessions.directory(self.session.session_id),
        )
        calls = iter(
            [
                tool_response("workspace-files", {"operation": "list", "path": "."}),
                text_response("我检查完了，当前没有失败请求。"),
            ]
        )
        loop.executor.execute = lambda tool, arguments, session: {
            "message": "请求 0 次，暂无失败。",
            "artifacts": {},
            "data": {"request_count": 0},
        }
        with patch.object(loop.client, "chat", side_effect=lambda *args, **kwargs: next(calls)) as mocked:
            result = loop.run(self.session, "刚才请求了几次")
        self.assertIn("检查完了", result.message)
        self.assertEqual(mocked.call_count, 2)
        self.assertIn("tool_observed", [event["event"] for event in self.session.events])
        self.assertEqual(self.session.model_messages[-2]["role"], "tool")

    def test_existing_artifacts_do_not_force_network_confirmation(self) -> None:
        loop = AgentLoop(
            self.config,
            self.registry,
            self.sessions,
            self.sessions.directory(self.session.session_id),
        )
        self.session.artifacts["active_papers"] = str(self.tmp / "papers.json")
        executed: list[str] = []
        loop.executor.execute = lambda tool, arguments, session: (
            executed.append(tool)
            or {"message": "补充检索完成。", "artifacts": {}, "data": {}}
        )
        with patch.object(
            loop.client,
            "chat",
            side_effect=[
                tool_response("academic-search-multisource", {"query": "EEG"}),
                text_response("补充检索完成。"),
            ],
        ):
            result = loop.run(self.session, "补充一些文献")
        self.assertFalse(result.waiting)
        self.assertEqual(executed, ["academic-search-multisource"])

    def test_prompt_runtime_contains_reuse_first_policy(self) -> None:
        runtime = PromptRuntime(self.registry)
        prompt = runtime.system(self.session)
        self.assertIn("已有成果", prompt)
        self.assertIn("当前消息优先于旧任务", prompt)
        self.assertTrue(runtime.tools_for_llm())

    def test_unconfigured_model_does_not_echo_internal_prompt(self) -> None:
        object.__setattr__(self.config, "llm_api_key", "")
        client = LLMClient(self.config, ModelCallLogger(self.sessions.directory(self.session.session_id)))
        result = client.complete("test", "SECRET_INTERNAL_PROMPT", fallback="")
        self.assertFalse(result.used_remote_model)
        self.assertNotIn("SECRET_INTERNAL_PROMPT", result.text)

    def test_model_text_response_is_classified_as_text(self) -> None:
        payload = {"choices": [{"finish_reason": "stop", "message": {"content": "  usable answer  "}}]}
        client = LLMClient(self.config, ModelCallLogger(self.sessions.directory(self.session.session_id)))
        with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(payload).encode("utf-8"))):
            result = client.complete("test", "prompt", fallback="fallback")
        self.assertEqual(result.text, "usable answer")
        self.assertTrue(result.used_remote_model)
        self.assertEqual(result.outcome, "text")

    def test_model_reasoning_without_final_content_is_not_generic_empty_response(self) -> None:
        payload = {"choices": [{"finish_reason": "stop", "message": {"content": None, "reasoning_content": "private chain of thought"}}]}
        run_dir = self.sessions.directory(self.session.session_id)
        client = LLMClient(self.config, ModelCallLogger(run_dir))
        with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(payload).encode("utf-8"))):
            result = client.complete("test", "prompt", fallback="fallback")
        self.assertEqual(result.text, "fallback")
        self.assertEqual(result.error, "reasoning_incomplete")
        self.assertEqual(result.outcome, "reasoning_incomplete")
        log_text = (run_dir / "model_call_log.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("private chain of thought", log_text)
        self.assertEqual(json.loads(log_text)["metadata"]["response_shape"]["reasoning_chars"], len("private chain of thought"))

    def test_model_length_exhaustion_is_not_generic_empty_response(self) -> None:
        payload = {"choices": [{"finish_reason": "length", "message": {"content": ""}}]}
        client = LLMClient(self.config, ModelCallLogger(self.sessions.directory(self.session.session_id)))
        with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(payload).encode("utf-8"))):
            result = client.complete("test", "prompt", fallback="fallback")
        self.assertEqual(result.text, "fallback")
        self.assertEqual(result.error, "output_exhausted")
        self.assertEqual(result.outcome, "output_exhausted")

    def test_model_native_tool_calls_are_not_parsed_as_text(self) -> None:
        payload = {"choices": [{"finish_reason": "tool_calls", "message": {"content": None, "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "search", "arguments": "{}"}}]}}]}
        client = LLMClient(self.config, ModelCallLogger(self.sessions.directory(self.session.session_id)))
        with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(payload).encode("utf-8"))):
            result = client.complete("test", "prompt", fallback="fallback")
        self.assertEqual(result.text, "")
        self.assertTrue(result.tool_calls)
        self.assertEqual(result.outcome, "native_tool_call")

    def test_model_tool_calls_take_precedence_over_mixed_content(self) -> None:
        payload = {"choices": [{"finish_reason": "tool_calls", "message": {"content": "Do not treat this as a final answer", "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "search", "arguments": "{}"}}]}}]}
        client = LLMClient(self.config, ModelCallLogger(self.sessions.directory(self.session.session_id)))
        with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(payload).encode("utf-8"))):
            result = client.complete("test", "prompt", fallback="fallback")
        self.assertTrue(result.tool_calls)
        self.assertEqual(result.outcome, "native_tool_call")

    def test_reasoning_incomplete_waits_for_a_retry_without_running_a_tool(self) -> None:
        loop = AgentLoop(self.config, self.registry, self.sessions, self.sessions.directory(self.session.session_id))
        loop.executor.execute = lambda *args: self.fail("tool must not run")
        with patch.object(
            loop.client,
            "chat",
            return_value=LLMResult("", "test", "test", False, "reasoning_incomplete", "agent_decision", 1, "reasoning_incomplete"),
        ):
            result = loop.run(self.session, "继续当前研究任务")
        self.assertTrue(result.waiting)
        self.assertIn("尚未生成最终回答", result.message)
        self.assertNotIn("API key", result.message)
        self.assertEqual(self.session.status, "waiting_user")
        self.assertEqual(self.session.pending_action, {
            "type": "retry_current_request",
            "outcome": "reasoning_incomplete",
        })
        self.assertEqual(self.session.events[-1]["outcome"], "reasoning_incomplete")

    def test_output_exhausted_waits_for_a_retry_without_running_a_tool(self) -> None:
        loop = AgentLoop(self.config, self.registry, self.sessions, self.sessions.directory(self.session.session_id))
        loop.executor.execute = lambda *args: self.fail("tool must not run")
        with patch.object(
            loop.client,
            "chat",
            return_value=LLMResult("", "test", "test", False, "output_exhausted", "agent_decision", 1, "output_exhausted"),
        ):
            result = loop.run(self.session, "继续当前研究任务")
        self.assertTrue(result.waiting)
        self.assertIn("尚未生成最终回答", result.message)
        self.assertNotIn("模型地址", result.message)
        self.assertEqual(self.session.status, "waiting_user")
        self.assertEqual(self.session.pending_action["type"], "retry_current_request")
        self.assertEqual(self.session.events[-1]["outcome"], "output_exhausted")

    def test_repair_reasoning_incomplete_waits_for_a_retry(self) -> None:
        loop = AgentLoop(self.config, self.registry, self.sessions, self.sessions.directory(self.session.session_id))
        with patch.object(
            loop.client, "chat",
            return_value=LLMResult("", "test", "test", False, "model_request_failed", "agent_turn", 1, "reasoning_incomplete"),
        ):
            result = loop.run(self.session, "继续当前研究任务")
        self.assertTrue(result.waiting)
        self.assertEqual(self.session.status, "waiting_user")
        self.assertEqual(self.session.pending_action["outcome"], "reasoning_incomplete")

    def test_repair_output_exhausted_waits_for_a_retry(self) -> None:
        loop = AgentLoop(self.config, self.registry, self.sessions, self.sessions.directory(self.session.session_id))
        with patch.object(
            loop.client, "chat",
            return_value=LLMResult("", "test", "test", False, "model_request_failed", "agent_turn", 1, "output_exhausted"),
        ):
            result = loop.run(self.session, "继续当前研究任务")
        self.assertTrue(result.waiting)
        self.assertEqual(self.session.status, "waiting_user")
        self.assertEqual(self.session.pending_action["outcome"], "output_exhausted")

    def test_model_outcome_is_authoritative_over_error(self) -> None:
        loop = AgentLoop(self.config, self.registry, self.sessions, self.sessions.directory(self.session.session_id))
        with patch.object(
            loop.client,
            "chat",
            return_value=LLMResult("", "test", "test", False, "TimeoutError: timed out", "agent_decision", 1, "reasoning_incomplete"),
        ):
            result = loop.run(self.session, "继续当前研究任务")
        self.assertTrue(result.waiting)
        self.assertIn("尚未生成最终回答", result.message)
        self.assertNotIn("API key", result.message)
        self.assertEqual(self.session.events[-1]["outcome"], "reasoning_incomplete")

    def test_native_tool_call_is_an_unsupported_provider_error_without_running_a_tool(self) -> None:
        loop = AgentLoop(self.config, self.registry, self.sessions, self.sessions.directory(self.session.session_id))
        loop.executor.execute = lambda *args: self.fail("tool must not run")
        with patch.object(
            loop.client,
            "chat",
            return_value=LLMResult("", "test", "test", False, "native_tool_call", "agent_decision", 1, "native_tool_call"),
        ):
            result = loop.run(self.session, "搜索论文")
        self.assertFalse(result.waiting)
        self.assertIn("模型服务当前不可用", result.message)
        self.assertEqual(self.session.pending_action, None)
        self.assertEqual(self.session.events[-1]["outcome"], "native_tool_call")

    def test_transport_failure_keeps_the_unavailable_model_message(self) -> None:
        loop = AgentLoop(self.config, self.registry, self.sessions, self.sessions.directory(self.session.session_id))
        loop.executor.execute = lambda *args: self.fail("tool must not run")
        with patch.object(
            loop.client,
            "chat",
            return_value=LLMResult("", "test", "test", False, "TimeoutError: timed out", "agent_decision", 1, ""),
        ):
            result = loop.run(self.session, "搜索论文")
        self.assertFalse(result.waiting)
        self.assertIn("模型服务当前不可用", result.message)
        self.assertEqual(self.session.events[-1]["error"], "TimeoutError: timed out")

    def test_file_upload_accepts_model_local_file_path_alias(self) -> None:
        source = self.tmp / "paper.docx"
        source.write_bytes(b"not-a-real-docx-but-a-local-upload")
        result = FileService(self.sessions.directory(self.session.session_id)).register(
            {"local_file_path": str(source)}
        )
        self.assertEqual(result["data"]["files"][0]["status"], "registered")

    def test_document_summary_prompt_carries_request_and_evidence_boundary(self) -> None:
        service = WritingService(self.config, self.sessions.directory(self.session.session_id))
        request = "请详细解释这篇文章的贡献"
        with patch.object(
            service.client,
            "complete",
            return_value=LLMResult("## 问题\n\n已说明。", "test", "test", True),
        ) as model:
            result = service.summarize_document("The paper evaluates a model.", {"request": request})

        prompt = model.call_args.args[1]
        self.assertIn(request, prompt)
        self.assertIn("禁止编造", prompt)
        self.assertIn("详细", prompt)
        self.assertTrue(Path(result["artifacts"]["document_summary"]).exists())

    def test_reference_service_extracts_references_from_docx(self) -> None:
        from docx import Document

        source = self.tmp / "references.docx"
        document = Document()
        document.add_heading("References", level=1)
        document.add_paragraph("Smith, J. (2024). EEG biomarkers for depression. Journal of EEG, 12, 1-10.")
        document.save(source)
        service = ReferenceService(self.config, self.sessions.directory(self.session.session_id))
        parsed = '[{"id":"smith2024","type":"article-journal","authors":["John Smith"],"title":"EEG biomarkers for depression","year":"2024","venue":"Journal of EEG","volume":"12","pages":"1-10"}]'
        before = source.read_bytes()
        with patch(
            "research_agent.tools.llm_client.LLMClient.complete",
            return_value=LLMResult(parsed, "test", "test", True),
        ) as model:
            result = service.format({"path": str(source), "styles": ["nature"]}, {})
        records = __import__("json").loads(
            Path(result["artifacts"]["reference_input_normalized"]).read_text(encoding="utf-8")
        )
        self.assertEqual(records[0]["title"], "EEG biomarkers for depression")
        self.assertTrue(Path(result["artifacts"]["references_nature"]).exists())
        self.assertEqual(source.read_bytes(), before)
        model.assert_not_called()

    def test_reference_colon_creates_full_nature_copy_and_skips_sections(self) -> None:
        from docx import Document

        source = self.tmp / "article.docx"
        document = Document()
        document.add_heading("1. Introduction", level=1)
        document.add_paragraph("This sentence cites [1].")
        document.add_heading("Reference:", level=1)
        document.add_paragraph("Li A, Wang B. EEG decoding with a compact model[J]. Journal of EEG, 2024, 12(1): 1-9.")
        document.add_paragraph("Chen C, Zhao D. Transformer EEG classification[J]. Neural Systems, 2023, 8(2): 10-20.")
        document.save(source)
        before = source.read_bytes()
        result = ReferenceService(self.config, self.sessions.directory(self.session.session_id)).format(
            {"path": str(source), "styles": ["nature"], "convert_in_text": True}, {}
        )
        output = Path(result["artifacts"]["nature_document"])
        self.assertTrue(output.exists())
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(result["data"]["reference_count"], 2)
        self.assertEqual(result["data"]["in_text_citations"]["converted"], 1)
        rendered = Path(result["artifacts"]["references_nature"]).read_text(encoding="utf-8")
        self.assertNotIn("NEEDS_CHECK", rendered)
        self.assertIn("Li, A.", rendered)
        text = "\n".join(paragraph.text for paragraph in Document(output).paragraphs)
        self.assertIn("References", text)
        self.assertNotIn("1. Introduction", Path(result["artifacts"]["reference_input_normalized"]).read_text(encoding="utf-8"))

    def test_numbered_sections_are_not_a_reference_fallback(self) -> None:
        from docx import Document

        source = self.tmp / "no_references.docx"
        document = Document()
        for title in ("1. Introduction", "2. Methods", "3. Conclusion"):
            document.add_heading(title, level=1)
        document.save(source)
        with self.assertRaisesRegex(ValueError, "No reference section"):
            ReferenceService(self.config, self.sessions.directory(self.session.session_id)).format(
                {"path": str(source), "styles": ["nature"]}, {}
            )

    def test_quality_boundary_rejects_missing_artifact(self) -> None:
        with self.assertRaisesRegex(ContractError, "missing artifacts"):
            validate_result_quality({"artifacts": {"report": str(self.tmp / "missing.md")}, "data": {}})

    def test_task_plan_is_model_generated_and_revisable(self) -> None:
        loop = AgentLoop(self.config, self.registry, self.sessions, self.sessions.directory(self.session.session_id))
        self.session.status = "planning"
        with patch.object(loop.client, "chat", return_value=text_response("1. 读取文档\n2. 转换并验收")):
            result = loop.run(self.session, "convert this document")
        self.assertTrue(result.waiting)
        self.assertEqual(self.session.pending_action["type"], "plan_approval")
        self.assertIn("读取文档", result.message)

    def test_contract_rejects_ignored_parameters_and_replans(self) -> None:
        loop = AgentLoop(self.config, self.registry, self.sessions, self.sessions.directory(self.session.session_id))
        calls = iter([
            tool_response("doc-coauthoring", {"source": "latest_document", "instruction": "extract references"}),
            text_response("该工具不能提取参考文献；我需要改用引用格式化工具。"),
        ])
        with patch.object(loop.client, "chat", side_effect=lambda *args, **kwargs: next(calls)):
            result = loop.run(self.session, "为什么刚才失败")
        self.assertIn("不能提取参考文献", result.message)
        observed = [event for event in self.session.events if event["event"] == "tool_observed"][-1]
        self.assertEqual(observed["error_code"], "unknown_argument")

    def test_artifact_ledger_uses_types_not_only_paths(self) -> None:
        spec = self.registry.get("file-upload-router")
        register_artifacts(self.session, spec, {"latest_document": str(self.tmp / "paper.docx")})
        self.assertEqual(self.session.artifact_records["latest_document"]["type"], "WordDocument")
        self.assertEqual(self.session.artifact_records["latest_document"]["producer"], "file-upload-router")

    def test_prompt_excludes_large_stale_result_payloads(self) -> None:
        self.session.metadata["last_result"] = {"huge": "x" * 50000}
        prompt = PromptRuntime(self.registry).system(self.session)
        self.assertNotIn("x" * 1000, prompt)

    def test_review_outline_returns_to_model_without_hidden_workflow(self) -> None:
        loop = AgentLoop(
            self.config,
            self.registry,
            self.sessions,
            self.sessions.directory(self.session.session_id),
        )
        loop.executor.execute = lambda tool, arguments, session: {
            "message": "综述大纲已生成。",
            "artifacts": {"review_framework": str(self.tmp / "review_framework.md")},
            "data": {"stage": "outline", "requires_confirmation": True},
        }
        with patch.object(
            loop.client,
            "chat",
            side_effect=[
                tool_response("systematic-literature-review", {"stage": "outline"}),
                text_response("综述大纲已生成，是否继续撰写由你决定。"),
            ],
        ):
            result = loop.run(self.session, "用已有论文写综述")
        self.assertFalse(result.waiting)
        self.assertIn("大纲已生成", result.message)
        self.assertIsNone(self.session.pending_action)


if __name__ == "__main__":
    unittest.main()
