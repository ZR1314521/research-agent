from __future__ import annotations

from pathlib import Path
from typing import Any

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
        return self.system_path.read_text(encoding="utf-8").strip()

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
