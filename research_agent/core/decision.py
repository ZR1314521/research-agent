from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DecisionType(StrEnum):
    RESPOND = "respond"
    ASK_USER = "ask_user"
    TOOL_CALL = "tool_call"
    CHECKPOINT = "checkpoint"
    FINISH = "finish"


@dataclass
class Decision:
    type: DecisionType
    message: str = ""
    tool: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    goal_update: str = ""
    task_plan: list[dict[str, Any]] = field(default_factory=list)
    after_success: str = "finish"
    plan: dict[str, Any] | None = None

    @classmethod
    def from_text(cls, text: str) -> "Decision":
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end < start:
            raise ValueError("模型没有返回结构化决策")
        payload = json.loads(cleaned[start : end + 1])
        if not isinstance(payload, dict):
            raise ValueError("模型决策必须是 JSON 对象")
        raw_type = str(payload.get("type") or payload.get("action") or "").strip().lower()
        aliases = {"tool": "tool_call", "call_tool": "tool_call", "question": "ask_user"}
        raw_type = aliases.get(raw_type, raw_type)
        try:
            decision_type = DecisionType(raw_type)
        except ValueError as exc:
            raise ValueError(f"未知决策类型: {raw_type or '<empty>'}") from exc
        arguments = payload.get("arguments", {})
        if not isinstance(arguments, dict):
            raise ValueError("tool arguments 必须是对象")
        tool = str(payload.get("tool") or payload.get("skill") or "").strip()
        task_plan = payload.get("task_plan") or []
        if not isinstance(task_plan, list) or any(not isinstance(item, dict) for item in task_plan):
            raise ValueError("task_plan must be an array of objects")
        if decision_type == DecisionType.TOOL_CALL and not tool:
            raise ValueError("tool_call 缺少 tool")
        after_success = str(payload.get("after_success") or "finish").lower()
        if after_success not in {"finish", "replan", "checkpoint"}:
            raise ValueError("after_success must be finish, replan, or checkpoint")
        plan_raw = payload.get("plan")
        plan = plan_raw if isinstance(plan_raw, dict) and plan_raw.get("steps") else None
        return cls(
            type=decision_type,
            message=str(payload.get("message") or payload.get("reply") or "").strip(),
            tool=tool,
            arguments=arguments,
            reason=str(payload.get("reason") or "").strip(),
            goal_update=str(payload.get("goal_update") or payload.get("next_goal") or "").strip(),
            task_plan=task_plan,
            after_success=after_success,
            plan=plan,
        )

    def as_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "type": self.type.value,
            "message": self.message,
            "tool": self.tool,
            "arguments": self.arguments,
            "reason": self.reason,
            "goal_update": self.goal_update,
            "task_plan": self.task_plan,
            "after_success": self.after_success,
        }
        if self.plan:
            d["plan"] = self.plan
        return d
