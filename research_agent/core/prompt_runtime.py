from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from research_agent.platform_store import platform_sources
from research_agent.skill_registry import SkillRegistry


class PromptRuntime:
    """Build a multi-layered system prompt that describes the agent's
    environment and capabilities rather than prescribing behaviour."""

    def __init__(self, registry: SkillRegistry):
        self.registry = registry
        self._identity_path = registry.skills_dir.parent / "research_agent" / "prompts" / "agent_system.md"

    # ── layers ─────────────────────────────────────────────────────────

    def _identity(self) -> str:
        if self._identity_path.exists():
            return self._identity_path.read_text(encoding="utf-8").strip()
        return "你是一个科研助手。"

    def _harness(self, session: Any | None) -> str:
        """Describe what the infrastructure does, so the model knows its
        bounds without being told what to do."""
        parts = [
            "你运行在一个本地工作台中。你可以调用的工具列在每条消息的 tool list 里。",
            f"当前本地日期是 {datetime.now().astimezone().date().isoformat()}。遇到‘近三年’等相对时间时，以此日期动态换算，并在回答中写明实际年份范围。",
            "当前消息优先于旧任务。已有成果足以支持当前请求时优先复用；是否复用由你根据当前目标和证据判断，不按预设工具流程推进。",
            "每个会话有独立工作区；上传、工具文件读写和产物都位于该工作区。相对路径以当前会话工作区为基准。",
            "当工具返回大量数据时，系统会自动裁剪并保存完整结果到磁盘。模型只收到精简引用，需要时可以再读取。",
            "对话较长时系统会自动压缩较早部分，保留关键信息。这是透明的，你不需要干预。",
            "工具完成后，应直接给用户一份可读的最终结论：先回答问题，再说明证据与局限，最后按需引用成果。不要把 JSON、内部日志或文件路径列表当作最终答案。",
            "若工具观察标记 answer_ready=true，说明其中已包含回答当前问题所需的证据；应直接综合回答。只有用户明确要求额外成果，或观察明确指出缺少某个必要字段时，才继续读取内部文件或调用新的产物工具。",
        ]
        return "\n".join(parts)

    def _session_context(self, session: Any) -> str:
        status = getattr(session, "status", "active")
        artifacts = dict(getattr(session, "artifacts", {}) or {})
        artifact_records = dict(getattr(session, "artifact_records", {}) or {})
        pending = getattr(session, "pending_action", None)
        plan = getattr(session, "metadata", {}).get("plan_mode", False)

        parts: list[str] = []
        if plan:
            parts.append("当前处于规划模式。写操作工具已隐藏，搜索和阅读工具可用但建议先向用户说明意图。")
        if pending:
            parts.append(f"有一个待处理的确认请求：{pending.get('type', '')} — {pending.get('summary', '')[:120]}")
        if artifacts:
            entries: list[str] = []
            seen_paths: set[str] = set()
            for name in artifacts:
                record = artifact_records.get(name) if isinstance(artifact_records.get(name), dict) else {}
                artifact_path = str(record.get("path") or artifacts.get(name) or "").strip()
                path_key = artifact_path.casefold()
                if path_key and path_key in seen_paths:
                    continue
                if path_key:
                    seen_paths.add(path_key)
                details = [
                    str(record.get("type") or "").strip(),
                    str(record.get("producer") or "").strip(),
                    f"path={artifact_path}" if artifact_path else "",
                ]
                details = [item for item in details if item]
                entries.append(name + (f" ({'; '.join(details)})" if details else ""))
                if len(entries) >= 8:
                    break
            parts.append(f"会话已有产物：{', '.join(entries)}" + ("..." if len(entries) < len(artifacts) else ""))
        return "\n".join(parts)

    def _data_sources(self) -> str:
        root = self.registry.skills_dir.parent
        sources = [s for s in platform_sources(root / "runs") if not s.get("connector")]
        if not sources:
            return ""
        lines = ["\n用户启用的自定义数据源："]
        for s in sources:
            if s.get("kind") == "free":
                domain = urlparse(s["base_url"]).netloc
                lines.append(f"- {s['name']}: {s['base_url']}（检索时可加 site:{domain}）")
            else:
                lines.append(f"- {s['name']}: 凭据已本地保存，专属连接器尚未安装")
        return "\n".join(lines)

    # ── public ─────────────────────────────────────────────────────────

    def system(self, session: Any | None = None) -> str:
        layers = [
            self._identity(),
            "",
            self._harness(None),
            self._data_sources(),
        ]
        return "\n".join(part for part in layers if part).strip()

    def runtime_context(self, session: Any | None) -> str:
        """Dynamic state appended at the conversation tail, not the cache prefix."""
        return self._session_context(session) if session is not None else ""

    def tools_for_llm(self, read_only: bool = False, mode: str = "active") -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for tool in self.registry.tool_catalog():
            if not tool.get("executable"):
                continue
            if tool.get("available_in") and mode not in tool["available_in"]:
                continue
            if read_only and tool.get("write_access"):
                continue
            description = str(tool.get("description") or "")
            capability_notes: list[str] = []
            if tool.get("consumes"):
                capability_notes.append("Consumes: " + ", ".join(str(item) for item in tool["consumes"]))
            if tool.get("produces"):
                capability_notes.append("Produces: " + ", ".join(str(item) for item in tool["produces"]))
            if capability_notes:
                description += " " + "; ".join(capability_notes) + ". The model decides whether this capability is useful from the current goal and available evidence."
            if tool.get("batch_policy") == "single":
                description += " Submit at most one call to this tool per assistant response; combine related inputs into its array parameters."
            if read_only:
                description += " (plan mode: confirm with user before calling)"
            schema = tool.get("input_schema", {})
            result.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": description,
                    "parameters": {
                        "type": "object",
                        "properties": schema.get("properties", {}),
                        "required": schema.get("required", []),
                        "additionalProperties": False,
                    },
                },
            })
        return result
