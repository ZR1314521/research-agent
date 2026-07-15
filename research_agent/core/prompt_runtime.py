from __future__ import annotations

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
            "工具执行结果是持久化的——产物文件保存在会话目录下，可以在后续步骤中引用。",
            "当工具返回大量数据时，系统会自动裁剪并保存完整结果到磁盘。模型只收到精简引用，需要时可以再读取。",
            "对话较长时系统会自动压缩较早部分，保留关键信息。这是透明的，你不需要干预。",
        ]
        if session is not None:
            parts.append(self._session_context(session))
        return "\n".join(parts)

    def _session_context(self, session: Any) -> str:
        status = getattr(session, "status", "active")
        artifacts = dict(getattr(session, "artifacts", {}) or {})
        pending = getattr(session, "pending_action", None)
        plan = getattr(session, "metadata", {}).get("plan_mode", False)

        parts: list[str] = []
        if plan:
            parts.append("当前处于规划模式。写操作工具已隐藏，搜索和阅读工具可用但建议先向用户说明意图。")
        if pending:
            parts.append(f"有一个待处理的确认请求：{pending.get('type', '')} — {pending.get('summary', '')[:120]}")
        if artifacts:
            names = list(artifacts.keys())[:8]
            parts.append(f"会话已有产物：{', '.join(names)}" + ("..." if len(artifacts) > 8 else ""))
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
            self._harness(session),
            self._data_sources(),
        ]
        return "\n".join(part for part in layers if part).strip()

    def tools_for_llm(self, read_only: bool = False) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for tool in self.registry.tool_catalog():
            if not tool.get("executable"):
                continue
            if read_only and tool.get("write_access"):
                continue
            description = str(tool.get("description") or "")
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
