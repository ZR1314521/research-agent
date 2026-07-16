from __future__ import annotations

import json
import os
import shutil
import sqlite3
import time
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from research_agent.app import create_app
from research_agent.chat import ResearchChatAgent
from research_agent.config import AgentConfig
from research_agent.platform_store import PlatformStore
from research_agent.usage import UsageService


ROOT = Path(__file__).resolve().parents[1]
SHANGHAI = timezone(timedelta(hours=8), name="Asia/Shanghai")


class PlatformFeatureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = ROOT / ".test_runs" / self.id().replace(".", "_")
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.tmp.mkdir(parents=True)
        self.store = PlatformStore(self.tmp / "runs")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_store_seeds_real_academic_sources_and_manages_free_source(self) -> None:
        sources = self.store.list_data_sources()
        self.assertEqual(
            {item["connector"] for item in sources if item["built_in"]},
            {"openalex", "semantic_scholar", "pubmed", "arxiv"},
        )

        created = self.store.create_data_source({
            "name": "EEG Lab",
            "kind": "free",
            "base_url": "https://example.org/research",
        })

        self.assertFalse(created["built_in"])
        self.assertEqual(created["kind"], "free")
        updated = self.store.update_data_source(created["id"], {"enabled": False})
        self.assertFalse(updated["enabled"])
        self.assertTrue(self.store.delete_data_source(created["id"]))

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI test")
    def test_paid_source_secret_is_encrypted_and_never_returned(self) -> None:
        created = self.store.create_data_source({
            "name": "Paid Index",
            "kind": "paid",
            "base_url": "https://example.org/login",
            "username": "researcher",
            "password": "local-secret-value",
        })

        self.assertTrue(created["has_credentials"])
        self.assertNotIn("password", created)
        with closing(sqlite3.connect(self.store.path)) as db:
            secret = db.execute(
                "SELECT secret_blob FROM data_sources WHERE id=?", (created["id"],)
            ).fetchone()[0]
        self.assertNotEqual(secret, "local-secret-value")
        self.assertEqual(self.store.protector.unprotect(secret), "local-secret-value")

    def test_usage_report_aggregates_real_provider_ledger_shape(self) -> None:
        session = self.tmp / "runs" / "sessions" / "run-1"
        session.mkdir(parents=True)
        record = {
            "call_id": "call-1",
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "started_at": time.time(),
            "status": "completed",
            "duration_ms": 1250,
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 25,
                "total_tokens": 125,
                "prompt_cache_hit_tokens": 80,
            },
        }
        (session / "provider_calls.jsonl").write_text(
            json.dumps(record) + "\nnot-json\n", encoding="utf-8"
        )

        report = UsageService(self.tmp / "runs", self.store).report()

        self.assertEqual(report["summary"]["requests"], 1)
        self.assertEqual(report["summary"]["total_tokens"], 125)
        self.assertEqual(report["summary"]["cached_tokens"], 80)
        self.assertEqual(report["summary"]["damaged_records"], 1)
        self.assertIsNone(report["summary"]["cost"])

    def test_schedule_store_supports_pause_resume_and_execution_history(self) -> None:
        run_at = (datetime.now(SHANGHAI) + timedelta(hours=1)).isoformat()
        schedule = self.store.create_schedule({
            "name": "每日文献简报",
            "prompt": "检索今天新增的脑电研究并生成摘要",
            "schedule_type": "daily",
            "timezone": "Asia/Shanghai",
            "next_run_at": run_at,
        })

        paused = self.store.update_schedule(schedule["id"], {"enabled": False})
        self.assertEqual(paused["status"], "paused")
        resumed = self.store.update_schedule(schedule["id"], {"enabled": True})
        self.assertEqual(resumed["status"], "scheduled")
        execution = self.store.begin_manual_schedule_run(schedule["id"])
        self.store.update_schedule_execution(
            execution["execution_id"], schedule["id"], "completed", run_id="run-2", finished=True
        )
        self.assertEqual(self.store.schedule_runs(schedule["id"])[0]["run_id"], "run-2")


class PlatformApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = ROOT / ".test_runs" / self.id().replace(".", "_")
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.tmp.mkdir(parents=True)
        config = AgentConfig.load(ROOT)
        object.__setattr__(config, "root_dir", self.tmp)
        object.__setattr__(config, "runs_dir", self.tmp / "runs")
        object.__setattr__(config, "llm_api_key", "")
        self.agent = ResearchChatAgent(config)
        self.app = create_app(self.agent)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.app.state.schedule_service.stop()
        self.agent.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_settings_sources_usage_and_schedules_are_exposed(self) -> None:
        self.assertEqual(len(self.client.get("/data-sources").json()), 4)
        privacy = self.client.post("/settings/privacy", json={
            "external_network_access": False,
            "approval_required": True,
            "log_retention_days": 45,
        })
        self.assertEqual(privacy.status_code, 200)
        self.assertFalse(privacy.json()["external_network_access"])

        account = self.client.post("/settings/account", json={
            "display_name": "林研",
            "institution": "本地实验室",
        })
        self.assertEqual(account.json()["display_name"], "林研")
        self.assertIn("summary", self.client.get("/usage").json())

        run_at = (datetime.now(SHANGHAI) + timedelta(hours=1)).isoformat()
        created = self.client.post("/schedules", json={
            "name": "一次任务",
            "prompt": "整理当前研究方向",
            "schedule_type": "once",
            "timezone": "Asia/Shanghai",
            "next_run_at": run_at,
        })
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(len(self.client.get("/schedules").json()), 1)
        schedule_id = created.json()["id"]
        launched = self.client.post(f"/schedules/{schedule_id}/run")
        self.assertEqual(launched.status_code, 200, launched.text)
        executions = []
        for _ in range(40):
            executions = self.client.get(f"/schedule-runs?schedule_id={schedule_id}").json()
            if executions and executions[0]["finished_at"]:
                break
            time.sleep(0.05)
        self.assertTrue(executions)
        self.assertTrue(executions[0]["run_id"])
        self.assertIn(executions[0]["status"], {"completed", "failed"})


if __name__ == "__main__":
    unittest.main()
