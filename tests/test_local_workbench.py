from __future__ import annotations

import json
import shutil
import threading
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from research_agent.app import create_app
from research_agent.chat import ResearchChatAgent
from research_agent.config import AgentConfig
from research_agent.turns import TurnControl


ROOT = Path(__file__).resolve().parents[1]


class LocalWorkbenchApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = ROOT / ".test_runs" / self.id().replace(".", "_")
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.tmp.mkdir(parents=True)
        config = AgentConfig.load(ROOT)
        object.__setattr__(config, "root_dir", self.tmp)
        object.__setattr__(config, "runs_dir", self.tmp / "runs")
        object.__setattr__(config, "llm_api_key", "")
        self.agent = ResearchChatAgent(config)
        self.client = TestClient(create_app(self.agent))

    def tearDown(self) -> None:
        self.agent.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_factory_health_contract_is_loopback_safe(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["bind_host"], "127.0.0.1")
        self.assertFalse(payload["public_network"])

    def test_create_message_and_sse_event_contracts(self) -> None:
        created_response = self.client.post("/runs", json={})
        self.assertEqual(created_response.status_code, 200)
        created = created_response.json()
        run_id = created["run_id"]
        self.assertEqual(created["status"], "active")

        replied_response = self.client.post(f"/runs/{run_id}/messages", json={"message": "Hello"})
        self.assertEqual(replied_response.status_code, 200)
        replied = replied_response.json()
        self.assertEqual(replied["run_id"], run_id)
        self.assertTrue(replied["assistant_message"])

        response = self.client.get(f"/runs/{run_id}/events")
        self.assertEqual(response.status_code, 200)
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        self.assertTrue(events)
        self.assertTrue(any(item["event"] == "assistant_message" for item in events))

    def test_multipart_upload_preserves_original_filename_and_content(self) -> None:
        run_id = self.client.post("/runs", json={}).json()["run_id"]

        response = self.client.post(
            f"/runs/{run_id}/files",
            files=[("files", ("study notes.txt", b"original upload content", "text/plain"))],
        )

        self.assertEqual(response.status_code, 200, response.text)
        uploaded = response.json()["data"]["files"]
        self.assertEqual(uploaded[0]["filename"], "study notes.txt")
        self.assertEqual(Path(uploaded[0]["stored_path"]).read_bytes(), b"original upload content")

    def test_multipart_upload_returns_current_sequenced_run_snapshot(self) -> None:
        created = self.client.post("/runs", json={}).json()
        run_id = created["run_id"]

        upload = self.client.post(
            f"/runs/{run_id}/files",
            files=[("files", ("evidence.txt", b"upload evidence", "text/plain"))],
        )

        self.assertEqual(upload.status_code, 200, upload.text)
        payload = upload.json()
        self.assertEqual(payload["events"][:len(created["events"])], created["events"])
        self.assertTrue(payload["artifacts"])
        self.assertTrue(any(item["event"] == "tool_observed" for item in payload["events"]))
        sequences = [item["sequence"] for item in payload["events"]]
        self.assertEqual(sequences, list(dict.fromkeys(sequences)))

    def test_registered_artifact_can_be_opened_by_name(self) -> None:
        run_id = self.client.post("/runs", json={}).json()["run_id"]
        session = self.agent.sessions.load(run_id)
        image = self.agent.sessions.directory(run_id) / "chart.png"
        image.write_bytes(b"fake-png-content")
        session.artifact_records["chart_one"] = {
            "type": "Image", "path": str(image), "producer": "scientific-chart",
        }
        self.agent.sessions.save(session)

        response = self.client.get(f"/runs/{run_id}/artifacts/chart_one")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"fake-png-content")

    def test_intervention_endpoint_resumes_the_same_paused_turn(self) -> None:
        run_id = self.client.post("/runs", json={}).json()["run_id"]
        coordinator = self.client.app.state.turn_coordinator
        control = TurnControl(run_id, self.agent.sessions.directory(run_id))
        control.state = "running"
        control.request_pause()
        boundary = []
        worker = threading.Thread(target=lambda: boundary.append(control.safe_boundary()))
        worker.start()
        deadline = time.time() + 1
        while control.state != "paused" and time.time() < deadline:
            time.sleep(0.01)
        coordinator._active[run_id] = control
        coordinator._turns[control.turn_id] = control

        response = self.client.post(
            f"/runs/{run_id}/intervene", json={"message": "保留原图，再生成箱线图"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["run_id"], run_id)
        self.assertEqual(response.json()["turn_id"], control.turn_id)
        self.assertEqual(response.json()["status"], "running")
        worker.join(1)
        self.assertEqual(boundary, ["保留原图，再生成箱线图"])

    def test_quality_outcome_report_is_available_to_the_workbench(self) -> None:
        run_id = self.client.post("/runs", json={}).json()["run_id"]
        reply = self.client.post(f"/runs/{run_id}/messages", json={"message": "Hello"})

        self.assertEqual(reply.status_code, 200)
        self.assertTrue(reply.json()["outcome_report"])
        report = self.client.get("/quality/outcomes")
        self.assertEqual(report.status_code, 200)
        self.assertIn("用户结果验收报告", report.json()["markdown"])

    def test_plan_reject_endpoint_keeps_plan_mode_without_execution(self) -> None:
        run_id = self.client.post("/runs", json={}).json()["run_id"]
        session = self.agent.sessions.load(run_id)
        session.status = "waiting_user"
        session.metadata["plan_mode"] = True
        session.model_messages = [{"role": "assistant", "content": "plan"}]
        session.pending_action = {
            "type": "plan_approval",
            "model_messages": session.model_messages,
            "user_message": "plan this",
            "summary": "Plan 已完成。是否执行？",
        }
        self.agent.sessions.save(session)

        response = self.client.post(f"/runs/{run_id}/reject")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "planning")
        self.assertTrue(payload["plan_mode"])
        self.assertIsNone(payload["pending_action"])
        self.assertIn("仍处于 Plan 模式", payload["assistant_message"])

    def test_workbench_keeps_accept_and_reject_controls(self) -> None:
        source = (ROOT / "workbench" / "src" / "App.js").read_text(encoding="utf-8")
        dock = (ROOT / "workbench" / "src" / "components" / "ApprovalDock.js").read_text(encoding="utf-8")

        self.assertIn("<ApprovalDock pending={pendingApproval} onResolve={resolveApproval}", source)
        self.assertIn("/reject", source)
        self.assertIn("/approve", source)
        self.assertIn("onResolve(false)", dock)
        self.assertIn("onResolve(true)", dock)
        self.assertIn(">允许并继续</button>", dock)
        self.assertIn(">拒绝</button>", dock)

    def test_workbench_uses_resumable_turn_stream_and_ignores_late_runs(self) -> None:
        source = (ROOT / "workbench" / "src" / "App.js").read_text(encoding="utf-8")

        self.assertIn("/turns/stream", source)
        self.assertIn("generationRef.current", source)
        self.assertIn("sequenceRef.current", source)
        self.assertIn("/events?after=", source)
        self.assertIn("turnIdRef.current", source)

    def test_workbench_has_independent_pause_resume_controls(self) -> None:
        source = (ROOT / "workbench" / "src" / "App.js").read_text(encoding="utf-8")

        self.assertIn('control("pause")', source)
        self.assertIn('control("resume")', source)
        self.assertIn("pause_requested", source)
        self.assertIn("rate_limited", source)

    def test_workbench_exposes_home_settings_and_scheduler_features(self) -> None:
        home = (ROOT / "workbench" / "src" / "pages" / "HomePage.js").read_text(encoding="utf-8")
        settings = (ROOT / "workbench" / "src" / "pages" / "SettingsPage.js").read_text(encoding="utf-8")
        tasks = (ROOT / "workbench" / "src" / "pages" / "TaskCenterPage.js").read_text(encoding="utf-8")

        self.assertIn("https://maas.ai-yuanjing.com/", home)
        self.assertIn("/maas-brand.png", home)
        self.assertIn("onPointerMove", home)
        self.assertIn("学术数据源", settings)
        self.assertIn("色彩设计", settings)
        self.assertIn("/settings/privacy", settings)
        self.assertIn("/usage?", settings)
        self.assertIn("/schedules", tasks)
        self.assertIn("仅一次", tasks)
        self.assertIn("每天", tasks)
        self.assertIn("每周", tasks)

    def test_settings_effects_do_not_return_async_loader_promises(self) -> None:
        settings = (ROOT / "workbench" / "src" / "pages" / "SettingsPage.js").read_text(encoding="utf-8")

        self.assertNotIn("useEffect(load, [load])", settings)


if __name__ == "__main__":
    unittest.main()
