from __future__ import annotations

import base64
import ctypes
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


BUILT_IN_SOURCES = (
    {
        "id": "builtin-openalex",
        "name": "OpenAlex",
        "base_url": "https://api.openalex.org/",
        "check_url": "https://api.openalex.org/works?per-page=1",
        "connector": "openalex",
    },
    {
        "id": "builtin-semantic-scholar",
        "name": "Semantic Scholar",
        "base_url": "https://api.semanticscholar.org/",
        "check_url": "https://api.semanticscholar.org/graph/v1/paper/search?query=science&limit=1",
        "connector": "semantic_scholar",
    },
    {
        "id": "builtin-pubmed",
        "name": "PubMed",
        "base_url": "https://eutils.ncbi.nlm.nih.gov/",
        "check_url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/einfo.fcgi?db=pubmed&retmode=json",
        "connector": "pubmed",
    },
    {
        "id": "builtin-arxiv",
        "name": "arXiv",
        "base_url": "https://export.arxiv.org/",
        "check_url": "https://export.arxiv.org/api/query?search_query=all:science&start=0&max_results=1",
        "connector": "arxiv",
    },
)


DEFAULT_PRIVACY = {
    "external_network_access": True,
    "approval_required": True,
    "log_retention_days": 30,
    "mask_credentials": True,
}

DEFAULT_ACCOUNT = {
    "display_name": "本地科研用户",
    "institution": "",
    "email": "",
    "title": "",
    "bio": "",
    "avatar": "",
}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _valid_url(value: str) -> str:
    value = str(value or "").strip()
    parsed = urlparse(value)
    if len(value) > 2048 or parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("请输入有效的 http 或 https 地址")
    return value


def _timezone(value: str):
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as error:
        if value == "Asia/Shanghai":
            return timezone(timedelta(hours=8), name="Asia/Shanghai")
        if value == "UTC":
            return timezone.utc
        raise ValueError("当前系统没有该时区数据") from error


class CredentialProtectionError(RuntimeError):
    pass


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_byte))]


class CredentialProtector:
    """Protect paid-source credentials with the current Windows user profile."""

    flags = 0x01  # CRYPTPROTECT_UI_FORBIDDEN

    def _require_windows(self) -> None:
        if os.name != "nt" or not hasattr(ctypes, "windll"):
            raise CredentialProtectionError("付费数据源凭据加密仅支持 Windows 本机")

    @staticmethod
    def _input_blob(data: bytes) -> tuple[_DataBlob, Any]:
        buffer = ctypes.create_string_buffer(data)
        blob = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
        return blob, buffer

    def protect(self, value: str) -> str:
        self._require_windows()
        raw = value.encode("utf-8")
        source, source_buffer = self._input_blob(raw)
        output = _DataBlob()
        ok = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(source),
            "Research Agent data source",
            None,
            None,
            None,
            self.flags,
            ctypes.byref(output),
        )
        _ = source_buffer
        if not ok:
            raise CredentialProtectionError("Windows 无法加密数据源凭据")
        try:
            protected = ctypes.string_at(output.pbData, output.cbData)
            return base64.b64encode(protected).decode("ascii")
        finally:
            ctypes.windll.kernel32.LocalFree(output.pbData)

    def unprotect(self, value: str) -> str:
        self._require_windows()
        try:
            raw = base64.b64decode(value.encode("ascii"), validate=True)
        except Exception as error:
            raise CredentialProtectionError("加密凭据格式无效") from error
        source, source_buffer = self._input_blob(raw)
        output = _DataBlob()
        description = ctypes.c_void_p()
        ok = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(source),
            ctypes.byref(description),
            None,
            None,
            None,
            self.flags,
            ctypes.byref(output),
        )
        _ = source_buffer
        if not ok:
            raise CredentialProtectionError("当前 Windows 用户无法解密数据源凭据")
        try:
            return ctypes.string_at(output.pbData, output.cbData).decode("utf-8")
        finally:
            ctypes.windll.kernel32.LocalFree(output.pbData)
            if description.value:
                ctypes.windll.kernel32.LocalFree(description)


class PlatformStore:
    def __init__(self, runs_dir: Path):
        self.runs_dir = Path(runs_dir)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.runs_dir / "platform.sqlite3"
        self._lock = threading.RLock()
        self.protector = CredentialProtector()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 15000")
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS data_sources (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    base_url TEXT NOT NULL,
                    check_url TEXT NOT NULL DEFAULT '',
                    username TEXT NOT NULL DEFAULT '',
                    secret_blob TEXT NOT NULL DEFAULT '',
                    connector TEXT NOT NULL DEFAULT '',
                    built_in INTEGER NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'not_checked',
                    status_message TEXT NOT NULL DEFAULT '',
                    last_checked_at TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS schedules (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    schedule_type TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    next_run_at TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'scheduled',
                    last_run_at TEXT NOT NULL DEFAULT '',
                    last_run_id TEXT NOT NULL DEFAULT '',
                    last_error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS schedule_runs (
                    id TEXT PRIMARY KEY,
                    schedule_id TEXT NOT NULL,
                    run_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(schedule_id) REFERENCES schedules(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_schedules_due ON schedules(enabled, next_run_at);
                CREATE INDEX IF NOT EXISTS idx_schedule_runs_schedule ON schedule_runs(schedule_id, started_at DESC);
                """
            )
            for source in BUILT_IN_SOURCES:
                now = _now()
                db.execute(
                    """
                    INSERT INTO data_sources (
                        id, name, kind, base_url, check_url, connector, built_in,
                        enabled, status, created_at, updated_at
                    ) VALUES (?, ?, 'free', ?, ?, ?, 1, 1, 'available', ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name=excluded.name, base_url=excluded.base_url,
                        check_url=excluded.check_url, connector=excluded.connector,
                        built_in=1, updated_at=excluded.updated_at
                    """,
                    (
                        source["id"], source["name"], source["base_url"],
                        source["check_url"], source["connector"], now, now,
                    ),
                )
            for key, value in (("privacy", DEFAULT_PRIVACY), ("account", DEFAULT_ACCOUNT)):
                db.execute(
                    "INSERT OR IGNORE INTO app_settings(key, value_json, updated_at) VALUES (?, ?, ?)",
                    (key, json.dumps(value, ensure_ascii=False), _now()),
                )

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT value_json FROM app_settings WHERE key=?", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value_json"])
        except json.JSONDecodeError:
            return default

    def set_setting(self, key: str, value: Any) -> Any:
        encoded = json.dumps(value, ensure_ascii=False)
        with self._lock, self._connect() as db:
            db.execute(
                """
                INSERT INTO app_settings(key, value_json, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at
                """,
                (key, encoded, _now()),
            )
        return value

    def privacy(self) -> dict[str, Any]:
        return {**DEFAULT_PRIVACY, **dict(self.get_setting("privacy", {}) or {})}

    def save_privacy(self, value: dict[str, Any]) -> dict[str, Any]:
        current = self.privacy()
        for key in DEFAULT_PRIVACY:
            if key in value:
                current[key] = value[key]
        current["external_network_access"] = bool(current["external_network_access"])
        current["approval_required"] = bool(current["approval_required"])
        current["mask_credentials"] = True
        current["log_retention_days"] = max(1, min(3650, int(current["log_retention_days"])))
        return self.set_setting("privacy", current)

    def account(self) -> dict[str, Any]:
        return {**DEFAULT_ACCOUNT, **dict(self.get_setting("account", {}) or {})}

    def save_account(self, value: dict[str, Any]) -> dict[str, Any]:
        current = self.account()
        for key in DEFAULT_ACCOUNT:
            if key in value:
                current[key] = str(value[key] or "").strip()[:1000]
        return self.set_setting("account", current)

    @staticmethod
    def _source_payload(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "kind": row["kind"],
            "base_url": row["base_url"],
            "username": row["username"],
            "connector": row["connector"],
            "built_in": bool(row["built_in"]),
            "enabled": bool(row["enabled"]),
            "status": row["status"],
            "status_message": row["status_message"],
            "last_checked_at": row["last_checked_at"],
            "has_credentials": bool(row["secret_blob"]),
            "masked_secret": "••••••••" if row["secret_blob"] else "",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_data_sources(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT * FROM data_sources ORDER BY built_in DESC, name COLLATE NOCASE"
            ).fetchall()
        return [self._source_payload(row) for row in rows]

    def get_data_source(self, source_id: str) -> dict[str, Any]:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM data_sources WHERE id=?", (source_id,)).fetchone()
        if not row:
            raise KeyError(source_id)
        return self._source_payload(row)

    def create_data_source(self, value: dict[str, Any]) -> dict[str, Any]:
        kind = str(value.get("kind") or "free").strip().lower()
        if kind not in {"free", "paid"}:
            raise ValueError("数据源类型只能是免费或付费")
        name = str(value.get("name") or "").strip()[:120]
        if not name:
            raise ValueError("请填写数据源名称")
        base_url = _valid_url(str(value.get("base_url") or ""))
        username = str(value.get("username") or "").strip()[:300]
        password = str(value.get("password") or "")
        if kind == "paid" and (not username or not password):
            raise ValueError("付费数据源需要填写账号和密码")
        secret = self.protector.protect(password) if password else ""
        source_id = "source-" + uuid.uuid4().hex
        now = _now()
        with self._lock, self._connect() as db:
            db.execute(
                """
                INSERT INTO data_sources (
                    id, name, kind, base_url, check_url, username, secret_blob,
                    connector, built_in, enabled, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, '', 0, 1, 'not_checked', ?, ?)
                """,
                (source_id, name, kind, base_url, base_url, username, secret, now, now),
            )
        return self.get_data_source(source_id)

    def update_data_source(self, source_id: str, value: dict[str, Any]) -> dict[str, Any]:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM data_sources WHERE id=?", (source_id,)).fetchone()
            if not row:
                raise KeyError(source_id)
            name = str(value.get("name", row["name"]) or "").strip()[:120]
            base_url = _valid_url(str(value.get("base_url", row["base_url"]) or ""))
            username = str(value.get("username", row["username"]) or "").strip()[:300]
            enabled = 1 if bool(value.get("enabled", bool(row["enabled"]))) else 0
            secret = row["secret_blob"]
            if value.get("password"):
                if row["built_in"]:
                    raise ValueError("内置数据源凭据请在快速设置或环境配置中管理")
                secret = self.protector.protect(str(value["password"]))
            if row["built_in"]:
                name, base_url, username = row["name"], row["base_url"], row["username"]
            db.execute(
                """
                UPDATE data_sources SET name=?, base_url=?, check_url=?, username=?,
                    secret_blob=?, enabled=?, updated_at=? WHERE id=?
                """,
                (name, base_url, row["check_url"] if row["built_in"] else base_url,
                 username, secret, enabled, _now(), source_id),
            )
        return self.get_data_source(source_id)

    def delete_data_source(self, source_id: str) -> bool:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT built_in FROM data_sources WHERE id=?", (source_id,)).fetchone()
            if not row:
                return False
            if row["built_in"]:
                raise ValueError("内置数据源不能删除，可以将其停用")
            db.execute("DELETE FROM data_sources WHERE id=?", (source_id,))
        return True

    def source_check_url(self, source_id: str) -> str:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT check_url FROM data_sources WHERE id=?", (source_id,)).fetchone()
        if not row:
            raise KeyError(source_id)
        return row["check_url"]

    def record_source_check(self, source_id: str, ok: bool, message: str) -> dict[str, Any]:
        with self._lock, self._connect() as db:
            cursor = db.execute(
                """
                UPDATE data_sources SET status=?, status_message=?, last_checked_at=?, updated_at=? WHERE id=?
                """,
                ("available" if ok else "unavailable", str(message)[:500], _now(), _now(), source_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(source_id)
        return self.get_data_source(source_id)

    def enabled_source_context(self) -> list[dict[str, str]]:
        with self._lock, self._connect() as db:
            rows = db.execute(
                "SELECT name, base_url, kind, connector FROM data_sources WHERE enabled=1 ORDER BY built_in DESC, name"
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _schedule_payload(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"], "name": row["name"], "prompt": row["prompt"],
            "schedule_type": row["schedule_type"], "timezone": row["timezone"],
            "next_run_at": row["next_run_at"] or "", "enabled": bool(row["enabled"]),
            "status": row["status"], "last_run_at": row["last_run_at"],
            "last_run_id": row["last_run_id"], "last_error": row["last_error"],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
        }

    @staticmethod
    def _normalize_run_at(value: str, timezone_name: str) -> str:
        try:
            zone = _timezone(timezone_name)
        except Exception as error:
            raise ValueError("时区无效") from error
        try:
            when = datetime.fromisoformat(str(value or ""))
        except ValueError as error:
            raise ValueError("执行时间格式无效") from error
        if when.tzinfo is None:
            when = when.replace(tzinfo=zone)
        return when.astimezone(zone).isoformat(timespec="seconds")

    def list_schedules(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as db:
            rows = db.execute("SELECT * FROM schedules ORDER BY enabled DESC, next_run_at, created_at DESC").fetchall()
        return [self._schedule_payload(row) for row in rows]

    def get_schedule(self, schedule_id: str) -> dict[str, Any]:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM schedules WHERE id=?", (schedule_id,)).fetchone()
        if not row:
            raise KeyError(schedule_id)
        return self._schedule_payload(row)

    def create_schedule(self, value: dict[str, Any]) -> dict[str, Any]:
        name = str(value.get("name") or "").strip()[:160]
        prompt = str(value.get("prompt") or "").strip()[:20000]
        schedule_type = str(value.get("schedule_type") or "once").strip().lower()
        timezone_name = str(value.get("timezone") or "Asia/Shanghai").strip()
        if not name or not prompt:
            raise ValueError("请填写任务名称和完整 Agent 指令")
        if schedule_type not in {"once", "daily", "weekly"}:
            raise ValueError("计划类型只能是一次、每天或每周")
        next_run_at = self._normalize_run_at(str(value.get("next_run_at") or ""), timezone_name)
        if datetime.fromisoformat(next_run_at) <= datetime.now(_timezone(timezone_name)):
            raise ValueError("下一次执行时间必须晚于当前时间")
        schedule_id = "schedule-" + uuid.uuid4().hex
        now = _now()
        with self._lock, self._connect() as db:
            db.execute(
                """
                INSERT INTO schedules (
                    id, name, prompt, schedule_type, timezone, next_run_at,
                    enabled, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 1, 'scheduled', ?, ?)
                """,
                (schedule_id, name, prompt, schedule_type, timezone_name, next_run_at, now, now),
            )
        return self.get_schedule(schedule_id)

    def update_schedule(self, schedule_id: str, value: dict[str, Any]) -> dict[str, Any]:
        current = self.get_schedule(schedule_id)
        name = str(value.get("name", current["name"]) or "").strip()[:160]
        prompt = str(value.get("prompt", current["prompt"]) or "").strip()[:20000]
        schedule_type = str(value.get("schedule_type", current["schedule_type"])).strip().lower()
        timezone_name = str(value.get("timezone", current["timezone"])).strip()
        run_value = value.get("next_run_at", current["next_run_at"])
        next_run_at = self._normalize_run_at(str(run_value), timezone_name) if run_value else ""
        enabled = bool(value.get("enabled", current["enabled"]))
        if not name or not prompt or schedule_type not in {"once", "daily", "weekly"}:
            raise ValueError("定时任务配置无效")
        with self._lock, self._connect() as db:
            db.execute(
                """
                UPDATE schedules SET name=?, prompt=?, schedule_type=?, timezone=?,
                    next_run_at=?, enabled=?, status=?, updated_at=? WHERE id=?
                """,
                (name, prompt, schedule_type, timezone_name, next_run_at or None,
                 1 if enabled else 0, "scheduled" if enabled else "paused", _now(), schedule_id),
            )
        return self.get_schedule(schedule_id)

    def delete_schedule(self, schedule_id: str) -> bool:
        with self._lock, self._connect() as db:
            cursor = db.execute("DELETE FROM schedules WHERE id=?", (schedule_id,))
        return bool(cursor.rowcount)

    @staticmethod
    def _advance(when: datetime, schedule_type: str, now: datetime) -> datetime | None:
        if schedule_type == "once":
            return None
        step = timedelta(days=1 if schedule_type == "daily" else 7)
        candidate = when + step
        while candidate <= now:
            candidate += step
        return candidate

    def mark_overdue_missed(self, grace_seconds: int = 5) -> int:
        now = datetime.now().astimezone()
        cutoff = now - timedelta(seconds=max(0, grace_seconds))
        count = 0
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT * FROM schedules WHERE enabled=1 AND next_run_at IS NOT NULL"
            ).fetchall()
            for row in rows:
                due = datetime.fromisoformat(row["next_run_at"])
                if due > cutoff:
                    continue
                next_run = self._advance(due, row["schedule_type"], now)
                execution_id = "schedule-run-" + uuid.uuid4().hex
                db.execute(
                    "INSERT INTO schedule_runs(id, schedule_id, status, started_at, finished_at, error) VALUES (?, ?, 'missed', ?, ?, ?)",
                    (execution_id, row["id"], due.isoformat(timespec="seconds"), _now(), "后端未运行，已跳过本次计划"),
                )
                db.execute(
                    """
                    UPDATE schedules SET enabled=?, status='missed', next_run_at=?,
                        last_error=?, updated_at=? WHERE id=?
                    """,
                    (1 if next_run else 0, next_run.isoformat(timespec="seconds") if next_run else None,
                     "后端未运行，已跳过本次计划", _now(), row["id"]),
                )
                count += 1
        return count

    def claim_due_schedules(self) -> list[dict[str, Any]]:
        now = datetime.now().astimezone()
        claimed: list[dict[str, Any]] = []
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT * FROM schedules WHERE enabled=1 AND next_run_at IS NOT NULL AND next_run_at<=? ORDER BY next_run_at",
                (now.isoformat(timespec="seconds"),),
            ).fetchall()
            for row in rows:
                due = datetime.fromisoformat(row["next_run_at"])
                next_run = self._advance(due, row["schedule_type"], now)
                execution_id = "schedule-run-" + uuid.uuid4().hex
                db.execute(
                    "INSERT INTO schedule_runs(id, schedule_id, status, started_at) VALUES (?, ?, 'running', ?)",
                    (execution_id, row["id"], _now()),
                )
                db.execute(
                    """
                    UPDATE schedules SET enabled=?, status='running', next_run_at=?,
                        last_run_at=?, last_error='', updated_at=? WHERE id=?
                    """,
                    (1 if next_run else 0, next_run.isoformat(timespec="seconds") if next_run else None,
                     _now(), _now(), row["id"]),
                )
                item = self._schedule_payload(row)
                item["execution_id"] = execution_id
                claimed.append(item)
        return claimed

    def begin_manual_schedule_run(self, schedule_id: str) -> dict[str, Any]:
        schedule = self.get_schedule(schedule_id)
        execution_id = "schedule-run-" + uuid.uuid4().hex
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO schedule_runs(id, schedule_id, status, started_at) VALUES (?, ?, 'running', ?)",
                (execution_id, schedule_id, _now()),
            )
            db.execute(
                "UPDATE schedules SET status='running', last_run_at=?, last_error='', updated_at=? WHERE id=?",
                (_now(), _now(), schedule_id),
            )
        schedule["execution_id"] = execution_id
        return schedule

    def update_schedule_execution(
        self,
        execution_id: str,
        schedule_id: str,
        status: str,
        *,
        run_id: str = "",
        error: str = "",
        finished: bool = False,
    ) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                """
                UPDATE schedule_runs SET run_id=?, status=?, error=?, finished_at=? WHERE id=?
                """,
                (run_id, status, str(error)[:1000], _now() if finished else "", execution_id),
            )
            row = db.execute("SELECT enabled, next_run_at FROM schedules WHERE id=?", (schedule_id,)).fetchone()
            display_status = status
            if finished and status == "completed" and row and row["enabled"] and row["next_run_at"]:
                display_status = "scheduled"
            db.execute(
                """
                UPDATE schedules SET status=?, last_run_id=?, last_error=?, updated_at=? WHERE id=?
                """,
                (display_status, run_id, str(error)[:1000], _now(), schedule_id),
            )

    def schedule_runs(self, schedule_id: str = "", limit: int = 100) -> list[dict[str, Any]]:
        sql = "SELECT * FROM schedule_runs"
        values: list[Any] = []
        if schedule_id:
            sql += " WHERE schedule_id=?"
            values.append(schedule_id)
        sql += " ORDER BY started_at DESC LIMIT ?"
        values.append(max(1, min(500, int(limit))))
        with self._lock, self._connect() as db:
            rows = db.execute(sql, values).fetchall()
        return [dict(row) for row in rows]


def platform_setting(runs_dir: Path, key: str, default: Any = None) -> Any:
    path = Path(runs_dir) / "platform.sqlite3"
    if not path.exists():
        return default
    try:
        connection = sqlite3.connect(path, timeout=2)
        try:
            row = connection.execute("SELECT value_json FROM app_settings WHERE key=?", (key,)).fetchone()
        finally:
            connection.close()
        return json.loads(row[0]) if row else default
    except Exception:
        return default


def platform_sources(runs_dir: Path) -> list[dict[str, str]]:
    path = Path(runs_dir) / "platform.sqlite3"
    if not path.exists():
        return []
    try:
        connection = sqlite3.connect(path, timeout=2)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                "SELECT name, base_url, kind, connector FROM data_sources WHERE enabled=1 ORDER BY built_in DESC, name"
            ).fetchall()
        finally:
            connection.close()
        return [dict(row) for row in rows]
    except Exception:
        return []
