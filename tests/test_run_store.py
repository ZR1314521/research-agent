from __future__ import annotations

import json
import shutil
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from research_agent.run_store import RunStore


ROOT = Path(__file__).resolve().parents[1]


class RunStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = ROOT / ".test_runs" / self.id().replace(".", "_")
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.tmp.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_create_and_reopen(self) -> None:
        store = RunStore(self.tmp / "runs")
        created = store.create_run("run-1", {"topic": "EEG"})
        self.assertEqual(store.database_path, self.tmp / "runs" / "run_store.sqlite3")
        self.assertEqual(created.metadata, {"topic": "EEG"})
        self.assertEqual(store._connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        store.close()

        with RunStore(self.tmp / "runs") as reopened:
            recovered = reopened.load_run("run-1")
        self.assertEqual(recovered.run, created)

    def test_events_have_monotonic_sequence_per_run(self) -> None:
        runs_dir = self.tmp / "runs"
        with RunStore(runs_dir) as store:
            store.create_run("run-1")
            events = [
                store.append_event("run-1", "started", {"step": 1}),
                store.append_event("run-1", "observed", {"step": 2}),
                store.append_event("run-1", "finished", {"step": 3}),
            ]
        with RunStore(runs_dir) as reopened:
            events.append(reopened.append_event("run-1", "resumed", {"step": 4}))
            recovered = reopened.load_run("run-1")
        self.assertEqual([event.sequence for event in events], [1, 2, 3, 4])
        self.assertEqual([event.event_type for event in recovered.events], ["started", "observed", "finished", "resumed"])

    def test_event_redaction_removes_supplied_secrets(self) -> None:
        secret = "top-secret"
        runs_dir = self.tmp / "runs"
        with RunStore(runs_dir) as store:
            store.create_run("run-1")
            store.append_event(
                "run-1",
                "model_called",
                {"authorization": f"Bearer {secret}", "nested": [secret], secret: "key value"},
                redactions=[secret],
                snapshot={"authorization": f"Bearer {secret}", "nested": [secret]},
            )
        with closing(sqlite3.connect(runs_dir / "run_store.sqlite3")) as connection:
            event_json = connection.execute("SELECT payload_json FROM events WHERE run_id = ?", ("run-1",)).fetchone()[0]
            snapshot_json = connection.execute("SELECT payload_json FROM snapshots WHERE run_id = ?", ("run-1",)).fetchone()[0]
        self.assertNotIn(secret, event_json)
        self.assertNotIn(secret, snapshot_json)
        self.assertEqual(json.loads(event_json)["authorization"], "Bearer [REDACTED]")

    def test_artifact_replacement_keeps_the_current_value(self) -> None:
        with RunStore(self.tmp / "runs") as store:
            store.create_run("run-1")
            store.replace_artifact("run-1", "report", "first.md", {"version": 1})
            store.replace_artifact("run-1", "report", "final.md", {"version": 2})
            artifacts = store.load_run("run-1").artifacts
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0].path, "final.md")
        self.assertEqual(artifacts[0].metadata, {"version": 2})

    def test_snapshot_recovery_is_current_and_tied_to_event_sequence(self) -> None:
        with RunStore(self.tmp / "runs") as store:
            store.create_run("run-1")
            store.append_event("run-1", "started", {"step": 1}, snapshot={"status": "running"})
            store.append_event("run-1", "finished", {"step": 2}, snapshot={"status": "completed"})
        with RunStore(self.tmp / "runs") as reopened:
            recovered = reopened.load_run("run-1")
        self.assertEqual([event.sequence for event in recovered.events], [1, 2])
        self.assertIsNotNone(recovered.snapshot)
        self.assertEqual(recovered.snapshot.event_sequence, 2)
        self.assertEqual(recovered.snapshot.payload, {"status": "completed"})

    def test_snapshot_failure_rolls_back_its_event(self) -> None:
        with RunStore(self.tmp / "runs") as store:
            store.create_run("run-1")
            with patch.object(store, "_replace_snapshot_row", side_effect=sqlite3.DatabaseError("forced failure")):
                with self.assertRaisesRegex(sqlite3.DatabaseError, "forced failure"):
                    store.append_event("run-1", "finished", {"step": 1}, snapshot={"status": "completed"})
            recovered = store.load_run("run-1")
        self.assertEqual(recovered.events, ())
        self.assertIsNone(recovered.snapshot)


if __name__ == "__main__":
    unittest.main()
