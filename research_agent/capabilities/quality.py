from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class QualityAuditService:
    def __init__(self, session_dir: Path):
        self.session_dir = session_dir

    def answer(self, arguments: dict[str, Any], artifacts: dict[str, str], events: list[dict[str, Any]]) -> dict[str, Any]:
        search_plan = self._json_artifact(artifacts.get("recursive_search_plan"))
        errors = self._json_artifact(artifacts.get("literature_search_errors"))
        active = self._json_artifact(artifacts.get("active_papers"))
        excluded = self._json_artifact(artifacts.get("excluded_papers"))
        edge = self._json_artifact(artifacts.get("edge_papers"))
        execution = self._execution_log()

        source_counts: dict[str, int] = {}
        stop_reasons = []
        if isinstance(search_plan, dict):
            for round_item in search_plan.get("rounds", []):
                stop = round_item.get("stop_reason")
                if stop:
                    stop_reasons.append(f"round {round_item.get('round')}: {stop}")
                for item in round_item.get("source_requests", []):
                    source = item.get("source") or "unknown"
                    source_counts[source] = source_counts.get(source, 0) + 1
        if not source_counts and isinstance(errors, list):
            for item in errors:
                source = item.get("source") or "unknown"
                source_counts.setdefault(source, 0)

        failures = []
        if isinstance(errors, list):
            failures.extend(f"{item.get('source')}: {item.get('error')}" for item in errors)
        failures.extend(
            f"{item.get('skill') or item.get('step')}: {item.get('summary')}"
            for item in execution
            if item.get("event") == "failed" or item.get("status") == "failed"
        )

        lines = ["# 质量追责", ""]
        if source_counts:
            lines.append("## 请求次数")
            lines.extend(f"- {source}: {count}" for source, count in sorted(source_counts.items()))
            lines.append("")
        lines.extend(
            [
                "## 文献数量",
                f"- 纳入池: {len(active) if isinstance(active, list) else 0}",
                f"- 排除池: {len(excluded) if isinstance(excluded, list) else 0}",
                f"- 边缘池: {len(edge) if isinstance(edge, list) else 0}",
                "",
            ]
        )
        if failures:
            lines.append("## 失败来源")
            lines.extend(f"- {item}" for item in failures[:20])
            lines.append("")
        if stop_reasons:
            lines.append("## 停止条件")
            lines.extend(f"- {item}" for item in stop_reasons)
            lines.append("")
        if artifacts:
            lines.append("## 相关产物")
            for key in ("paper_pool_markdown", "active_papers", "excluded_papers", "edge_papers", "recursive_search_plan", "literature_search_errors"):
                if artifacts.get(key):
                    lines.append(f"- {key}: {artifacts[key]}")
        if len(lines) <= 8:
            lines.append("当前会话没有足够日志。请先执行检索、筛选或工作流任务。")

        path = self.session_dir / "quality_audit.md"
        path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        return {"message": path.read_text(encoding="utf-8"), "artifacts": {"quality_audit": str(path)}, "data": {}}

    def _json_artifact(self, raw_path: str | None) -> Any:
        if not raw_path:
            return None
        path = Path(raw_path)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return None

    def _execution_log(self) -> list[dict[str, Any]]:
        path = self.session_dir / "execution_log.jsonl"
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

