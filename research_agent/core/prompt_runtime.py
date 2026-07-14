from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from research_agent.platform_store import platform_sources
from research_agent.skill_registry import SkillRegistry


class PromptRuntime:
    """Expose capabilities and factual session context to the model.

    This class does not classify user intent, route tasks, or encode workflows.
    """

    def __init__(self, registry: SkillRegistry):
        self.registry = registry
        self.system_path = registry.skills_dir.parent / "research_agent" / "prompts" / "agent_system.md"

    def system(self, session: Any | None = None) -> str:
        if not self.system_path.exists():
            raise FileNotFoundError(f"Missing agent system prompt: {self.system_path}")
        prompt = self.system_path.read_text(encoding="utf-8").strip()
        root_dir = self.registry.skills_dir.parent
        custom_sources = [
            source for source in platform_sources(root_dir / "runs")
            if not source.get("connector")
        ]
        if custom_sources:
            lines = ["\n\n当前用户启用的自定义数据源："]
            for source in custom_sources:
                if source.get("kind") == "free":
                    domain = urlparse(source["base_url"]).netloc
                    lines.append(
                        f"- {source['name']}: {source['base_url']}。网页检索时可把 site:{domain} 加入查询。"
                    )
                else:
                    lines.append(
                        f"- {source['name']}: 已在本机保存凭据，但尚未安装专属连接器；不要声称已经登录。"
                    )
            prompt += "\n".join(lines)
        return prompt

    def tools_for_llm(self, read_only: bool = False) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for tool in self.registry.tool_catalog():
            if not tool.get("executable"):
                continue
            schema = tool.get("input_schema", {})
            description = str(tool.get("description") or "")
            if read_only and tool.get("write_access"):
                description += " Planning mode is active: only non-mutating operations are permitted."
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
