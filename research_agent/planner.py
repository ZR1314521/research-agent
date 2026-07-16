from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from research_agent.config import AgentConfig
from research_agent.intent import IntentParser, ResearchIntent
from research_agent.logging import ModelCallLogger
from research_agent.session import ChatSession
from research_agent.skill_registry import SkillRegistry
from research_agent.tools.llm_client import LLMClient


@dataclass
class Action:
    skill: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class Plan:
    actions: list[Action] = field(default_factory=list)
    reply: str = ""
    source: str = "rules"

    @property
    def action(self) -> Action | None:
        return self.actions[0] if self.actions else None


class RulePlanner:
    def __init__(self) -> None:
        self.parser = IntentParser()

    def plan(self, text: str, session: ChatSession) -> Plan:
        intent = self.parser.parse(text, session.artifacts)
        if intent.reply:
            return Plan(reply=intent.reply)
        actions = self._actions(intent, session)
        if not actions:
            return Plan(reply=self._fallback_reply(text, session))
        return Plan(actions=actions, source="rules")

    def _actions(self, intent: ResearchIntent, session: ChatSession) -> list[Action]:
        actions: list[Action] = []
        if intent.has("quality_audit"):
            return [Action("quality-audit", {"request": intent.raw})]
        if intent.has("workflow_control"):
            action = self._workflow_action(intent)
            if action:
                return [action]
        if intent.has("document_summary"):
            return [Action("document-summary", self._common_args(intent))]
        if intent.has("file_upload"):
            actions.append(Action("file-upload-router", {"paths": intent.files}))
            # Import plus "analyze this file" should continue in the same turn.
            if not (intent.has("data_analysis") or intent.has("rag") or intent.has("references")):
                return actions
        if intent.has("rag") and not intent.has("literature_search"):
            return [*actions, Action("rag-vector-knowledge-base", {"query": self._rag_query(intent), "scope": intent.scope or "uploaded"})]
        if intent.has("data_transform"):
            return [*actions, Action("data-transform", self._common_args(intent))]
        if intent.has("docx") and not intent.has("literature_search") and not intent.has("data_analysis"):
            return [*actions, Action("docx", self._common_args(intent))]
        if intent.has("docx") and intent.has("data_analysis") and not intent.files and re.search(r"保存|导出|转|另存", intent.raw):
            return [*actions, Action("docx", self._common_args(intent))]
        if intent.has("references") and not intent.has("literature_search"):
            return [*actions, Action("reference-format-gbt7714", self._reference_args(intent))]
        if intent.has("data_analysis"):
            result = [*actions, Action("experiment-data-analysis", self._common_args(intent))]
            if intent.has("docx"):
                result.append(Action("docx", self._common_args(intent)))
            return result
        if intent.has("screen"):
            return [Action("literature-screening", self._screen_args(intent))]
        if intent.has("literature_search"):
            actions.append(Action("academic-search-multisource", self._literature_args(intent)))
            if intent.requires_confirmation:
                return actions
            if intent.has("matrix"):
                actions.append(Action("literature-matrix-extraction", {"limit": intent.limit or 10, "request": intent.raw}))
            if intent.has("review"):
                actions.append(Action("systematic-literature-review", {"request": intent.raw}))
            if intent.has("references"):
                actions.append(Action("reference-format-gbt7714", self._reference_args(intent)))
            if intent.has("docx"):
                actions.append(Action("docx", self._common_args(intent)))
            return actions
        if intent.has("matrix"):
            return [Action("literature-matrix-extraction", {"limit": intent.limit or 10, "request": intent.raw})]
        if intent.has("paper_writing"):
            return [Action("20-ml-paper-writing", {"request": intent.raw})]
        if intent.has("review"):
            return [Action("systematic-literature-review", {"request": intent.raw})]
        if intent.has("humanize"):
            return [Action("humanizer", {"request": intent.raw, "text": self._inline_text(intent.raw)})]
        if intent.has("visual"):
            return [Action("canvas-design", {"request": intent.raw})]
        if intent.has("docx"):
            return [Action("docx", self._common_args(intent))]
        return actions

    def _common_args(self, intent: ResearchIntent) -> dict[str, Any]:
        args: dict[str, Any] = {
            "request": intent.raw,
            "output_path": intent.output_path,
            "ops": intent.transform_ops,
            "keep_columns": intent.keep_columns,
        }
        if intent.files:
            args["path"] = intent.files[0]
        return {key: value for key, value in args.items() if value not in ("", [], None)}

    def _literature_args(self, intent: ResearchIntent) -> dict[str, Any]:
        args = {
            "query": intent.query,
            "year_from": intent.year_from,
            "year_to": intent.year_to,
            "venues": intent.venues,
            "sources": intent.sources or self._default_sources(intent),
            "limit": intent.limit or 12,
            "rounds": intent.rounds,
            "max_requests_per_source": intent.max_requests_per_source,
            "must_include": intent.must_include,
            "exclude": intent.exclude,
            "sort_by": intent.sort_by,
            "precise": bool(intent.must_include or intent.exclude or re.search(r"必须|只要|精准", intent.raw)),
            "no_network": intent.no_network,
            "request": intent.raw,
        }
        if intent.output_path:
            args["output_path"] = intent.output_path
        return {key: value for key, value in args.items() if value not in ("", [], None)}

    def _reference_args(self, intent: ResearchIntent) -> dict[str, Any]:
        args = {"styles": intent.styles or ["gbt7714-numeric"], "request": intent.raw}
        if intent.files:
            args["path"] = intent.files[0]
        return args

    def _screen_args(self, intent: ResearchIntent) -> dict[str, Any]:
        # Offline compatibility must still honor the same public tool contract.
        allowed = {"query", "year_from", "year_to", "venues", "must_include", "exclude", "precise", "request"}
        return {key: value for key, value in self._literature_args(intent).items() if key in allowed}

    def _default_sources(self, intent: ResearchIntent) -> list[str]:
        if intent.no_network:
            return []
        return ["openalex", "semantic_scholar", "pubmed", "arxiv"]

    def _workflow_action(self, intent: ResearchIntent) -> Action | None:
        text = intent.raw
        if re.search(r"暂停|pause", text, re.IGNORECASE):
            return Action("workflow-state-manager", {"command": "pause", "request": text})
        if re.search(r"继续|恢复|resume|接着", text, re.IGNORECASE):
            return Action("workflow-state-manager", {"command": "resume", "request": text})
        if re.search(r"状态|status|上次任务", text, re.IGNORECASE):
            return Action("workflow-state-manager", {"command": "status", "request": text})
        if re.search(r"从.*重跑|目标.*改|不要重新联网", text):
            return Action("workflow-state-manager", {"command": "change", "request": text, "limit": intent.limit})
        return None

    def _rag_query(self, intent: ResearchIntent) -> str:
        return re.sub(r"(?:只依据|只用|我上传|资料|回答|给出处|不要.*编|不要联网|本地)", " ", intent.raw).strip(" ：:，。") or intent.raw

    def _inline_text(self, text: str) -> str:
        match = re.search(r"(?:润色|改写|humanize|太像\s*ai|去\s*ai)(?:一下|这段|以下|：|:)*\s*(.+)$", text, re.IGNORECASE)
        return match.group(1).strip() if match else ""

    def _fallback_reply(self, text: str, session: ChatSession) -> str:
        stripped = text.strip()
        last_assistant = next((item for item in reversed(session.messages[:-1]) if item.get("role") == "assistant"), None)
        last_content = str(last_assistant.get("content", "")) if last_assistant else ""
        if re.fullmatch(r"[？?。.!！!…\s]+", stripped):
            if last_assistant and ("请直接说要" in last_content or "没有把这句话" in last_content):
                return (
                    "刚才那句太像命令菜单了，不合适。这个终端现在应该是交互式科研智能体："
                    "你可以正常聊天、改条件、追问原因，也可以直接给科研任务。"
                    "比如“找近三年某个研究主题的论文，先给候选”，我会拆成检索、筛选、确认、矩阵、综述这些步骤。"
                )
            return "刚才我没接住你的意思。你可以直接说“不是，我问的是……”我会按上下文改回答，不会默认调用工具。"
        if re.search(r"答非所问|不对|不是|你说的啥|说啥|没问这个|啥意思|没懂|不是这个", stripped, re.IGNORECASE):
            return (
                "你说得对，我刚才答偏了。"
                "我应该先判断你是在聊天、纠正我，还是要执行科研任务，而不是马上切回工具提示。"
                "你刚才这句我理解为：你在指出上一轮回答没有对上你的意思。你可以接着说你真正想问的点，我按那个重新答。"
            )
        if re.fullmatch(r"(唉|哎|哎呀|害|无语|服了|算了|崩溃|难绷)[。.!！!？?\s]*", stripped, re.IGNORECASE):
            return (
                "我知道，你是在反馈刚才这段对话体验不对。"
                "问题不是你没说清楚，而是我应该把这种短句当作上下文反馈来处理，先承认偏差，再回到你的真实意图。"
                "你可以继续按自然语言说，我会先接上下文，不会再把每句话都硬塞进工具菜单。"
            )
        if re.fullmatch(r"(nihao|ninhao|hello|hi|hey|你好|您好|你好啊|在吗|在不在)[。.!！!？?\s]*", stripped, re.IGNORECASE):
            return "你好，我在。你可以先随便聊需求，也可以直接给科研任务；我会先理解上下文，再决定要不要调用工具。"
        if re.search(r"更新|升级", stripped, re.IGNORECASE):
            return (
                "知道，我现在这版是面向高校科研场景的交互式科研智能体。"
                "不是只能跑一条固定流水线，而是先理解你的自然语言，再按需要调用检索、筛选、矩阵、综述、数据分析、引用格式、文件导出、RAG 和流程状态这些能力。"
                "你可以先随便问，也可以直接给任务。"
            )
        if re.search(r"是不是|框架|chat|交互|能干嘛|怎么用|能力", stripped, re.IGNORECASE):
            return (
                "应该是 chat 类型，而且背后有工作流框架。当前设计是：自然语言输入 -> 意图解析 -> 多步骤计划 -> 工具执行 -> 状态和日志记录。"
                "如果只是聊天或确认，我会直接回答；如果是科研任务，我会拆成可追踪步骤。"
                "现在你可以用一句话测试，比如“找近 3 年某个研究主题的论文，排除综述，先给我候选”。"
            )
        if re.search(r"谢谢|好的|ok|嗯|行|明白", stripped, re.IGNORECASE):
            return "收到。你继续说下一步就行，我会根据上下文判断是追问、改条件，还是执行新的科研步骤。"
        return (
            "这句我先按普通对话处理，不调用工具。"
            "我没完全接住你的意思，换句话说一下就行；如果你是在接着上一轮纠正我，也可以直接说“不是，我的意思是……”。"
        )


class Planner:
    def __init__(self, config: AgentConfig, registry: SkillRegistry, session_dir: Path):
        self.config = config
        self.registry = registry
        self.rules = RulePlanner()
        self.client = LLMClient(config, ModelCallLogger(session_dir))

    def plan(self, text: str, session: ChatSession) -> Plan:
        rule_plan = self.rules.plan(text, session)
        if rule_plan.actions or rule_plan.reply or not self.config.llm_configured:
            return rule_plan
        prompt = json.dumps(
            {
                "instruction": (
                    "Parse the user request into zero or more ordered local skill actions. "
                    "Return JSON only: {actions:[{skill:string, arguments:object}], reply:string}. "
                    "Prefer asking one clarifying question when key constraints are missing."
                ),
                "skills": self.registry.planner_catalog(),
                "active_artifacts": session.artifacts,
                "recent_messages": session.messages[-6:],
                "user_message": text,
            },
            ensure_ascii=False,
        )
        result = self.client.complete("chat_plan", prompt, fallback="", temperature=0)
        if not result.used_remote_model:
            return rule_plan
        try:
            data = self._json(result.text)
            actions = []
            for raw in data.get("actions") or []:
                if not isinstance(raw, dict) or not raw.get("skill"):
                    continue
                spec = self.registry.get(str(raw["skill"]))
                if not spec.planner_visible:
                    continue
                arguments = raw.get("arguments") if isinstance(raw.get("arguments"), dict) else {}
                actions.append(Action(spec.name, arguments))
            if actions:
                return Plan(actions=actions, reply=str(data.get("reply") or ""), source="model")
            return Plan(reply=str(data.get("reply") or rule_plan.reply), source="model")
        except (ValueError, KeyError, json.JSONDecodeError):
            return rule_plan

    def _json(self, text: str) -> dict[str, Any]:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end < start:
            raise ValueError("Planner did not return JSON")
        data = json.loads(cleaned[start : end + 1])
        if not isinstance(data, dict):
            raise ValueError("Planner JSON must be an object")
        return data
