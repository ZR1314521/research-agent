from __future__ import annotations

import json
import shutil
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from research_agent.run_store import RunStore
from research_agent.session import SessionStore


ROOT = Path(__file__).resolve().parents[1]


class RunStoreIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = ROOT / ".test_runs" / self.id().replace(".", "_")
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.tmp.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_creating_and_saving_session_creates_readable_run_snapshot(self) -> None:
        sessions = SessionStore(self.tmp / "runs")
        session = sessions.create()
        session.metadata["topic"] = "EEG"
        sessions.save(session)

        with RunStore(self.tmp / "runs") as reopened:
            recovered = reopened.load_run(session.session_id)

        self.assertIsNotNone(recovered.snapshot)
        self.assertEqual(recovered.snapshot.payload["session_id"], session.session_id)
        self.assertEqual(recovered.snapshot.payload["metadata"]["topic"], "EEG")
        sessions.close()

    def test_user_and_tool_events_keep_durable_jsonl_order_in_sqlite(self) -> None:
        sessions = SessionStore(self.tmp / "runs")
        session = sessions.create()
        sessions.event(session, "user", summary="find EEG papers")
        sessions.event(session, "tool_started", "academic-search", "search started")

        execution_log = sessions.directory(session.session_id) / "execution_log.jsonl"
        legacy_events = [json.loads(line) for line in execution_log.read_text(encoding="utf-8").splitlines()]
        with RunStore(self.tmp / "runs") as reopened:
            sqlite_events = reopened.load_run(session.session_id).events

        self.assertEqual([item["event"] for item in legacy_events], ["user", "tool_started"])
        self.assertEqual([item.event_type for item in sqlite_events], ["user", "tool_started"])
        sessions.close()

    def test_context_manager_closes_the_owned_run_store(self) -> None:
        with SessionStore(self.tmp / "runs") as sessions:
            session = sessions.create()

        with self.assertRaises(sqlite3.ProgrammingError):
            sessions.run_store.load_run(session.session_id)

    def test_failed_close_remains_retryable(self) -> None:
        sessions = SessionStore(self.tmp / "runs")
        with patch.object(sessions.run_store, "close", side_effect=[RuntimeError("close failed"), None]) as close:
            with self.assertRaisesRegex(RuntimeError, "close failed"):
                sessions.close()
            sessions.close()

        self.assertEqual(close.call_count, 2)

    def test_artifact_records_are_available_after_reopening_run_store(self) -> None:
        sessions = SessionStore(self.tmp / "runs")
        session = sessions.create()
        session.artifacts["report"] = "report.md"
        session.artifact_records["report"] = {
            "path": "report.md",
            "type": "Report",
            "producer": "test-tool",
        }
        sessions.save(session)
        sessions.close()

        with RunStore(self.tmp / "runs") as reopened:
            artifacts = reopened.load_run(session.session_id).artifacts

        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0].name, "report")
        self.assertEqual(artifacts[0].path, "report.md")
        self.assertEqual(artifacts[0].metadata["type"], "Report")

    def test_loading_legacy_session_ensures_its_sqlite_run(self) -> None:
        sessions = SessionStore(self.tmp / "runs")
        session = sessions.create()
        sessions.close()
        (self.tmp / "runs" / "run_store.sqlite3").unlink()

        restored_sessions = SessionStore(self.tmp / "runs")
        restored = restored_sessions.load(session.session_id)
        with RunStore(self.tmp / "runs") as reopened:
            recovered = reopened.load_run(session.session_id)

        self.assertEqual(recovered.run.run_id, restored.session_id)
        self.assertEqual(recovered.snapshot.payload["session_id"], restored.session_id)
        restored_sessions.close()

    def test_mirror_failure_preserves_legacy_session_and_is_not_mirrored_recursively(self) -> None:
        sessions = SessionStore(self.tmp / "runs")
        session = sessions.create()

        with patch.object(sessions.run_store, "append_event", side_effect=RuntimeError("forced SQLite failure")) as append:
            sessions.event(session, "tool_started", "academic-search", "search started")

        payload = json.loads((sessions.directory(session.session_id) / "session.json").read_text(encoding="utf-8"))
        self.assertEqual(append.call_count, 1)
        self.assertEqual(payload["events"][-2]["event"], "tool_started")
        self.assertEqual(payload["events"][-1]["event"], "run_store_mirror_failed")
        self.assertIn("forced SQLite failure", payload["events"][-1]["summary"])
        sessions.close()


if __name__ == "__main__":
    unittest.main()
