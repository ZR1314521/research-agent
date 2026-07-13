from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from research_agent.run_store import RunStore
from research_agent.version import RUNTIME_VERSION


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


@dataclass
class ChatSession:
    session_id: str
    created_at: str
    updated_at: str
    status: str = "active"
    messages: list[dict[str, Any]] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    pending_action: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    goal: str = ""
    plan: list[dict[str, Any]] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    artifact_dependencies: dict[str, list[str]] = field(default_factory=dict)
    invalidated_artifacts: list[str] = field(default_factory=list)
    artifact_records: dict[str, dict[str, str]] = field(default_factory=dict)
    task_ledger: list[dict[str, Any]] = field(default_factory=list)
    model_messages: list[dict[str, Any]] = field(default_factory=list)
    runtime_version: str = RUNTIME_VERSION

    @classmethod
    def create(cls) -> "ChatSession":
        now = _now()
        return cls(
            session_id=time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8],
            created_at=now,
            updated_at=now,
        )

    def add_message(self, role: str, content: str, **extra: Any) -> None:
        item = {"timestamp": _now(), "role": role, "content": content}
        item.update(extra)
        self.messages.append(item)
        self.updated_at = _now()


class SessionStore:
    def __init__(self, runs_dir: Path):
        self.runs_dir = Path(runs_dir)
        self.root = self.runs_dir / "sessions"
        self.root.mkdir(parents=True, exist_ok=True)
        self.run_store = RunStore(self.runs_dir)
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self.run_store.close()
        self._closed = True

    def __enter__(self) -> "SessionStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def directory(self, session_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9._-]+", session_id):
            raise ValueError("Invalid session id")
        return self.root / session_id

    def create(self) -> ChatSession:
        session = ChatSession.create()
        self.save(session)
        return session

    def load(self, session_id: str) -> ChatSession:
        path = self.directory(session_id) / "session.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not payload.get("runtime_version"):
            payload["runtime_version"] = "legacy"
            payload.setdefault("metadata", {})["runtime_notice"] = "This session predates the current runtime; restart the terminal before trusting new tool contracts."
        session = ChatSession(**payload)
        self._mirror_snapshot(session, self._serialize(session))
        return session

    def latest(self) -> ChatSession | None:
        files = sorted(self.root.glob("*/session.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        return self.load(files[0].parent.name) if files else None

    def save(self, session: ChatSession) -> Path:
        path, snapshot = self._save_legacy(session)
        self._mirror_snapshot(session, snapshot)
        return path

    def _save_legacy(self, session: ChatSession) -> tuple[Path, dict[str, Any]]:
        session.updated_at = _now()
        directory = self.directory(session.session_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "session.json"
        temp = directory / "session.json.tmp"
        payload = json.dumps(asdict(session), ensure_ascii=False, indent=2)
        temp.write_text(payload, encoding="utf-8")
        first_replace_error: PermissionError | None = None
        # ponytail: three short retries cover transient Windows replacement locks.
        for attempt in range(3):
            try:
                temp.replace(path)
                break
            except PermissionError as error:
                first_replace_error = first_replace_error or error
                if attempt == 2:
                    raise first_replace_error
                time.sleep(0.01 * (attempt + 1))
        (directory / "workflow_trace.json").write_text(
            json.dumps(session.events, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return path, json.loads(payload)

    def reset_context(self, session: ChatSession) -> ChatSession:
        session.messages.clear(); session.events.clear(); session.plan.clear(); session.observations.clear(); session.model_messages.clear()
        session.goal = ""; session.pending_action = None; session.task_ledger.clear()
        session.artifacts.clear(); session.artifact_records.clear(); session.artifact_dependencies.clear(); session.invalidated_artifacts.clear()
        session.metadata = {"reset_at": _now()}; session.status = "active"
        self.save(session)
        return session

    def event(self, session: ChatSession, event: str, skill: str = "", summary: str = "", **extra: Any) -> None:
        item = {"timestamp": _now(), "event": event, "skill": skill, "summary": summary}
        item.update(extra)
        session.events.append(item)
        self._append_legacy_event(session.session_id, item)
        _path, snapshot = self._save_legacy(session)
        self._mirror_event(session, item, snapshot)

    def _append_legacy_event(self, session_id: str, item: dict[str, Any]) -> None:
        directory = self.directory(session_id)
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "execution_log.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    @staticmethod
    def _serialize(session: ChatSession) -> dict[str, Any]:
        return json.loads(json.dumps(asdict(session), ensure_ascii=False))

    def _ensure_run(self, session: ChatSession) -> None:
        try:
            self.run_store.load_run(session.session_id)
        except KeyError:
            self.run_store.create_run(session.session_id)

    def _mirror_snapshot(self, session: ChatSession, snapshot: dict[str, Any]) -> None:
        try:
            self._ensure_run(session)
            self.run_store.replace_snapshot(session.session_id, snapshot)
            self._mirror_artifacts(session)
        except Exception as error:
            self._report_mirror_failure(session, error)

    def _mirror_event(self, session: ChatSession, item: dict[str, Any], snapshot: dict[str, Any]) -> None:
        try:
            self._ensure_run(session)
            self.run_store.append_event(session.session_id, item["event"], item, snapshot=snapshot)
            self._mirror_artifacts(session)
        except Exception as error:
            self._report_mirror_failure(session, error)

    def _mirror_artifacts(self, session: ChatSession) -> None:
        for name, path in session.artifacts.items():
            record = dict(session.artifact_records.get(name, {}))
            self.run_store.replace_artifact(session.session_id, name, record.get("path", path), record)
        for name, record in session.artifact_records.items():
            if name not in session.artifacts and record.get("path"):
                self.run_store.replace_artifact(session.session_id, name, record["path"], record)

    def _report_mirror_failure(self, session: ChatSession, error: Exception) -> None:
        message = f"Run-store mirror failed: {type(error).__name__}: {error}"
        session.metadata["run_store_mirror_error"] = message
        item = {"timestamp": _now(), "event": "run_store_mirror_failed", "skill": "", "summary": message}
        session.events.append(item)
        self._append_legacy_event(session.session_id, item)
        self._save_legacy(session)
