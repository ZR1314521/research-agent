from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from research_agent.provider_runtime import ProviderEvent, call_context, provider_event_sink


TERMINAL_STATES = {"completed", "failed", "cancelled"}


class ActiveTurnError(RuntimeError):
    def __init__(self, turn_id: str):
        super().__init__(f"Run already has an active turn: {turn_id}")
        self.turn_id = turn_id


@dataclass
class TurnControl:
    run_id: str
    run_dir: Path
    turn_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    state: str = "idle"
    cancel_event: threading.Event = field(default_factory=threading.Event)
    events: list[dict[str, Any]] = field(default_factory=list)
    final_payload: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        self._condition = threading.Condition()
        self._pause_requested = False
        self._approval: bool | None = None
        self._rate_limit_count = 0
        self._event_path = self.run_dir / f"turn_{self.turn_id}.jsonl"

    def emit(self, event: ProviderEvent | str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        kind, payload = (event.kind, dict(event.data)) if isinstance(event, ProviderEvent) else (event, dict(data or {}))
        with self._condition:
            item = {
                "sequence": len(self.events) + 1,
                "turn_id": self.turn_id,
                "run_id": self.run_id,
                "event": kind,
                "timestamp": time.time(),
                **payload,
            }
            self.events.append(item)
            self._event_path.parent.mkdir(parents=True, exist_ok=True)
            with self._event_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
            self._condition.notify_all()
            return item

    def request_pause(self) -> str:
        with self._condition:
            if self.state != "running":
                return self.state
            self._pause_requested = True
            self.state = "pause_requested"
            self.emit("pause_requested")
            return self.state

    def safe_boundary(self) -> bool:
        """Block only between provider/tool operations; never restart completed work."""
        with self._condition:
            if not self._pause_requested:
                return not self.cancel_event.is_set()
            self.state = "paused"
            self.emit("turn_paused")
            while self._pause_requested and not self.cancel_event.is_set():
                self._condition.wait(timeout=1.0)
            return not self.cancel_event.is_set()

    def resume(self) -> str:
        with self._condition:
            if self.state not in {"paused", "pause_requested", "rate_limited"}:
                return self.state
            self._pause_requested = False
            self.state = "running"
            self.emit("turn_resumed")
            self._condition.notify_all()
            return self.state

    def handle_rate_limit(self, retry_after: float | None) -> bool:
        with self._condition:
            self._rate_limit_count += 1
            self.state = "rate_limited"
            self.emit("rate_limited", {"retry_after": retry_after, "count": self._rate_limit_count})
            # Only the first response with an explicit provider delay resumes
            # automatically. Repeated limits and missing headers wait for the
            # user's Resume instead of inventing a local sleep value.
            if retry_after is not None and self._rate_limit_count == 1:
                deadline = time.monotonic() + retry_after
                while not self.cancel_event.is_set():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        self.state = "running"
                        self.emit("turn_resumed", {"source": "retry_after"})
                        return True
                    self._condition.wait(timeout=min(remaining, 1.0))
                return False
            self._pause_requested = True
        return self.safe_boundary()

    def wait_for_approval(self) -> bool | None:
        with self._condition:
            self.state = "waiting_approval"
            self.emit("approval_required")
            while self._approval is None and not self.cancel_event.is_set():
                self._condition.wait(timeout=1.0)
            decision = self._approval
            self._approval = None
            if not self.cancel_event.is_set():
                self.state = "running"
            return decision

    def resolve_approval(self, approved: bool) -> str:
        with self._condition:
            if self.state != "waiting_approval":
                return self.state
            self._approval = approved
            self.emit("approval_resolved", {"approved": approved})
            self._condition.notify_all()
            return self.state

    def cancel(self) -> str:
        with self._condition:
            if self.state in TERMINAL_STATES:
                return self.state
            self.cancel_event.set()
            self._pause_requested = False
            self.state = "cancelled"
            self.emit("turn_cancelled")
            self._condition.notify_all()
            return self.state

    def finish(self, state: str, payload: dict[str, Any]) -> None:
        with self._condition:
            self.state = state
            self.final_payload = payload
            self.emit("turn_finished" if state == "completed" else "turn_failed", payload)
            self._condition.notify_all()

    def stream(self, after: int = 0) -> Iterator[dict[str, Any]]:
        cursor = max(0, after)
        while True:
            heartbeat = False
            with self._condition:
                while cursor >= len(self.events) and self.state not in TERMINAL_STATES:
                    self._condition.wait(timeout=10.0)
                    if cursor >= len(self.events) and self.state not in TERMINAL_STATES:
                        heartbeat = True
                        break
                pending = self.events[cursor:]
                terminal = self.state in TERMINAL_STATES
            if heartbeat:
                yield {"event": "heartbeat", "turn_id": self.turn_id, "sequence": cursor}
            for item in pending:
                cursor = max(cursor, int(item["sequence"]))
                yield item
            if terminal and cursor >= len(self.events):
                return

    def wait_for_result_boundary(self) -> str:
        with self._condition:
            while self.state not in TERMINAL_STATES | {"waiting_approval", "paused", "rate_limited"}:
                self._condition.wait(timeout=1.0)
            return self.state


class TurnCoordinator:
    """One logical turn per run with resumable local event streaming."""

    def __init__(self, agent: Any):
        self.agent = agent
        self._lock = threading.Lock()
        self._active: dict[str, TurnControl] = {}
        self._turns: dict[str, TurnControl] = {}

    def start(self, run_id: str, message: str) -> TurnControl:
        with self._lock:
            active = self._active.get(run_id)
            if active and active.state not in TERMINAL_STATES:
                raise ActiveTurnError(active.turn_id)
            control = TurnControl(run_id, self.agent.sessions.directory(run_id))
            self._active[run_id] = control
            self._turns[control.turn_id] = control
        thread = threading.Thread(target=self._run, args=(control, message), daemon=True)
        thread.start()
        return control

    def _run(self, control: TurnControl, message: str) -> None:
        control.state = "running"
        control.emit("turn_started")
        try:
            session = self.agent.sessions.load(control.run_id)
            with call_context(turn_id=control.turn_id, operation="agent_turn"), provider_event_sink(control.emit):
                response = self.agent.handle(
                    session,
                    message,
                    cancel_event=control.cancel_event,
                    event_sink=control.emit,
                    pause_gate=control.safe_boundary,
                    rate_limit_gate=control.handle_rate_limit,
                )
                while response.session.pending_action and not control.cancel_event.is_set():
                    decision = control.wait_for_approval()
                    if decision is None:
                        break
                    response = self.agent.resolve_pending(
                        response.session,
                        decision,
                        cancel_event=control.cancel_event,
                        event_sink=control.emit,
                        pause_gate=control.safe_boundary,
                        rate_limit_gate=control.handle_rate_limit,
                    )
            if control.cancel_event.is_set():
                if control.state != "cancelled":
                    control.cancel()
                return
            context_size = 0
            provider_log = control.run_dir / "provider_calls.jsonl"
            if provider_log.exists():
                for line in provider_log.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if not line.strip(): continue
                    try:
                        call = json.loads(line)
                        prompt = call.get("usage", {}).get("prompt_tokens", 0)
                        if prompt:
                            context_size = prompt
                    except Exception: pass
            payload = {
                "assistant_message": response.message,
                "skill": response.skill,
                "status": response.session.status,
                "artifacts": response.session.artifact_records,
                "pending_action": response.session.pending_action,
                "context_size": context_size,
            }
            self.agent.sessions.event(
                response.session, "assistant_message", response.skill, response.message[:300]
            )
            control.finish("completed", payload)
        except Exception as error:
            control.finish("failed", {"error": f"{type(error).__name__}: {error}"})
        finally:
            with self._lock:
                if self._active.get(control.run_id) is control and control.state in TERMINAL_STATES:
                    self._active.pop(control.run_id, None)

    def active(self, run_id: str) -> TurnControl | None:
        with self._lock:
            control = self._active.get(run_id)
            return control if control and control.state not in TERMINAL_STATES else None

    def get(self, turn_id: str) -> TurnControl:
        with self._lock:
            try:
                return self._turns[turn_id]
            except KeyError as error:
                raise KeyError(turn_id) from error

    def pause(self, run_id: str) -> str:
        control = self.active(run_id)
        return control.request_pause() if control else "idle"

    def resume(self, run_id: str) -> str:
        control = self.active(run_id)
        return control.resume() if control else "idle"

    def approve(self, run_id: str, approved: bool) -> str:
        control = self.active(run_id)
        return control.resolve_approval(approved) if control else "idle"

    def cancel(self, run_id: str) -> str:
        control = self.active(run_id)
        return control.cancel() if control else "idle"
