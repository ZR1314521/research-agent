from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from threading import Event
from typing import Any, Callable

from research_agent.config import AgentConfig
from research_agent.context import ContextManager
from research_agent.core.contracts import ContractError, public_artifacts, register_artifacts
from research_agent.core.prompt_runtime import PromptRuntime
from research_agent.executor import ToolExecutor
from research_agent.logging import ModelCallLogger
from research_agent.session import ChatSession, SessionStore
from research_agent.skill_registry import SkillRegistry
from research_agent.tools.llm_client import LLMClient
from research_agent.provider_runtime import (
    ProviderEvent,
    call_context,
)


Progress = Callable[[str, str], None]


@dataclass
class AgentResult:
    message: str
    skill: str = ""
    waiting: bool = False


@dataclass
class LoopState:
    last_skill: str = ""
    last_success: str = ""
    seen_calls: set[str] = field(default_factory=set)
    rejected_repeats: set[str] = field(default_factory=set)
    last_call_id: str = ""
    answer_ready: bool = False
    completion_guidance: str = ""


class AgentLoop:
    """Native model/tool conversation with persisted human approval checkpoints."""

    def __init__(
        self,
        config: AgentConfig,
        registry: SkillRegistry,
        sessions: SessionStore,
        session_dir: Path,
        progress: Progress | None = None,
        cancel_event: Event | None = None,
        event_sink: Callable[[ProviderEvent], Any] | None = None,
        pause_gate: Callable[[], bool | str] | None = None,
        rate_limit_gate: Callable[[float | None], bool] | None = None,
    ) -> None:
        self.config = config
        self.registry = registry
        self.sessions = sessions
        self.session_dir = session_dir
        self.progress = progress
        self.prompts = PromptRuntime(registry)
        self.cancel_event = cancel_event
        self.event_sink = event_sink
        self.pause_gate = pause_gate
        self.rate_limit_gate = rate_limit_gate
        self.client = LLMClient(config, ModelCallLogger(session_dir), cancel_event)
        self.executor = ToolExecutor(config, registry, session_dir, cancel_event)
        self.context = ContextManager(
            session_dir,
            config.context_window,
            context_budget=config.context_budget,
            observation_budget=config.context_observation_budget,
        )

    def run(self, session: ChatSession, user_message: str) -> AgentResult:
        return self._drive(session, self._conversation(session, user_message), user_message, LoopState())

    def resume(self, session: ChatSession, approved: bool) -> AgentResult:
        return self._resume(session, approved)

    def _resume(self, session: ChatSession, approved: bool) -> AgentResult:
        pending = session.pending_action or {}
        pending_type = pending.get("type")
        if pending_type not in {"tool_approval", "plan_approval"}:
            return AgentResult("当前没有等待确认的操作。", waiting=False)

        messages = [dict(item) for item in pending.get("model_messages", session.model_messages)]
        # Purge orphan tool_calls left by a cancelled turn before the
        # sanitisation fix — otherwise the provider returns HTTP 400.
        if messages and messages[-1].get("role") == "assistant" and messages[-1].get("tool_calls"):
            messages[-1].pop("tool_calls", None)
            if not messages[-1].get("content"):
                messages[-1]["content"] = "（操作已取消）"
        user_message = str(pending.get("user_message") or "")
        state = LoopState(
            last_skill=str(pending.get("last_skill") or ""),
            last_success=str(pending.get("last_success") or ""),
            last_call_id=str(pending.get("last_call_id") or ""),
        )
        session.pending_action = None
        session.status = "active"

        if pending_type == "plan_approval":
            self.sessions.event(session, "approval_resolved", summary="plan accepted" if approved else "plan rejected", approved=approved)
            if not approved:
                messages.append({"role": "user", "content": "The user rejected the proposed plan. Do not execute it."})
                message = "已拒绝执行该计划，计划内容和已有成果仍然保留。你仍处于 Plan 模式，可以继续调整计划。"
                messages.append({"role": "assistant", "content": message})
                session.model_messages = list(messages)
                session.status = "planning"
                session.add_message("assistant", message)
                self.sessions.save(session)
                return AgentResult(message)
            control = "The user approved the immediately preceding plan. Exit planning mode and execute it now using the available tools."
            messages.append({"role": "user", "content": control})
            session.add_message("user", "Accept", control=True)
            session.metadata.pop("plan_mode", None)
            self.sessions.save(session)
            return self._drive(session, messages, user_message, state)

        raw_calls = pending.get("tool_calls") or []
        if approved:
            self.sessions.event(session, "approval_resolved", state.last_skill, "tool call accepted", approved=True)
            stopped = self._execute_calls(session, messages, raw_calls, user_message, state)
            if stopped:
                return stopped
        else:
            self.sessions.event(session, "approval_resolved", state.last_skill, "tool call rejected", approved=False)
            for raw_call in raw_calls:
                call_id = str(raw_call.get("id") or "tool-rejected")
                function = raw_call.get("function") if isinstance(raw_call.get("function"), dict) else {}
                name = str(function.get("name") or "tool")
                self._append_tool_message(messages, call_id, {
                    "ok": False,
                    "tool": name,
                    "error": "The user rejected this tool call. No side effect was performed.",
                    "error_code": "user_rejected",
                })
                function = raw_call.get("function") if isinstance(raw_call.get("function"), dict) else {}
                arguments, error = self._arguments(function.get("arguments"))
                if not error:
                    try:
                        spec = self.registry.resolve(str(function.get("name") or "").strip())
                        state.seen_calls.add(f"{spec.name}:{json.dumps(arguments, ensure_ascii=False, sort_keys=True, default=str)}")
                    except KeyError:
                        pass
        session.model_messages = list(messages)
        self.sessions.save(session)
        return self._drive(session, messages, user_message, state)

    def _drive(
        self,
        session: ChatSession,
        messages: list[dict[str, Any]],
        user_message: str,
        state: LoopState,
    ) -> AgentResult:
        base_tools = self.prompts.tools_for_llm(read_only=(session.status == "planning"))
        turn = 0
        while True:
            turn += 1
            if self.config.agent_emergency_turn_limit and turn > self.config.agent_emergency_turn_limit:
                message = state.last_success or "模型工具循环触发了可配置的紧急保护；当前会话和成果已保留。"
                return self._finish(session, message, state.last_skill, messages)
            if self.cancel_event and self.cancel_event.is_set():
                return self._cancelled(session, state.last_skill, messages)
            if self.pause_gate:
                boundary = self.pause_gate()
                if boundary is False:
                    return self._cancelled(session, state.last_skill, messages)
                if isinstance(boundary, str) and boundary.strip():
                    user_message = boundary.strip()
                    messages.append({"role": "user", "content": user_message})
                    session.model_messages = list(messages)
                    session.add_message("user", user_message, intervention=True)
                    self.sessions.event(session, "intervention_applied", summary=user_message[:300])
                    self.sessions.save(session)

            tools = [] if state.answer_ready else base_tools
            system = self.prompts.system(session)
            if state.answer_ready:
                system += (
                    "\n\nThe latest successful tool result declares that enough evidence is available. "
                    "Answer the user's current request now from the supplied observation. Do not request, "
                    "read, or search for more material. "
                    + (state.completion_guidance or "")
                )
            messages = self.context.fit_to_budget(
                messages,
                summarizer=lambda older: self._summarize_older(older),
                fixed_context={"system": system, "tools": tools},
                reserve_tokens=self.config.context_output_reserve,
            )

            # Polite pause between turns so providers don't interpret
            # rapid successive calls as abuse.  The delay grows slightly
            # with turn count to naturally discourage runaway loops.
            import time as _time
            _time.sleep(min(2.0, turn * 0.15))

            with call_context(
                operation="agent_turn", parent_call_id=state.last_call_id,
                trigger_event_id=f"model-turn-{turn}",
            ):
                result = self.client.chat(
                    "agent_turn",
                    messages,
                    system=system,
                    tools=tools or None,
                    on_event=self.event_sink,
                )
            state.last_call_id = result.call_id or state.last_call_id
            if result.error == "cancelled":
                return self._cancelled(session, state.last_skill, messages)
            if result.error == "rate_limited" and self.rate_limit_gate:
                if self.rate_limit_gate(result.retry_after):
                    continue
                return self._cancelled(session, state.last_skill, messages)
            if not result.used_remote_model:
                if state.last_success:
                    return self._finish_with_fallback(session, state.last_success, state.last_skill, messages, result.error)
                return self._model_unavailable(session, result.outcome, result.error)

            assistant = result.assistant_message or {"role": "assistant", "content": result.text}
            messages.append(assistant)
            session.model_messages = list(messages)

            if not result.tool_calls:
                message = result.text.strip()
                if not message:
                    if state.last_success:
                        return self._finish_with_fallback(session, state.last_success, state.last_skill, messages, "empty_model_response")
                    return self._model_unavailable(session, result.outcome, result.error or "empty_model_response")
                if session.status == "planning":
                    return self._pause_for_plan_approval(session, message, messages, user_message, state)
                return self._finish(session, message, state.last_skill, messages)

            if session.status != "planning" and self._batch_requires_confirmation(result.tool_calls, state):
                return self._pause_for_tool_approval(session, result.tool_calls, messages, user_message, state)

            stopped = self._execute_calls(session, messages, result.tool_calls, user_message, state, turn=turn)
            if stopped:
                return stopped
            session.model_messages = list(messages)
            self.sessions.save(session)

    def _batch_requires_confirmation(self, raw_calls: list[dict[str, Any]], state: LoopState) -> bool:
        for raw_call in raw_calls:
            function = raw_call.get("function") if isinstance(raw_call.get("function"), dict) else {}
            arguments, error = self._arguments(function.get("arguments"))
            if error:
                continue
            try:
                spec = self.registry.resolve(str(function.get("name") or "").strip())
            except KeyError:
                continue
            call_key = f"{spec.name}:{json.dumps(arguments, ensure_ascii=False, sort_keys=True, default=str)}"
            if call_key in state.seen_calls:
                continue
            if self.executor.requires_confirmation(spec.name, arguments):
                return True
        return False

    def _execute_calls(
        self,
        session: ChatSession,
        messages: list[dict[str, Any]],
        raw_calls: list[dict[str, Any]],
        user_message: str,
        state: LoopState,
        *,
        turn: int = 0,
    ) -> AgentResult | None:
        if self.event_sink and raw_calls:
            self.event_sink(ProviderEvent("tool_batch_started", {"count": len(raw_calls), "turn": turn}))
        direct_messages: list[str] = []
        all_direct_delivery = bool(raw_calls)
        batch_seen: set[str] = set()
        for raw_call in raw_calls:
            call_id = str(raw_call.get("id") or f"tool-{turn or 1}")
            function = raw_call.get("function") if isinstance(raw_call.get("function"), dict) else {}
            requested_name = str(function.get("name") or "").strip()
            arguments, argument_error = self._arguments(function.get("arguments"))
            if argument_error:
                all_direct_delivery = False
                self._append_tool_message(messages, call_id, {"ok": False, "error": argument_error})
                continue
            try:
                spec = self.registry.resolve(requested_name)
            except KeyError:
                all_direct_delivery = False
                self._append_tool_message(messages, call_id, {"ok": False, "error": f"Unknown tool: {requested_name}"})
                continue
            if not spec.handler or not spec.planner_visible:
                all_direct_delivery = False
                self._append_tool_message(messages, call_id, {"ok": False, "error": f"Tool is not executable: {spec.name}"})
                continue
            if spec.batch_policy == "single" and spec.name in batch_seen:
                all_direct_delivery = False
                payload = {
                    "ok": False,
                    "tool": spec.name,
                    "error": "This tool accepts one call per assistant response. Reuse the completed observation or combine related inputs into one call.",
                    "error_code": "batch_policy",
                }
                self.sessions.event(
                    session, "tool_skipped", spec.name, payload["error"],
                    ok=False, error_code="batch_policy", turn=turn,
                )
                self._append_tool_message(messages, call_id, payload)
                continue
            batch_seen.add(spec.name)
            if not spec.direct_delivery:
                all_direct_delivery = False

            state.last_skill = spec.name
            call_key = f"{spec.name}:{json.dumps(arguments, ensure_ascii=False, sort_keys=True, default=str)}"
            if call_key in state.seen_calls:
                if call_key in state.rejected_repeats:
                    self._append_tool_message(messages, call_id, {
                        "ok": False, "tool": spec.name,
                        "error": "Repeated tool call stopped by the emergency loop guard.",
                    })
                    message = state.last_success or "模型连续请求相同工具且没有产生新信息，当前成果已保留。"
                    return self._finish(session, message, state.last_skill, messages)
                state.rejected_repeats.add(call_key)
                payload = {
                    "ok": False, "tool": spec.name,
                    "error": "This exact tool call already ran. Use its existing observation, change the arguments, or answer the user.",
                }
                self.sessions.event(session, "tool_observed", spec.name, payload["error"], ok=False, error_code="duplicate_tool_call", turn=turn)
                self._append_tool_message(messages, call_id, payload)
                all_direct_delivery = False
                continue
            state.seen_calls.add(call_key)

            tool_arguments = dict(arguments)
            tool_arguments.setdefault("request", user_message)
            if spec.network_access and tool_arguments.get("no_network") is True:
                all_direct_delivery = False
                payload = {"ok": False, "tool": spec.name, "error": "The user restricted this task to local evidence."}
                self.sessions.event(session, "tool_observed", spec.name, payload["error"], ok=False, turn=turn)
                self._append_tool_message(messages, call_id, payload)
                continue

            self.sessions.event(session, "tool_requested", spec.name, arguments=tool_arguments, turn=turn)
            self.sessions.event(session, "tool_started", spec.name, "tool execution started", turn=turn)
            if self.event_sink:
                self.event_sink(ProviderEvent("tool_started", {"tool": spec.name, "turn": turn}))
            if self.progress:
                self.progress("run", spec.name)
            try:
                with call_context(
                    parent_call_id=state.last_call_id,
                    trigger_event_id=f"tool:{call_id}",
                    operation=f"tool:{spec.name}",
                ):
                    tool_result = self.executor.execute(spec.name, tool_arguments, session)
            except KeyboardInterrupt:
                return self._cancelled(session, spec.name, messages)
            except ContractError as exc:
                all_direct_delivery = False
                payload = exc.as_observation(spec.name)
                self.sessions.event(session, "tool_observed", spec.name, str(exc), ok=False, outcome="failed", error_code=exc.code, turn=turn)
                if self.event_sink:
                    self.event_sink(ProviderEvent("tool_result", {
                        "tool": spec.name, "ok": False, "outcome": "failed", "message": str(exc),
                        "artifacts": {}, "turn": turn, "metrics": {},
                    }))
                if self.progress:
                    self.progress("failed", spec.name)
                self._append_tool_message(messages, call_id, payload)
                continue
            except Exception as exc:
                all_direct_delivery = False
                error = str(exc)
                code = getattr(exc, "code", None)
                outcome = "rate_limited" if code == 429 or self._is_rate_limit(error) else "failed"
                payload = {"ok": False, "outcome": outcome, "tool": spec.name, "error": error}
                self.sessions.event(session, "tool_observed", spec.name, error, ok=False, outcome=outcome, turn=turn)
                if self.event_sink:
                    self.event_sink(ProviderEvent("tool_result", {
                        "tool": spec.name, "ok": False, "outcome": outcome, "message": error,
                        "artifacts": {}, "turn": turn, "metrics": {},
                    }))
                if self.progress:
                    self.progress("failed", spec.name)
                self._append_tool_message(messages, call_id, payload)
                continue

            if self.cancel_event and self.cancel_event.is_set():
                return self._cancelled(session, spec.name, messages)
            session.artifacts.update({key: str(value) for key, value in tool_result.get("artifacts", {}).items()})
            register_artifacts(session, spec, tool_result.get("artifacts", {}))
            visible_artifacts = public_artifacts({
                key: session.artifact_records[key]
                for key in tool_result.get("artifacts", {})
                if key in session.artifact_records
            })
            for key in tool_result.get("artifacts", {}):
                session.artifact_dependencies[key] = [spec.name]
            session.metadata["last_skill"] = spec.name
            model_data = tool_result.get("model_data", tool_result.get("data", {}))
            outcome = str(tool_result.get("outcome") or "success")
            tool_ok = outcome in {"success", "partial"}
            if isinstance(model_data, dict) and model_data.get("answer_ready") is True:
                state.answer_ready = True
                state.completion_guidance = str(model_data.get("completion_guidance") or "").strip()
            full_observation = {
                "ok": tool_ok,
                "outcome": outcome,
                "tool": spec.name,
                "message": str(tool_result.get("message") or ""),
                "data": model_data,
                "artifacts": tool_result.get("artifacts", {}),
            }
            observation = self.context.observation(
                tool=spec.name, message=full_observation["message"], data=full_observation["data"],
                artifacts=full_observation["artifacts"], messages=messages,
                ok=tool_ok, outcome=outcome,
            )
            persistent_observation = {
                key: value for key, value in observation.items() if key != "data"
            }
            session.observations.append(persistent_observation)
            session.metadata["last_result"] = persistent_observation
            if tool_ok:
                state.last_success = full_observation["message"] or state.last_success
            if spec.direct_delivery and tool_ok and full_observation["message"]:
                direct_messages.append(full_observation["message"])
            progress = tool_result.get("progress") if isinstance(tool_result.get("progress"), dict) else {}
            public_message = str(progress.get("summary") or full_observation["message"] or "工具已返回结果")
            event_artifacts = visible_artifacts if outcome in {"success", "partial"} else {}
            self.sessions.event(
                session, "tool_observed", spec.name, public_message,
                artifacts=event_artifacts, ok=tool_ok, outcome=outcome,
                turn=turn, metrics=dict(progress.get("metrics") or {}),
            )
            if self.event_sink:
                self.event_sink(ProviderEvent("tool_result", {
                    "tool": spec.name, "ok": tool_ok, "outcome": outcome, "message": public_message,
                    "artifacts": event_artifacts, "turn": turn,
                    "metrics": dict(progress.get("metrics") or {}),
                }))
            if self.progress:
                self.progress("failed" if outcome in {"failed", "rate_limited"} else "done", spec.name)
            self._append_tool_message(messages, call_id, observation)
        if all_direct_delivery and direct_messages:
            return self._finish(session, "\n\n".join(direct_messages), state.last_skill, messages)
        return None

    @staticmethod
    def _is_rate_limit(error: str) -> bool:
        value = str(error or "").lower()
        return "429" in value or "too many" in value or "rate limit" in value or "rate_limited" in value

    def _pause_for_tool_approval(
        self,
        session: ChatSession,
        raw_calls: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        user_message: str,
        state: LoopState,
    ) -> AgentResult:
        details: list[str] = []
        names: list[str] = []
        for raw_call in raw_calls:
            function = raw_call.get("function") if isinstance(raw_call.get("function"), dict) else {}
            name = str(function.get("name") or "tool")
            arguments, _ = self._arguments(function.get("arguments"))
            names.append(name)
            visible = ", ".join(f"{key}={value}" for key, value in arguments.items() if key != "request")
            details.append(f"- {name}" + (f": {visible}" if visible else ""))
        message = "需要你的确认后才能执行：\n" + "\n".join(details) + "\n\n请选择 Accept 或 Reject。"
        session.status = "waiting_user"
        session.metadata["last_approval_message"] = message
        session.pending_action = {
            "type": "tool_approval",
            "skill": ", ".join(names),
            "tool_calls": raw_calls,
            "model_messages": messages,
            "user_message": user_message,
            "last_skill": state.last_skill,
            "last_success": state.last_success,
            "last_call_id": state.last_call_id,
            "summary": message,
        }
        session.model_messages = list(messages)
        session.add_message("assistant", message, waiting=True)
        self.sessions.event(session, "approval_requested", ", ".join(names), message)
        self.sessions.save(session)
        return AgentResult(message, ", ".join(names), waiting=True)

    def _pause_for_plan_approval(
        self,
        session: ChatSession,
        message: str,
        messages: list[dict[str, Any]],
        user_message: str,
        state: LoopState,
    ) -> AgentResult:
        session.status = "waiting_user"
        session.metadata["last_approval_message"] = message
        session.pending_action = {
            "type": "plan_approval",
            "model_messages": messages,
            "user_message": user_message,
            "last_skill": state.last_skill,
            "last_success": state.last_success,
            "last_call_id": state.last_call_id,
            "summary": "Plan 已完成。是否执行？",
        }
        session.model_messages = list(messages)
        session.add_message("assistant", message, skill=state.last_skill, waiting=True)
        self.sessions.event(session, "approval_requested", summary="Plan 已完成。是否执行？", approval_type="plan")
        self.sessions.save(session)
        return AgentResult(message, state.last_skill, waiting=True)

    def _conversation(self, session: ChatSession, user_message: str) -> list[dict[str, Any]]:
        if session.model_messages:
            messages = [dict(item) for item in session.model_messages]
        else:
            messages = [
                {"role": item["role"], "content": str(item.get("content") or "")}
                for item in session.messages
                if item.get("role") in {"user", "assistant"}
            ]
        # Purge orphan tool_calls: walk back to find the most recent
        # assistant with tool_calls, keep only calls with a matching
        # tool result already appended.
        seen: set[str] = set()
        for msg in reversed(messages):
            if msg.get("role") == "tool":
                seen.add(str(msg.get("tool_call_id") or ""))
            elif msg.get("role") == "assistant" and msg.get("tool_calls"):
                surviving = [tc for tc in msg["tool_calls"] if str(tc.get("id") or "") in seen]
                if surviving:
                    msg["tool_calls"] = surviving
                else:
                    msg.pop("tool_calls", None)
                    if not msg.get("content"):
                        msg["content"] = "（操作已取消）"
                break
        runtime_context = self.prompts.runtime_context(session)
        model_user_message = user_message
        if runtime_context:
            model_user_message += f"\n\n<runtime_context>\n{runtime_context}\n</runtime_context>"
        if not messages or messages[-1].get("role") != "user" or messages[-1].get("content") != model_user_message:
            messages.append({"role": "user", "content": model_user_message})
        session.model_messages = list(messages)
        return messages

    def _summarize_older(self, messages: list[dict[str, Any]]) -> str:
        """Summarize older conversation turns into a compact paragraph.

        Uses a minimal, non-streaming LLM call.  On failure, degrades to
        a structural summary so the harness never blocks.
        """
        transcript = self.context.fit_text(
            json.dumps(messages, ensure_ascii=False, default=str),
            label="context-summary-input",
            reserve_tokens=self.config.context_output_reserve,
        )
        try:
            result = self.client.complete(
                "context_summary",
                f"Summarize these earlier conversation turns in Chinese. "
                f"Keep: user goals, tool names called, key findings, and decisions made. "
                f"Discard: raw data, error traces, redundant details.\n\n{transcript}",
                fallback="",
                system="Reply with only the summary paragraph. No preamble.",
                temperature=0,
            )
            if result.used_remote_model and result.text.strip():
                return result.text.strip()
        except Exception:
            pass
        roles = [m.get("role", "?") for m in messages]
        tools = list(dict.fromkeys(
            (json.loads(m.get("content", "{}")).get("tool", "") if isinstance(m.get("content"), str) else "")
            for m in messages if m.get("role") == "tool"
        ))
        return f"Earlier: {len(messages)} messages ({roles.count('user')} user turns, tools: {', '.join(t for t in tools if t) or 'none'})."

    @staticmethod
    def _arguments(raw: Any) -> tuple[dict[str, Any], str]:
        if raw in (None, ""):
            return {}, ""
        if isinstance(raw, dict):
            return raw, ""
        if not isinstance(raw, str):
            return {}, "Tool arguments must be a JSON object."
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            return {}, f"Invalid tool arguments: {exc}"
        return (value, "") if isinstance(value, dict) else ({}, "Tool arguments must be a JSON object.")

    def _append_tool_message(self, messages: list[dict[str, Any]], call_id: str, payload: dict[str, Any]) -> None:
        payload = self.context.tool_payload(payload, messages=messages)
        messages.append({
            "role": "tool",
            "tool_call_id": call_id,
            "content": json.dumps(payload, ensure_ascii=False, default=str),
        })

    def _finish(self, session: ChatSession, message: str, skill: str, model_messages: list[dict[str, Any]]) -> AgentResult:
        if not model_messages or model_messages[-1].get("role") != "assistant" or model_messages[-1].get("content") != message:
            model_messages.append({"role": "assistant", "content": message})
        # Strip raw data from tool results before persisting to context.
        # The full result is on disk (tool_observations/); the model only
        # needs the summary across turn boundaries.
        for msg in model_messages:
            if msg.get("role") == "tool":
                try:
                    payload = json.loads(msg.get("content", "{}"))
                    if isinstance(payload, dict) and "data" in payload:
                        payload.pop("data", None)
                        msg["content"] = json.dumps(payload, ensure_ascii=False, default=str)
                except (json.JSONDecodeError, TypeError):
                    pass
        session.model_messages = list(model_messages)
        session.status = "active"
        session.pending_action = None
        session.add_message("assistant", message, skill=skill)
        self.sessions.event(session, "finished", skill, message)
        self.sessions.save(session)
        return AgentResult(message, skill)

    def _finish_with_fallback(self, session: ChatSession, message: str, skill: str, model_messages: list[dict[str, Any]], model_error: str) -> AgentResult:
        session.metadata["last_model_error"] = model_error
        self.sessions.event(session, "model_followup_failed", skill, "Returning the verified tool result because the model follow-up failed.", error=model_error)
        return self._finish(session, message, skill, model_messages)

    def _cancelled(self, session: ChatSession, skill: str, model_messages: list[dict[str, Any]]) -> AgentResult:
        message = "已取消当前步骤；已完成成果和会话状态已保存，源文件没有被删除或覆盖。"
        session.model_messages = list(model_messages)
        # An assistant message with pending tool_calls must be followed
        # by a matching tool result for every call before the next user
        # turn, otherwise the provider rejects the request (HTTP 400).
        # Walk backwards to find the most recent assistant message that
        # owns tool_calls, then strip only orphan calls (those without
        # a tool result already appended).
        seen_results: set[str] = set()
        for msg in reversed(session.model_messages):
            if msg.get("role") == "tool":
                seen_results.add(str(msg.get("tool_call_id") or ""))
            elif msg.get("role") == "assistant" and msg.get("tool_calls"):
                surviving = []
                for tc in msg["tool_calls"]:
                    if str(tc.get("id") or "") in seen_results:
                        surviving.append(tc)
                if surviving:
                    msg["tool_calls"] = surviving
                else:
                    msg.pop("tool_calls", None)
                    if not msg.get("content"):
                        msg["content"] = "（操作已取消）"
                break  # only sanitize the most recent assistant with tool_calls
        session.status = "waiting_user"
        session.pending_action = {"type": "cancelled", "tool": skill}
        session.add_message("assistant", message, skill=skill, cancelled=True)
        self.sessions.event(session, "cancelled", skill, message)
        self.sessions.save(session)
        return AgentResult(message, skill, waiting=True)

    def _model_unavailable(self, session: ChatSession, outcome: str = "", error: str = "") -> AgentResult:
        if outcome in {"reasoning_incomplete", "output_exhausted"}:
            message = "模型尚未生成最终回答；本轮没有执行新的工具，已有成果仍然保留。"
            session.status = "waiting_user"
            session.pending_action = {"type": "retry_current_request", "outcome": outcome}
        else:
            message = "模型服务当前不可用；本轮没有执行新的工具，已有成果仍然保留。"
        if error:
            session.metadata["last_model_error"] = error
        session.add_message("assistant", message, error=True)
        self.sessions.event(session, "failed", summary=message, error=error, outcome=outcome)
        self.sessions.save(session)
        return AgentResult(message, waiting=session.status == "waiting_user")
