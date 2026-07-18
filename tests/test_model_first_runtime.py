from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from research_agent.acceptance import UserOutcomeObserver
from research_agent.capabilities.workspace import WorkspaceService
from research_agent.config import AgentConfig
from research_agent.core.agent import AgentLoop
from research_agent.logging import ModelCallLogger
from research_agent.session import SessionStore
from research_agent.skill_registry import SkillRegistry
from research_agent.tools.llm_client import LLMResult, ModelGateway


PROJECT = Path(__file__).resolve().parents[1]
TEST_TMP = PROJECT / ".test_runtime"


def native_tool_call(call_id: str = "call-1", arguments: dict | None = None) -> LLMResult:
    arguments = arguments or {"operation": "list", "path": "."}
    tool_calls = [{
        "id": call_id,
        "type": "function",
        "function": {
            "name": "workspace-files",
            "arguments": json.dumps(arguments),
        },
    }]
    return LLMResult(
        "", "test", "model", True,
        operation="agent_turn",
        outcome="native_tool_call",
        tool_calls=tool_calls,
        assistant_message={"role": "assistant", "tool_calls": tool_calls},
    )


def named_tool_call(name: str, arguments: dict, call_id: str = "call-control") -> LLMResult:
    tool_calls = [{
        "id": call_id, "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
    }]
    return LLMResult(
        "", "test", "model", True, operation="agent_turn", outcome="native_tool_call",
        tool_calls=tool_calls, assistant_message={"role": "assistant", "tool_calls": tool_calls},
    )


class ModelFirstRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        root = TEST_TMP / "agent"
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        base = AgentConfig.load(PROJECT)
        self.config = replace(
            base,
            root_dir=root,
            runs_dir=root / "runs",
            skills_dir=PROJECT / "skills",
            llm_provider="test",
            llm_model="model",
            llm_base_url="https://example.invalid/v1",
            llm_api_key="key",
            llm_retry=0,
            agent_emergency_turn_limit=6,
        )
        self.registry = SkillRegistry(self.config.skills_dir)
        self.sessions = SessionStore(self.config.runs_dir)
        self.session = self.sessions.create()

    def tearDown(self) -> None:
        self.sessions.close()

    def loop(self) -> AgentLoop:
        return AgentLoop(
            self.config,
            self.registry,
            self.sessions,
            self.sessions.directory(self.session.session_id),
        )

    def test_direct_answer_does_not_require_a_tool_or_json_decision(self) -> None:
        loop = self.loop()
        loop.client.chat = MagicMock(return_value=LLMResult(
            "你好，我在。", "test", "model", True,
            operation="agent_turn", outcome="text",
            assistant_message={"role": "assistant", "content": "你好，我在。"},
        ))
        loop.executor.execute = MagicMock()

        result = loop.run(self.session, "你好")

        self.assertEqual(result.message, "你好，我在。")
        loop.executor.execute.assert_not_called()
        self.assertEqual(self.session.model_messages[-1]["content"], "你好，我在。")

    def test_declared_file_arguments_are_scoped_and_resolved_by_the_executor(self) -> None:
        loop = self.loop()
        workspace_file = loop.executor.workspace_context.uploads_root / "notes.md"
        workspace_file.write_text("evidence", encoding="utf-8")
        captured: dict[str, str] = {}

        def inspect(arguments, _session):
            captured["path"] = arguments["path"]
            return {"message": "ok", "artifacts": {}, "data": {}}

        loop.executor.handlers["document_summary"] = inspect
        loop.executor.execute("document-summary", {"path": "uploads/notes.md"}, self.session)
        self.assertEqual(Path(captured["path"]), workspace_file.resolve())

        outside = self.root / "outside.md"
        outside.write_text("private", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "当前会话工作区"):
            loop.executor.execute("document-summary", {"path": str(outside)}, self.session)

    def test_file_producing_services_default_to_the_session_workspace(self) -> None:
        executor = self.loop().executor
        workspace = executor.workspace_context.workspace_root
        services = [
            executor.literature, executor.documents, executor.rag, executor.references,
            executor.data, executor.data_transform, executor.arxiv, executor.papers,
            executor.office_md,
        ]
        self.assertTrue(all(Path(service.session_dir).resolve() == workspace for service in services))

    def test_native_tool_messages_are_preserved_for_model_followup(self) -> None:
        loop = self.loop()
        captured: list[list[dict]] = []
        responses = iter([
            native_tool_call(),
            LLMResult(
                "我看到了 2 个文件。", "test", "model", True,
                operation="agent_turn", outcome="text",
                assistant_message={"role": "assistant", "content": "我看到了 2 个文件。"},
            ),
        ])

        def chat(*_args, **kwargs):
            captured.append(deepcopy(_args[1]))
            return next(responses)

        loop.client.chat = chat
        loop.executor.execute = MagicMock(return_value={
            "message": "a.md\nb.md",
            "artifacts": {},
            "data": {"files": ["a.md", "b.md"]},
        })

        result = loop.run(self.session, "看看目录里有什么")

        self.assertEqual(result.message, "我看到了 2 个文件。")
        self.assertEqual(loop.executor.execute.call_count, 1)
        self.assertEqual(captured[1][-2]["role"], "assistant")
        self.assertTrue(captured[1][-2]["tool_calls"])
        self.assertEqual(captured[1][-1]["role"], "tool")
        self.assertIn("a.md", captured[1][-1]["content"])

    def test_verified_tool_result_is_returned_if_model_followup_fails(self) -> None:
        loop = self.loop()
        loop.client.chat = MagicMock(side_effect=[
            native_tool_call(),
            LLMResult("", "test", "model", False, error="timeout", outcome="timeout"),
        ])
        loop.executor.execute = MagicMock(return_value={
            "message": "已生成：result.md",
            "artifacts": {"workspace_file": str(self.root / "result.md")},
            "data": {},
        })

        result = loop.run(self.session, "生成结果")

        self.assertEqual(result.message, "已生成：result.md")
        self.assertEqual(self.session.metadata["last_model_error"], "timeout")

    def test_declarative_direct_delivery_skips_wrap_up_call(self) -> None:
        loop = self.loop()
        tool_calls = [{
            "id": "call-summary",
            "type": "function",
            "function": {
                "name": "document-summary",
                "arguments": json.dumps({"path": "paper.md"}),
            },
        }]
        loop.client.chat = MagicMock(return_value=LLMResult(
            "", "test", "model", True,
            operation="agent_turn", outcome="native_tool_call",
            tool_calls=tool_calls,
            assistant_message={"role": "assistant", "tool_calls": tool_calls},
        ))
        loop.executor.execute = MagicMock(return_value={
            "message": "论文总结已生成。",
            "artifacts": {"document_summary": str(self.root / "summary.md")},
            "data": {},
        })

        result = loop.run(self.session, "总结这篇论文")

        self.assertEqual(result.message, "论文总结已生成。")
        self.assertEqual(loop.client.chat.call_count, 1)
        self.assertEqual(loop.executor.execute.call_count, 1)

    def test_outcome_observer_is_passive_and_writes_readable_report(self) -> None:
        observer = UserOutcomeObserver(self.root / "quality", self.registry)
        before = deepcopy(self.session.model_messages)
        record = observer.record(
            self.session,
            "请查看文件",
            "已经看过。",
            [{"event": "finished", "skill": "workspace-files", "summary": "done"}],
        )

        self.assertEqual(record["status"], "completed")
        self.assertEqual(self.session.model_messages, before)
        self.assertTrue(observer.records_path.exists())
        self.assertIn("不参与模型提示", observer.report_path.read_text(encoding="utf-8"))

    def test_protected_tool_waits_for_accept_before_side_effect(self) -> None:
        loop = self.loop()
        loop.client.chat = MagicMock(side_effect=[
            native_tool_call(arguments={"operation": "write", "path": "answer.md", "text": "done"}),
            LLMResult(
                "文件已经写好。", "test", "model", True,
                operation="agent_turn", outcome="text",
                assistant_message={"role": "assistant", "content": "文件已经写好。"},
            ),
        ])
        loop.executor.execute = MagicMock(return_value={"message": "written", "artifacts": {}, "data": {}})

        waiting = loop.run(self.session, "写入 answer.md")

        self.assertTrue(waiting.waiting)
        self.assertEqual(self.session.pending_action["type"], "tool_approval")
        loop.executor.execute.assert_not_called()

        finished = loop.resume(self.session, approved=True)

        self.assertEqual(finished.message, "文件已经写好。")
        loop.executor.execute.assert_called_once()
        self.assertIsNone(self.session.pending_action)

    def test_reject_skips_side_effect_and_returns_rejection_to_model(self) -> None:
        loop = self.loop()
        captured: list[list[dict]] = []
        responses = iter([
            native_tool_call(arguments={"operation": "delete", "path": "answer.md", "confirmed": True}),
            LLMResult(
                "好的，已取消删除。", "test", "model", True,
                operation="agent_turn", outcome="text",
                assistant_message={"role": "assistant", "content": "好的，已取消删除。"},
            ),
        ])

        def chat(*args, **_kwargs):
            captured.append(deepcopy(args[1]))
            return next(responses)

        loop.client.chat = chat
        loop.executor.execute = MagicMock()
        loop.run(self.session, "删除 answer.md")

        finished = loop.resume(self.session, approved=False)

        self.assertEqual(finished.message, "好的，已取消删除。")
        loop.executor.execute.assert_not_called()
        self.assertIn("rejected", captured[-1][-1]["content"].lower())

    def test_finished_plan_waits_and_accept_resumes_the_same_model_conversation(self) -> None:
        loop = self.loop()
        self.session.status = "planning"
        self.session.metadata["plan_mode"] = True
        loop.client.chat = MagicMock(side_effect=[
            named_tool_call("present-plan", {"content": "计划：先查看目录，再根据结果处理。"}),
            native_tool_call(arguments={"operation": "list", "path": "."}),
            LLMResult(
                "计划已经执行完成。", "test", "model", True,
                operation="agent_turn", outcome="text",
                assistant_message={"role": "assistant", "content": "计划已经执行完成。"},
            ),
        ])
        loop.executor.execute = MagicMock(return_value={"message": "listed", "artifacts": {}, "data": {}})

        waiting = loop.run(self.session, "先规划如何处理")

        self.assertTrue(waiting.waiting)
        self.assertEqual(self.session.pending_action["type"], "plan_approval")
        loop.executor.execute.assert_not_called()

        finished = loop.resume(self.session, approved=True)

        self.assertEqual(finished.message, "计划已经执行完成。")
        self.assertEqual(self.session.status, "active")
        self.assertNotIn("plan_mode", self.session.metadata)
        loop.executor.execute.assert_called_once()

    def test_plan_clarification_does_not_request_execution_approval(self) -> None:
        loop = self.loop()
        self.session.status = "planning"
        self.session.metadata["plan_mode"] = True
        loop.client.chat = MagicMock(return_value=LLMResult(
            "你希望先做实证论文还是综述？", "test", "model", True,
            operation="agent_turn", outcome="text",
            assistant_message={"role": "assistant", "content": "你希望先做实证论文还是综述？"},
        ))

        response = loop.run(self.session, "帮我规划论文")

        self.assertFalse(response.waiting)
        self.assertEqual(response.message, "你希望先做实证论文还是综述？")
        self.assertEqual(self.session.status, "planning")
        self.assertIsNone(self.session.pending_action)


class WorkspaceServiceTests(unittest.TestCase):
    def test_workspace_operations_are_scoped_to_the_current_session(self) -> None:
        root = TEST_TMP / "workspace"
        session_dir = root / "runs" / "one"
        session_dir.mkdir(parents=True, exist_ok=True)
        service = WorkspaceService(root, session_dir)
        workspace = session_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "notes.md").write_text("first\nneedle here\nthird\nfourth\n", encoding="utf-8")

        tail = service.operate({"operation": "read", "path": "notes.md", "limit": 2, "tail": True})
        found = service.operate({"operation": "search", "path": ".", "query": "needle"})
        root_listing = service.operate({"operation": "list", "path": "/"})

        self.assertIn("3: third", tail["message"])
        self.assertEqual(found["data"]["matches"][0]["line"], 2)
        self.assertIn("needle here", found["data"]["matches"][0]["text"])
        self.assertIn("notes.md", root_listing["data"]["files"])
        outside = root.parent / "outside.txt"
        outside.write_text("global workspace file", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "当前会话工作区"):
            service.operate({"operation": "read", "path": str(outside)})

        other_session = root / "runs" / "two" / "workspace"
        other_session.mkdir(parents=True, exist_ok=True)
        other_file = other_session / "private.txt"
        other_file.write_text("other session", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "当前会话工作区"):
            service.operate({"operation": "read", "path": str(other_file)})


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class GatewayProtocolTests(unittest.TestCase):
    def test_chat_uses_native_messages_and_preserves_reasoning_tool_call(self) -> None:
        root = TEST_TMP / "gateway"
        root.mkdir(parents=True, exist_ok=True)
        config = replace(
            AgentConfig.load(PROJECT),
            root_dir=root,
            runs_dir=root / "runs",
            llm_provider="deepseek",
            llm_model="deepseek-reasoner",
                llm_base_url="https://api.deepseek.com",
                llm_api_key="key",
                llm_max_tokens=0,
                llm_retry=0,
        )
        gateway = ModelGateway(config, ModelCallLogger(root))
        tool_calls = [{
            "id": "call-9",
            "type": "function",
            "function": {"name": "demo", "arguments": "{}"},
        }]
        payload = {
            "choices": [{
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "reasoning_content": "reasoning token",
                    "tool_calls": tool_calls,
                },
            }],
        }
        captured = {}

        def fake_urlopen(request, timeout):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeResponse(payload)

        tools = [{"type": "function", "function": {"name": "demo", "description": "demo", "parameters": {"type": "object", "properties": {}}}}]
        with patch("research_agent.tools.llm_client.urllib.request.urlopen", side_effect=fake_urlopen):
            result = gateway.chat("agent_turn", [{"role": "user", "content": "look"}], system="system", tools=tools)

            self.assertNotIn("response_format", captured["body"])
            self.assertNotIn("max_tokens", captured["body"])
        self.assertEqual(captured["body"]["messages"][1]["content"], "look")
        self.assertEqual(result.assistant_message["reasoning_content"], "reasoning token")
        self.assertEqual(result.tool_calls, tool_calls)


if __name__ == "__main__":
    unittest.main()
