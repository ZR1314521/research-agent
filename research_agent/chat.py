from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Any
from threading import Event, Thread

from research_agent.acceptance import UserOutcomeObserver
from research_agent.config import AgentConfig
from research_agent.core.agent import AgentLoop
from research_agent.executor import ToolExecutor
from research_agent.logging import ModelCallLogger
from research_agent.session import ChatSession, SessionStore
from research_agent.skill_registry import SkillRegistry
from research_agent.tools.llm_client import ModelGateway
from research_agent.provider_runtime import CallLedger
from research_agent.version import RUNTIME_VERSION


Progress = Callable[[str, str], None]


@dataclass
class ChatResponse:
    message: str
    session: ChatSession
    skill: str = ""


class ResearchChatAgent:
    def __init__(self, config: AgentConfig | None = None):
        self.config = config or AgentConfig.load()
        self.config.runs_dir.mkdir(parents=True, exist_ok=True)
        self.registry = SkillRegistry(self.config.skills_dir)
        self.sessions = SessionStore(self.config.runs_dir)
        self.outcomes = UserOutcomeObserver(self.config.root_dir / "quality_reports", self.registry)

    def close(self) -> None:
        self.sessions.close()

    def new_session(self) -> ChatSession:
        return self.sessions.create()

    def load_or_create(self, session_id: str = "", resume_latest: bool = True) -> ChatSession:
        if session_id:
            return self.sessions.load(session_id)
        return self.sessions.latest() if resume_latest and self.sessions.latest() else self.new_session()

    def handle(
        self,
        session: ChatSession,
        text: str,
        progress: Progress | None = None,
        cancel_event: Event | None = None,
        event_sink: Callable[[Any], Any] | None = None,
        pause_gate: Callable[[], bool | str] | None = None,
        rate_limit_gate: Callable[[float | None], bool] | None = None,
    ) -> ChatResponse:
        text = text.strip()
        if not text:
            return ChatResponse("请输入科研任务。", session)
        pending_approval = (session.pending_action or {}).get("type") in {"tool_approval", "plan_approval"}
        if (session.pending_action or {}).get("type") == "cancelled":
            session.pending_action = None
            session.status = "active"
        if text.startswith("/"):
            command = text.partition(" ")[0].lower()
            if pending_approval and command not in {"/approve", "/reject", "/status"}:
                return ChatResponse("当前有操作等待确认，请先选择 Accept 或 Reject。", session)
            return self._command(session, text)
        if pending_approval:
            return ChatResponse("当前有操作等待确认，请先选择 Accept 或 Reject。", session)
        if session.runtime_version != RUNTIME_VERSION:
            session.metadata["runtime_notice"] = "This session was created by an older runtime; restart the terminal before trusting new tool contracts."
            self.sessions.event(session, "runtime_mismatch", summary=session.metadata["runtime_notice"])
        first_event = len(session.events)
        session.add_message("user", text)
        self.sessions.save(session)
        if not self.config.llm_configured:
            message = "模型尚未配置，当前不会用本地关键词规则假装理解任务。请先配置模型连接后重试。"
            session.add_message("assistant", message, error=True)
            self.sessions.event(session, "failed", summary=message, error="model_not_configured")
            self.sessions.save(session)
            response = ChatResponse(message, session)
            self._observe(response, text, first_event)
            return response
        result = AgentLoop(
            self.config, self.registry, self.sessions, self.sessions.directory(session.session_id),
            progress=progress, cancel_event=cancel_event, event_sink=event_sink,
            pause_gate=pause_gate, rate_limit_gate=rate_limit_gate,
        ).run(session, text)
        response = ChatResponse(result.message, session, result.skill)
        self._observe(response, text, first_event)
        return response

    def _observe(self, response: ChatResponse, user_message: str, first_event: int) -> None:
        try:
            record = self.outcomes.record(
                response.session,
                user_message,
                response.message,
                response.session.events[first_event:],
                waiting=bool(response.session.pending_action),
                provider_calls=CallLedger(self.sessions.directory(response.session.session_id)).records(),
            )
            response.session.metadata["outcome_report"] = str(self.outcomes.report_path)
            response.session.metadata["last_outcome_status"] = record["status"]
            self.sessions.save(response.session)
        except Exception as error:
            # Acceptance is deliberately out-of-band and must never break a user turn.
            response.session.metadata["outcome_observer_error"] = f"{type(error).__name__}: {error}"
            self.sessions.save(response.session)

    def resolve_pending(
        self,
        session: ChatSession,
        approved: bool,
        progress: Progress | None = None,
        cancel_event: Event | None = None,
        event_sink: Callable[[Any], Any] | None = None,
        pause_gate: Callable[[], bool | str] | None = None,
        rate_limit_gate: Callable[[float | None], bool] | None = None,
    ) -> ChatResponse:
        result = AgentLoop(
            self.config,
            self.registry,
            self.sessions,
            self.sessions.directory(session.session_id),
            progress=progress,
            cancel_event=cancel_event,
            event_sink=event_sink,
            pause_gate=pause_gate,
            rate_limit_gate=rate_limit_gate,
        ).resume(session, approved)
        return ChatResponse(result.message, session, result.skill)

    def _command(self, session: ChatSession, text: str) -> ChatResponse:
        command, _, _argument = text.partition(" ")
        command = command.lower()
        if command == "/help":
            message = "直接输入自然语言任务。命令：/skills /status /pause /resume /reset /new /model /model-test /exit /plan /approve /reject"
        elif command == "/plan":
            if session.metadata.get("plan_mode"):
                session.metadata.pop("plan_mode", None)
                session.status = "active"
                message = "已退出规划模式。"
            else:
                session.metadata["plan_mode"] = True
                session.status = "planning"
                message = "已进入只读规划模式。模型可以搜索和读取，但不能写文件或下载；再次输入 /plan 即可退出。"
        elif command == "/approve":
            return self.resolve_pending(session, True)
        elif command == "/reject":
            return self.resolve_pending(session, False)
        elif command == "/skills":
            message = "\n".join(f"- {item.name} [{item.kind}]" for item in self.registry.all())
        elif command == "/status":
            message = ToolExecutor(self.config, self.registry, self.sessions.directory(session.session_id)).status(session)["message"]
        elif command == "/pause":
            session.status, message = "paused", "会话已暂停并保存。"
            self.sessions.event(session, "paused", summary="user paused session")
        elif command == "/resume":
            session.status, message = "active", "会话已恢复。"
            self.sessions.event(session, "resumed", summary="user resumed session")
        elif command == "/reset":
            self.sessions.reset_context(session)
            message = "上下文已清空；会话目录内的文件仍保留，但不再作为当前上下文使用。"
        elif command == "/new":
            session = self.new_session()
            message = f"新会话：{session.session_id}"
        elif command == "/model":
            message = f"provider={self.config.llm_provider}\nmodel={self.config.llm_model}\nbase_url={self.config.llm_base_url}\nconfigured={self.config.llm_configured}"
        elif command == "/model-test":
            message = str(ModelGateway(self.config, ModelCallLogger(self.sessions.directory(session.session_id))).health())
        elif command == "/exit":
            message = "会话已保存。"
        else:
            message = f"未知命令：{command}"
        self.sessions.save(session)
        return ChatResponse(message, session)


def _run_with_esc(agent: ResearchChatAgent, session: ChatSession, text: str) -> ChatResponse:
    """Use Windows' console reader to request cancellation without new dependencies."""
    response_box: list[ChatResponse] = []
    cancel_event = Event()
    worker = Thread(
        target=lambda: response_box.append(
            agent.handle(session, text, progress=lambda event, skill: print(f"[{event}] {skill}", flush=True), cancel_event=cancel_event)
        ),
        daemon=True,
    )
    worker.start()
    try:
        import msvcrt
        announced = False
        while worker.is_alive():
            if msvcrt.kbhit() and msvcrt.getwch() == "\x1b":
                cancel_event.set()
                if not announced:
                    print("\n[Esc received: cancelling current step…]", flush=True)
                    announced = True
            worker.join(0.05)
    except KeyboardInterrupt:
        cancel_event.set()
        print("\n[cancelling current step…]", flush=True)
        worker.join()
    return response_box[0] if response_box else ChatResponse("Current step cancelled; session saved.", session)


def _run_terminal_with_agent(agent: ResearchChatAgent, session_id: str = "", resume_latest: bool = True) -> None:
    session = agent.load_or_create(session_id, resume_latest=resume_latest)
    print("AI Research Agent", flush=True)
    print(f"session: {session.session_id}\nmodel: {agent.config.llm_provider}/{agent.config.llm_model}\nruntime: {RUNTIME_VERSION}", flush=True)
    while True:
        try:
            text = input("\nResearch> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n会话已保存。", flush=True)
            break
        if not text:
            continue
        try:
            response = _run_with_esc(agent, session, text)
        except KeyboardInterrupt:
            print("\n已取消当前请求；会话已保存。", flush=True)
            continue
        session = response.session
        print(f"\nAgent> {response.message}", flush=True)
        if text.lower() == "/exit":
            break


def run_terminal(config: AgentConfig | None = None, session_id: str = "", resume_latest: bool = True) -> None:
    agent = ResearchChatAgent(config)
    try:
        _run_terminal_with_agent(agent, session_id, resume_latest)
    finally:
        agent.close()
