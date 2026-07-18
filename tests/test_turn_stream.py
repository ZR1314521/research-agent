from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json
import threading
import time
import unittest

from research_agent.config import AgentConfig
from research_agent.logging import ModelCallLogger
from research_agent.provider_runtime import ProviderEvent, call_context, provider_event_sink
from research_agent.tools.llm_client import ModelGateway
from research_agent.turns import ActiveTurnError, TurnControl, TurnCoordinator


ROOT = Path(__file__).resolve().parents[1]


class FakeStreamResponse:
    def __init__(self, chunks: list[dict]):
        self.lines = [f"data: {json.dumps(item)}\n".encode() for item in chunks] + [b"data: [DONE]\n"]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def __iter__(self):
        return iter(self.lines)


class ProviderStreamTests(unittest.TestCase):
    def test_stream_normalizes_text_and_fragmented_tool_calls(self) -> None:
        run_dir = ROOT / ".test_runtime" / "turn_stream" / "provider"
        run_dir.mkdir(parents=True, exist_ok=True)
        config = replace(
            AgentConfig.load(ROOT),
            llm_provider="compatible-test", llm_protocol="openai-compatible",
            llm_model="test-model", llm_base_url="https://example.invalid/v1",
            llm_api_key="key", llm_max_tokens=0, llm_retry=0,
        )
        chunks = [
            {"choices": [{"delta": {"content": "你"}, "finish_reason": None}]},
            {"choices": [{"delta": {"content": "好"}, "finish_reason": None}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call-1", "function": {"name": "workspace", "arguments": "{\"path\":"}}]}, "finish_reason": None}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "\".\"}"}}]}, "finish_reason": "tool_calls"}]},
            {"choices": [], "usage": {"total_tokens": 9}},
        ]
        events: list[ProviderEvent] = []
        captured: dict = {}

        def fake_urlopen(request, timeout):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeStreamResponse(chunks)

        gateway = ModelGateway(config, ModelCallLogger(run_dir))
        with call_context(turn_id="turn-one", operation="test"), patch(
            "research_agent.tools.llm_client.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            result = gateway.chat("test", [{"role": "user", "content": "hello"}], on_event=events.append)

        self.assertEqual(result.text, "你好")
        self.assertEqual(json.loads(result.tool_calls[0]["function"]["arguments"]), {"path": "."})
        self.assertTrue(captured["body"]["stream"])
        self.assertNotIn("max_tokens", captured["body"])

    def test_dsml_tool_calls_in_content_are_parsed_and_cleaned(self) -> None:
        from research_agent.tools.llm_client import _extract_tool_calls_from_content, _is_inside_fence

        real_sample = (
            "Crossref success.\n\n"
            "<tool_calls>\n"
            "<invoke name=\"literature-search-crossref\">\n"
            "<parameter name=\"query\" string=\"true\">EEG motor imagery CSP Riemannian</parameter>\n"
            "<parameter name=\"year_from\" string=\"false\">2022</parameter>\n"
            "<parameter name=\"year_to\" string=\"false\">2026</parameter>\n"
            "<parameter name=\"limit\" string=\"false\">20</parameter>\n"
            "</invoke>\n"
            "<invoke name=\"literature-search-crossref\">\n"
            "<parameter name=\"query\" string=\"true\">EEG motor imagery transfer learning</parameter>\n"
            "<parameter name=\"year_from\" string=\"false\">2022</parameter>\n"
            "<parameter name=\"year_to\" string=\"false\">2026</parameter>\n"
            "<parameter name=\"limit\" string=\"false\">20</parameter>\n"
            "</invoke>\n"
            "<invoke name=\"literature-search-crossref\">\n"
            "<parameter name=\"query\" string=\"true\">EEG motor imagery rehabilitation BCI</parameter>\n"
            "<parameter name=\"year_from\" string=\"false\">2022</parameter>\n"
            "<parameter name=\"year_to\" string=\"false\">2026</parameter>\n"
            "<parameter name=\"limit\" string=\"false\">20</parameter>\n"
            "</invoke>\n"
            "</tool_calls>"
        )
        clean, calls = _extract_tool_calls_from_content(real_sample)

        self.assertEqual(len(calls), 3)
        self.assertNotIn("<tool_calls>", clean)
        self.assertIn("Crossref success.", clean)
        for c in calls:
            args = json.loads(c["function"]["arguments"])
            self.assertIsInstance(args["query"], str)
            self.assertIsInstance(args["year_from"], int)
            self.assertIsInstance(args["limit"], int)
            self.assertEqual(c["function"]["name"], "literature-search-crossref")

        # Streaming chunks must not leak
        chunks = [real_sample[:40], real_sample[40:200], real_sample[200:400], real_sample[400:]]
        buf: list[str] = []
        leaked = False
        for ch in chunks:
            buf.append(ch)
            if not _is_inside_fence("".join(buf)):
                from research_agent.tools.llm_client import _strip_tool_call_text
                flushed = _strip_tool_call_text("".join(buf))
                if "<tool_calls>" in flushed or "<invoke>" in flushed:
                    leaked = True
                buf.clear()
        self.assertFalse(leaked, "DSML leaked during streaming")

    def test_real_namespaced_dsml_is_never_emitted_as_assistant_text(self) -> None:
        run_dir = ROOT / ".test_runtime" / "turn_stream" / "namespaced-dsml"
        run_dir.mkdir(parents=True, exist_ok=True)
        config = replace(
            AgentConfig.load(ROOT),
            llm_provider="compatible-test", llm_protocol="openai-compatible",
            llm_model="test-model", llm_base_url="https://example.invalid/v1",
            llm_api_key="key", llm_max_tokens=0, llm_retry=0,
        )
        sample = (
            "Crossref success.\n\n"
            "<｜｜DSML｜｜tool_calls>"
            "<｜｜DSML｜｜invoke name=\"literature-search-crossref\">"
            "<｜｜DSML｜｜parameter name=\"query\" string=\"true\">EEG motor imagery</｜｜DSML｜｜parameter>"
            "<｜｜DSML｜｜parameter name=\"limit\" string=\"false\">20</｜｜DSML｜｜parameter>"
            "</｜｜DSML｜｜invoke>"
            "</｜｜DSML｜｜tool_calls>"
        )
        split_at = (4, 19, 22, 39, 67, 121, 173, len(sample))
        pieces = [sample[start:end] for start, end in zip((0, *split_at[:-1]), split_at)]
        chunks = [
            {"choices": [{"delta": {"content": piece}, "finish_reason": None}]}
            for piece in pieces
        ]
        chunks[-1]["choices"][0]["finish_reason"] = "stop"
        events: list[ProviderEvent] = []

        gateway = ModelGateway(config, ModelCallLogger(run_dir))
        with patch(
            "research_agent.tools.llm_client.urllib.request.urlopen",
            return_value=FakeStreamResponse(chunks),
        ):
            result = gateway.chat("test", [{"role": "user", "content": "search"}], on_event=events.append)

        visible = "".join(
            str(event.data.get("text") or "")
            for event in events
            if event.kind == "assistant_delta"
        )
        self.assertEqual(visible.strip(), "Crossref success.")
        self.assertNotIn("DSML", visible)
        self.assertEqual(result.text, "Crossref success.")
        self.assertEqual(len(result.tool_calls), 1)
        self.assertEqual(result.tool_calls[0]["function"]["name"], "literature-search-crossref")
        self.assertEqual(json.loads(result.tool_calls[0]["function"]["arguments"])["limit"], 20)

    def test_inherited_turn_sink_keeps_internal_model_content_out_of_user_stream(self) -> None:
        run_dir = ROOT / ".test_runtime" / "turn_stream" / "internal-visibility"
        run_dir.mkdir(parents=True, exist_ok=True)
        config = replace(
            AgentConfig.load(ROOT),
            llm_provider="compatible-test", llm_protocol="openai-compatible",
            llm_model="test-model", llm_base_url="https://example.invalid/v1",
            llm_api_key="key", llm_max_tokens=0, llm_retry=0,
        )
        chunks = [
            {"choices": [{"delta": {"reasoning_content": "internal reasoning"}, "finish_reason": None}]},
            {"choices": [{"delta": {"content": '{"papers":['}, "finish_reason": None}]},
            {"choices": [{"delta": {"content": "]}"}, "finish_reason": "stop"}]},
            {"choices": [], "usage": {"total_tokens": 12}},
        ]
        events: list[ProviderEvent] = []

        def fake_urlopen(_request, timeout):
            self.assertGreater(timeout, 0)
            return FakeStreamResponse(chunks)

        gateway = ModelGateway(config, ModelCallLogger(run_dir))
        with provider_event_sink(events.append), patch(
            "research_agent.tools.llm_client.urllib.request.urlopen", side_effect=fake_urlopen
        ):
            result = gateway.complete("literature_semantic_screening", "screen these papers")

        self.assertEqual(result.text, '{"papers":[]}')
        self.assertTrue(any(event.kind == "provider_call_started" for event in events))
        self.assertTrue(any(event.kind == "provider_call_finished" for event in events))
        self.assertFalse(any(event.kind in {"assistant_delta", "reasoning_delta", "tool_call_delta"} for event in events))

class FakeSessions:
    def __init__(self, root: Path):
        self.root = root
        self.session = SimpleNamespace(
            session_id="run-one", pending_action=None, artifact_records={}, status="active",
        )

    def directory(self, _run_id: str) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    def load(self, _run_id: str):
        return self.session

    def event(self, *_args, **_kwargs):
        return None


class BlockingAgent:
    def __init__(self, root: Path):
        self.sessions = FakeSessions(root)
        self.config = AgentConfig.load(ROOT)
        self.started = threading.Event()

    def handle(self, session, _message, cancel_event=None, **_kwargs):
        self.started.set()
        while not cancel_event.is_set():
            time.sleep(0.01)
        return SimpleNamespace(session=session, message="cancelled", skill="")


class TurnCoordinatorTests(unittest.TestCase):
    def test_approval_resolution_leaves_the_waiting_boundary_atomically(self) -> None:
        root = ROOT / ".test_runtime" / "turn_stream" / "approval"
        root.mkdir(parents=True, exist_ok=True)
        control = TurnControl("run-one", root)
        decisions: list[bool | None] = []

        def worker() -> None:
            decisions.append(control.wait_for_approval())
            control.finish("completed", {"assistant_message": "continued"})

        thread = threading.Thread(target=worker)
        thread.start()
        deadline = time.time() + 1
        while control.state != "waiting_approval" and time.time() < deadline:
            time.sleep(0.01)

        self.assertEqual(control.resolve_approval(True), "resuming")
        self.assertEqual(control.resolve_approval(True), "resuming")
        self.assertEqual(control.wait_for_result_boundary(), "completed")
        thread.join(1)
        self.assertEqual(decisions, [True])
        self.assertEqual(
            len([event for event in control.events if event["event"] == "approval_resolved"]),
            1,
        )

    def test_only_one_active_turn_per_run(self) -> None:
        root = ROOT / ".test_runtime" / "turn_stream" / "coordinator"
        root.mkdir(parents=True, exist_ok=True)
        agent = BlockingAgent(root)
        coordinator = TurnCoordinator(agent)
        first = coordinator.start("run-one", "first")
        self.assertTrue(agent.started.wait(1))
        with self.assertRaises(ActiveTurnError) as caught:
            coordinator.start("run-one", "second")
        self.assertEqual(caught.exception.turn_id, first.turn_id)
        coordinator.cancel("run-one")

    def test_pause_and_resume_are_a_safe_boundary(self) -> None:
        root = ROOT / ".test_runtime" / "turn_stream" / "pause"
        root.mkdir(parents=True, exist_ok=True)
        control = TurnControl("run-one", root)
        control.state = "running"
        self.assertEqual(control.request_pause(), "pause_requested")
        result: list[bool] = []
        worker = threading.Thread(target=lambda: result.append(control.safe_boundary()))
        worker.start()
        deadline = time.time() + 1
        while control.state != "paused" and time.time() < deadline:
            time.sleep(0.01)
        self.assertEqual(control.state, "paused")
        self.assertEqual(control.resume(), "running")
        worker.join(1)
        self.assertEqual(result, [True])


if __name__ == "__main__":
    unittest.main()
