"""SQLite persistence for new runtime runs; legacy JSON sessions remain separate."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import TypeAlias, cast


JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_object(value: Mapping[str, JsonValue]) -> tuple[str, JsonObject]:
    """Validate a JSON object and return an independent normalized copy."""
    text = json.dumps(dict(value), ensure_ascii=False, sort_keys=True, allow_nan=False)
    loaded = json.loads(text)
    if not isinstance(loaded, dict):  # defensive: Mapping input should always serialize to an object
        raise ValueError("Expected a JSON object")
    return text, cast(JsonObject, loaded)


def _redact(value: JsonValue, secrets: tuple[str, ...]) -> JsonValue:
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, list):
        return [_redact(item, secrets) for item in value]
    if isinstance(value, dict):
        return {
            cast(str, _redact(key, secrets)): _redact(item, secrets)
            for key, item in value.items()
        }
    return value


@dataclass(frozen=True)
class StoredRun:
    run_id: str
    created_at: str
    metadata: JsonObject


@dataclass(frozen=True)
class StoredEvent:
    run_id: str
    sequence: int
    event_type: str
    payload: JsonObject
    created_at: str


@dataclass(frozen=True)
class StoredArtifact:
    run_id: str
    name: str
    path: str
    metadata: JsonObject
    updated_at: str


@dataclass(frozen=True)
class StoredSnapshot:
    run_id: str
    event_sequence: int
    payload: JsonObject
    updated_at: str


@dataclass(frozen=True)
class RecoveredRun:
    run: StoredRun
    events: tuple[StoredEvent, ...]
    artifacts: tuple[StoredArtifact, ...]
    snapshot: StoredSnapshot | None


class RunStore:
    """Append-only SQLite store for runs created after the persistence migration."""

    def __init__(self, runs_dir: Path, database_name: str = "run_store.sqlite3"):
        self.runs_dir = Path(runs_dir)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.database_path = self.runs_dir / database_name
        self._write_lock = RLock()
        self._connection = sqlite3.connect(self.database_path, isolation_level=None, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        try:
            self._connection.execute("PRAGMA journal_mode = WAL")
        except sqlite3.DatabaseError:
            pass  # Some SQLite filesystems do not support WAL; transactions still protect writes.
        self._create_schema()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "RunStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def create_run(self, run_id: str | None = None, metadata: Mapping[str, JsonValue] | None = None) -> StoredRun:
        run_id = run_id or uuid.uuid4().hex
        if not run_id:
            raise ValueError("run_id must not be empty")
        metadata_text, normalized_metadata = _json_object(metadata or {})
        created_at = _now()
        with self._write_transaction():
            self._connection.execute(
                "INSERT INTO runs (run_id, created_at, metadata_json) VALUES (?, ?, ?)",
                (run_id, created_at, metadata_text),
            )
        return StoredRun(run_id, created_at, normalized_metadata)

    def append_event(
        self,
        run_id: str,
        event_type: str,
        payload: Mapping[str, JsonValue],
        *,
        redactions: Iterable[str] = (),
        snapshot: Mapping[str, JsonValue] | None = None,
    ) -> StoredEvent:
        if not event_type:
            raise ValueError("event_type must not be empty")
        secrets = tuple(secret for secret in redactions if secret)
        payload_text, normalized_payload = _json_object(_redact(dict(payload), secrets))
        snapshot_value = _json_object(_redact(dict(snapshot), secrets)) if snapshot is not None else None
        created_at = _now()
        with self._write_transaction():
            self._require_run(run_id)
            sequence = cast(
                int,
                self._connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 FROM events WHERE run_id = ?", (run_id,)
                ).fetchone()[0],
            )
            self._connection.execute(
                "INSERT INTO events (run_id, sequence, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (run_id, sequence, event_type, payload_text, created_at),
            )
            if snapshot_value is not None:
                snapshot_text, _ = snapshot_value
                self._replace_snapshot_row(run_id, sequence, snapshot_text, created_at)
        return StoredEvent(run_id, sequence, event_type, normalized_payload, created_at)

    def replace_artifact(
        self,
        run_id: str,
        name: str,
        path: str,
        metadata: Mapping[str, JsonValue] | None = None,
    ) -> StoredArtifact:
        if not name:
            raise ValueError("artifact name must not be empty")
        metadata_text, normalized_metadata = _json_object(metadata or {})
        updated_at = _now()
        with self._write_transaction():
            self._require_run(run_id)
            self._connection.execute(
                """
                INSERT INTO artifacts (run_id, name, path, metadata_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id, name) DO UPDATE SET
                    path = excluded.path,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (run_id, name, path, metadata_text, updated_at),
            )
        return StoredArtifact(run_id, name, path, normalized_metadata, updated_at)

    def replace_snapshot(
        self,
        run_id: str,
        payload: Mapping[str, JsonValue],
        *,
        redactions: Iterable[str] = (),
    ) -> StoredSnapshot:
        secrets = tuple(secret for secret in redactions if secret)
        payload_text, normalized_payload = _json_object(_redact(dict(payload), secrets))
        updated_at = _now()
        with self._write_transaction():
            self._require_run(run_id)
            event_sequence = cast(
                int,
                self._connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) FROM events WHERE run_id = ?", (run_id,)
                ).fetchone()[0],
            )
            self._replace_snapshot_row(run_id, event_sequence, payload_text, updated_at)
        return StoredSnapshot(run_id, event_sequence, normalized_payload, updated_at)

    def load_run(self, run_id: str) -> RecoveredRun:
        row = self._connection.execute(
            "SELECT run_id, created_at, metadata_json FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            raise KeyError(run_id)
        run = StoredRun(row["run_id"], row["created_at"], self._load_object(row["metadata_json"]))
        events = tuple(
            StoredEvent(row["run_id"], row["sequence"], row["event_type"], self._load_object(row["payload_json"]), row["created_at"])
            for row in self._connection.execute(
                "SELECT run_id, sequence, event_type, payload_json, created_at FROM events WHERE run_id = ? ORDER BY sequence",
                (run_id,),
            )
        )
        artifacts = tuple(
            StoredArtifact(row["run_id"], row["name"], row["path"], self._load_object(row["metadata_json"]), row["updated_at"])
            for row in self._connection.execute(
                "SELECT run_id, name, path, metadata_json, updated_at FROM artifacts WHERE run_id = ? ORDER BY name",
                (run_id,),
            )
        )
        row = self._connection.execute(
            "SELECT run_id, event_sequence, payload_json, updated_at FROM snapshots WHERE run_id = ?", (run_id,)
        ).fetchone()
        snapshot = (
            None
            if row is None
            else StoredSnapshot(row["run_id"], row["event_sequence"], self._load_object(row["payload_json"]), row["updated_at"])
        )
        return RecoveredRun(run, events, artifacts, snapshot)

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                run_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (run_id, sequence),
                FOREIGN KEY (run_id) REFERENCES runs(run_id)
            );
            CREATE TABLE IF NOT EXISTS artifacts (
                run_id TEXT NOT NULL,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (run_id, name),
                FOREIGN KEY (run_id) REFERENCES runs(run_id)
            );
            CREATE TABLE IF NOT EXISTS snapshots (
                run_id TEXT PRIMARY KEY,
                event_sequence INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES runs(run_id)
            );
            """
        )

    @contextmanager
    def _write_transaction(self) -> Iterator[None]:
        with self._write_lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self._connection.rollback()
                raise
            else:
                self._connection.commit()

    def _require_run(self, run_id: str) -> None:
        if self._connection.execute("SELECT 1 FROM runs WHERE run_id = ?", (run_id,)).fetchone() is None:
            raise KeyError(run_id)

    def _replace_snapshot_row(self, run_id: str, event_sequence: int, payload_text: str, updated_at: str) -> None:
        self._connection.execute(
            """
            INSERT INTO snapshots (run_id, event_sequence, payload_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                event_sequence = excluded.event_sequence,
                payload_json = excluded.payload_json,
                updated_at = excluded.updated_at
            """,
            (run_id, event_sequence, payload_text, updated_at),
        )

    @staticmethod
    def _load_object(text: str) -> JsonObject:
        value = json.loads(text)
        if not isinstance(value, dict):
            raise ValueError("Stored payload is not a JSON object")
        return cast(JsonObject, value)
