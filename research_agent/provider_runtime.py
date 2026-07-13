from __future__ import annotations

import json
import threading
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator


@dataclass(frozen=True)
class CallContext:
    """Open causal metadata for one provider call.

    ``operation`` and ``trigger_event_id`` are descriptive values, not a
    closed routing enum.  The runtime records them but never uses them to
    decide whether a request is allowed.
    """

    turn_id: str = ""
    parent_call_id: str = ""
    trigger_event_id: str = ""
    operation: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)


_CALL_CONTEXT: ContextVar[CallContext] = ContextVar("research_agent_call_context", default=CallContext())
_EVENT_SINK: ContextVar[Callable[["ProviderEvent"], None] | None] = ContextVar(
    "research_agent_provider_event_sink", default=None
)


def current_call_context() -> CallContext:
    return _CALL_CONTEXT.get()


def current_event_sink() -> Callable[["ProviderEvent"], None] | None:
    return _EVENT_SINK.get()


@contextmanager
def call_context(**values: Any) -> Iterator[CallContext]:
    current = current_call_context()
    merged = CallContext(
        turn_id=str(values.get("turn_id", current.turn_id) or ""),
        parent_call_id=str(values.get("parent_call_id", current.parent_call_id) or ""),
        trigger_event_id=str(values.get("trigger_event_id", current.trigger_event_id) or ""),
        operation=str(values.get("operation", current.operation) or ""),
        attributes={**current.attributes, **dict(values.get("attributes") or {})},
    )
    token = _CALL_CONTEXT.set(merged)
    try:
        yield merged
    finally:
        _CALL_CONTEXT.reset(token)


@contextmanager
def provider_event_sink(sink: Callable[["ProviderEvent"], None] | None) -> Iterator[None]:
    token = _EVENT_SINK.set(sink)
    try:
        yield
    finally:
        _EVENT_SINK.reset(token)


@dataclass
class ProviderCall:
    call_id: str
    turn_id: str
    parent_call_id: str
    trigger_event_id: str
    operation: str
    attempt: int
    provider: str
    model: str
    started_at: float
    finished_at: float = 0.0
    status: str = "running"
    error: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class CallLedger:
    """Append-only provider audit. It never calls a model or affects routing."""

    def __init__(self, run_dir: Path):
        self.path = Path(run_dir) / "provider_calls.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def begin(self, provider: str, model: str, operation: str, attempt: int) -> ProviderCall:
        context = current_call_context()
        return ProviderCall(
            call_id=uuid.uuid4().hex,
            turn_id=context.turn_id,
            parent_call_id=context.parent_call_id,
            trigger_event_id=context.trigger_event_id,
            operation=operation or context.operation,
            attempt=attempt,
            provider=provider,
            model=model,
            started_at=time.time(),
            metadata=dict(context.attributes),
        )

    def finish(
        self,
        call: ProviderCall,
        status: str,
        *,
        error: str = "",
        usage: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProviderCall:
        call.finished_at = time.time()
        call.status = status
        call.error = error
        call.usage = dict(usage or {})
        call.metadata.update(metadata or {})
        record = asdict(call)
        record["duration_ms"] = max(0, round((call.finished_at - call.started_at) * 1000))
        with self._lock, self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return call

    def records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        result: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                result.append(item)
        return result


@dataclass(frozen=True)
class ProviderEvent:
    kind: str
    data: dict[str, Any] = field(default_factory=dict)


class RateLimitError(RuntimeError):
    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after
