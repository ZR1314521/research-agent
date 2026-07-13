from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from research_agent.session import ChatSession
from research_agent.skill_registry import SkillRegistry


class UserOutcomeObserver:
    """Passive, best-effort observation of what the user actually received."""

    def __init__(self, report_dir: Path, registry: SkillRegistry):
        self.report_dir = report_dir
        self.registry = registry
        self.records_path = report_dir / "user_outcomes.jsonl"
        self.report_path = report_dir / "user_outcomes.md"

    def record(
        self,
        session: ChatSession,
        user_message: str,
        assistant_message: str,
        events: list[dict[str, Any]],
        *,
        waiting: bool = False,
        provider_calls: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        tool_requests = [event for event in events if event.get("event") == "tool_requested"]
        tool_failures = [
            event for event in events
            if event.get("event") == "tool_observed" and event.get("ok") is False
        ]
        model_failures = [
            event for event in events
            if event.get("event") in {"failed", "model_followup_failed"}
        ]
        write_capable_tools: list[str] = []
        for event in tool_requests:
            name = str(event.get("skill") or "")
            try:
                if self.registry.resolve(name).write_access:
                    write_capable_tools.append(name)
            except KeyError:
                continue
        artifacts: dict[str, dict[str, Any]] = {}
        for event in events:
            for name, raw_path in (event.get("artifacts") or {}).items():
                path = Path(str(raw_path))
                artifacts[name] = {"path": str(path), "exists": path.exists()}

        if any(event.get("event") == "finished" for event in events):
            status = "completed"
        elif waiting:
            status = "waiting_user"
        elif model_failures:
            status = "failed"
        else:
            status = "returned"
        record = {
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            "session_id": session.session_id,
            "status": status,
            "user_message": user_message,
            "assistant_message": assistant_message,
            "tools": [
                {"name": event.get("skill", ""), "arguments": event.get("arguments", {})}
                for event in tool_requests
            ],
            "tool_failures": [
                {
                    "name": event.get("skill", ""),
                    "error": event.get("summary", ""),
                    "error_code": event.get("error_code", ""),
                }
                for event in tool_failures
            ],
            "model_failures": [event.get("error") or event.get("summary", "") for event in model_failures],
            "repeated_calls_rejected": sum(
                1 for event in tool_failures if event.get("error_code") == "duplicate_tool_call"
            ),
            # Capability exposure is factual registry metadata. It does not
            # infer user intent or claim that a mutation actually occurred.
            "write_capable_tools": list(dict.fromkeys(write_capable_tools)),
            "artifacts": artifacts,
            "provider_calls": list(provider_calls or []),
            "provider_call_count": len(provider_calls or []),
            "provider_retry_count": sum(
                1 for item in (provider_calls or []) if int(item.get("attempt") or 1) > 1
            ),
        }
        self.report_dir.mkdir(parents=True, exist_ok=True)
        with self.records_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        self._render()
        return record

    def _render(self) -> None:
        records: list[dict[str, Any]] = []
        if self.records_path.exists():
            for line in self.records_path.read_text(encoding="utf-8").splitlines():
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    records.append(value)
        completed = sum(item.get("status") == "completed" for item in records)
        failed = sum(item.get("status") == "failed" for item in records)
        repeated = sum(int(item.get("repeated_calls_rejected") or 0) for item in records)
        lines = [
            "# 用户结果验收报告",
            "",
            "这是旁路观察报告，不参与模型提示、意图判断、工具选择或执行。",
            "",
            f"- 已记录轮次：{len(records)}",
            f"- 正常完成：{completed}",
            f"- 最终失败：{failed}",
            f"- 拒绝的重复调用：{repeated}",
            "",
            "## 最近结果",
            "",
            "| 时间 | 状态 | 用户请求 | 最终回答 | 工具 | 调用了可写工具 | 错误 | 成果 |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for item in records[-100:][::-1]:
            tools = ", ".join(tool.get("name", "") for tool in item.get("tools", [])) or "-"
            mutations = ", ".join(item.get("write_capable_tools", item.get("mutation_tools", []))) or "-"
            errors = len(item.get("tool_failures", [])) + len(item.get("model_failures", []))
            artifacts = sum(1 for value in item.get("artifacts", {}).values() if value.get("exists"))
            lines.append(
                "| {time} | {status} | {request} | {answer} | {tools} | {mutations} | {errors} | {artifacts} |".format(
                    time=self._cell(item.get("timestamp", ""), 25),
                    status=self._cell(item.get("status", ""), 20),
                    request=self._cell(item.get("user_message", ""), 80),
                    answer=self._cell(item.get("assistant_message", ""), 100),
                    tools=self._cell(tools, 60),
                    mutations=self._cell(mutations, 40),
                    errors=errors,
                    artifacts=artifacts,
                )
            )
        self.report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def _cell(value: Any, limit: int) -> str:
        text = " ".join(str(value or "").split()).replace("|", "\\|")
        return text if len(text) <= limit else text[: limit - 1] + "…"
