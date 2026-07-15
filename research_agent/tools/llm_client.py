from __future__ import annotations

import http.client
import json
import threading
import time as _time
import urllib.error
import urllib.request
from dataclasses import dataclass
from threading import Event
from typing import Any, Callable, Iterable, Protocol

from research_agent.config import AgentConfig
from research_agent.logging import ModelCallLogger
from research_agent.provider_runtime import CallLedger, ProviderEvent, current_event_sink


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    used_remote_model: bool
    error: str = ""
    operation: str = ""
    attempts: int = 0
    outcome: str = ""
    tool_calls: list[dict[str, Any]] | None = None
    assistant_message: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None
    retry_after: float | None = None
    call_id: str = ""


@dataclass(frozen=True)
class NormalizedResponse:
    text: str
    outcome: str
    finish_reason: str
    content_chars: int
    reasoning_chars: int
    tool_call_count: int

    def metadata(self) -> dict[str, object]:
        return {
            "outcome": self.outcome,
            "finish_reason": self.finish_reason,
            "content_chars": self.content_chars,
            "reasoning_chars": self.reasoning_chars,
            "tool_call_count": self.tool_call_count,
        }


def _message_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "".join(
            item.get("text", "") for item in value if isinstance(item, dict) and isinstance(item.get("text"), str)
        ).strip()
    return ""


def _response_text_length(value: Any) -> int:
    if isinstance(value, str):
        return len(value)
    if isinstance(value, list):
        return sum(len(item.get("text", "")) for item in value if isinstance(item, dict) and isinstance(item.get("text"), str))
    return 0


def _normalize_response(data: Any) -> NormalizedResponse:
    choices = data.get("choices") if isinstance(data, dict) else None
    choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    content = message.get("content")
    reasoning = message.get("reasoning_content")
    tool_calls = message.get("tool_calls")
    tool_call_count = len(tool_calls) if isinstance(tool_calls, list) else int(bool(tool_calls))
    finish_reason = choice.get("finish_reason") if isinstance(choice.get("finish_reason"), str) else ""
    text = _message_text(content)
    if tool_call_count:
        outcome = "native_tool_call"
    elif text:
        outcome = "text"
    elif finish_reason == "length":
        outcome = "output_exhausted"
    elif _response_text_length(reasoning):
        outcome = "reasoning_incomplete"
    else:
        outcome = "empty_model_response"
    return NormalizedResponse(
        text=text,
        outcome=outcome,
        finish_reason=finish_reason,
        content_chars=_response_text_length(content),
        reasoning_chars=_response_text_length(reasoning),
        tool_call_count=tool_call_count,
    )


EventSink = Callable[[ProviderEvent], None]


class ProviderAdapter(Protocol):
    def request(
        self,
        body: dict[str, Any],
        *,
        timeout: int,
        on_event: EventSink | None = None,
    ) -> dict[str, Any]: ...


class OpenAICompatibleProvider:
    """OpenAI-compatible wire adapter.

    Provider-specific streaming fragments are normalized here.  The agent
    loop only receives open ``ProviderEvent`` objects and a normal assistant
    message.
    """

    def __init__(self, base_url: str, api_key: str, semaphore: threading.BoundedSemaphore):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.semaphore = semaphore

    def request(
        self,
        body: dict[str, Any],
        *,
        timeout: int,
        on_event: EventSink | None = None,
    ) -> dict[str, Any]:
        payload = dict(body)
        if on_event is not None:
            payload["stream"] = True
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with self.semaphore:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if on_event is not None:
                    return self._read_stream_lines(response, on_event)
                raw = response.read()
                text = raw.decode("utf-8", errors="replace")
                # Cloudflare / reverse-proxy challenge pages are HTML, not
                # JSON.  Surface a clear error rather than letting the model
                # echo raw markup.
                if text.lstrip().startswith("<!") or text.lstrip().startswith("<html"):
                    raise ValueError("Provider returned HTML (likely a challenge page or proxy block)")
                return json.loads(text)

    @staticmethod
    def _read_stream_lines(lines: Iterable[str | bytes], on_event: EventSink) -> dict[str, Any]:
        content: list[str] = []
        reasoning: list[str] = []
        calls: dict[int, dict[str, Any]] = {}
        finish_reason = ""
        usage: dict[str, Any] = {}
        for raw in lines:
            line = raw.decode("utf-8", errors="replace").strip() if isinstance(raw, bytes) else str(raw).strip()
            if line.lstrip().lower().startswith(("<!", "<html")):
                raise ValueError("Provider returned HTML (likely a challenge page or proxy block)")
            if not line or line.startswith(":") or not line.startswith("data:"):
                continue
            value = line[5:].strip()
            if value == "[DONE]":
                break
            try:
                chunk = json.loads(value)
            except json.JSONDecodeError:
                on_event(ProviderEvent("provider_event", {"raw": value}))
                continue
            if isinstance(chunk.get("usage"), dict):
                usage = dict(chunk["usage"])
            choices = chunk.get("choices") if isinstance(chunk, dict) else None
            choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
            delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
            if isinstance(choice.get("finish_reason"), str):
                finish_reason = choice["finish_reason"]
            text = delta.get("content")
            if isinstance(text, str) and text:
                content.append(text)
                on_event(ProviderEvent("assistant_delta", {"text": text}))
            thought = delta.get("reasoning_content")
            if isinstance(thought, str) and thought:
                reasoning.append(thought)
                on_event(ProviderEvent("reasoning_delta", {"text": thought}))
            fragments = delta.get("tool_calls")
            if isinstance(fragments, list):
                for fragment in fragments:
                    if not isinstance(fragment, dict):
                        continue
                    index = int(fragment.get("index") or 0)
                    call = calls.setdefault(index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                    if fragment.get("id"):
                        call["id"] = str(fragment["id"])
                    function = fragment.get("function") if isinstance(fragment.get("function"), dict) else {}
                    if function.get("name"):
                        call["function"]["name"] += str(function["name"])
                    if function.get("arguments"):
                        call["function"]["arguments"] += str(function["arguments"])
                    on_event(ProviderEvent("tool_call_delta", {"index": index, "fragment": fragment}))
        message: dict[str, Any] = {"role": "assistant", "content": "".join(content) or None}
        if reasoning:
            message["reasoning_content"] = "".join(reasoning)
        if calls:
            message["tool_calls"] = [calls[index] for index in sorted(calls)]
        return {"choices": [{"finish_reason": finish_reason, "message": message}], "usage": usage}


class ModelGateway:
    """The only provider boundary used by the runtime."""

    _semaphore_lock = threading.Lock()
    _semaphores: dict[tuple[str, int], threading.BoundedSemaphore] = {}

    def __init__(self, config: AgentConfig, logger: ModelCallLogger, cancel_event: Event | None = None):
        self.config = config
        self.logger = logger
        self.cancel_event = cancel_event
        protocol = config.llm_protocol.strip().lower().replace("_", "-")
        if protocol not in {"openai-compatible", "openai"}:
            raise ValueError(f"Unsupported model protocol: {config.llm_protocol}")
        key = (config.llm_base_url.rstrip("/"), config.provider_max_concurrency)
        with self._semaphore_lock:
            semaphore = self._semaphores.setdefault(key, threading.BoundedSemaphore(config.provider_max_concurrency))
        self.adapter: ProviderAdapter = OpenAICompatibleProvider(config.llm_base_url, config.llm_api_key, semaphore)
        self.ledger = CallLedger(logger.path.parent)

    @staticmethod
    def _retry_after(error: urllib.error.HTTPError) -> float | None:
        if error.code != 429:
            return None
        raw = error.headers.get("Retry-After") if error.headers else None
        try:
            return max(0.0, float(raw)) if raw is not None else None
        except (TypeError, ValueError):
            return None

    def _perform(
        self,
        operation: str,
        body: dict[str, Any],
        *,
        timeout: int,
        prompt_for_log: str,
        on_event: EventSink | None,
    ) -> tuple[dict[str, Any] | None, int, str, float | None, str]:
        sink = on_event or current_event_sink()
        attempts = 1 + max(0, self.config.llm_retry)
        last_error = ""
        for attempt in range(1, attempts + 1):
            if attempt > 1:
                _time.sleep(1.0)  # polite back-off between retries
            call = self.ledger.begin(self.config.llm_provider, self.config.llm_model, operation, attempt)
            if sink:
                sink(ProviderEvent("provider_call_started", {
                    "call_id": call.call_id, "turn_id": call.turn_id, "operation": operation,
                    "attempt": attempt, "parent_call_id": call.parent_call_id,
                    "trigger_event_id": call.trigger_event_id,
                }))
            try:
                data = self.adapter.request(body, timeout=timeout, on_event=sink)
                usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
                self.ledger.finish(call, "completed", usage=usage)
                if sink:
                    sink(ProviderEvent("provider_call_finished", {
                        "call_id": call.call_id, "operation": operation, "attempt": attempt,
                        "status": "completed", "usage": usage,
                    }))
                return data, attempt, "", None, call.call_id
            except urllib.error.HTTPError as exc:
                retry_after = self._retry_after(exc)
                last_error = f"HTTPError: {exc}"
                status = "rate_limited" if exc.code == 429 else "failed"
                self.ledger.finish(call, status, error=last_error, metadata={"retry_after": retry_after})
                if sink:
                    sink(ProviderEvent(status, {
                        "call_id": call.call_id, "operation": operation, "attempt": attempt,
                        "error": last_error, "retry_after": retry_after,
                    }))
                # Rate limits are never retried immediately. The Turn Coordinator
                # owns the visible wait/resume policy.
                if exc.code == 429:
                    return None, attempt, "rate_limited", retry_after, call.call_id
                if attempt >= attempts:
                    return None, attempt, last_error, None, call.call_id
            except KeyboardInterrupt:
                self.ledger.finish(call, "cancelled", error="cancelled_by_user")
                return None, attempt, "cancelled", None, call.call_id
            except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError, ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                self.ledger.finish(call, "failed", error=last_error)
                if sink:
                    sink(ProviderEvent("provider_call_finished", {
                        "call_id": call.call_id, "operation": operation, "attempt": attempt,
                        "status": "failed", "error": last_error,
                    }))
                retryable = not isinstance(exc, (ValueError, KeyError, IndexError, json.JSONDecodeError))
                if attempt >= attempts or not retryable:
                    return None, attempt, last_error, None, call.call_id
        self.logger.log(
            provider=self.config.llm_provider, model=self.config.llm_model, operation=operation,
            prompt=prompt_for_log, response="", status="failed", error=last_error,
        )
        return None, attempts, last_error or "model_request_failed", None, ""

    def complete(
        self,
        operation: str,
        prompt: str,
        fallback: str = "",
        *,
        system: str = "",
        temperature: float = 0.2,
        tools: list[dict[str, Any]] | None = None,
        on_event: EventSink | None = None,
    ) -> LLMResult:
        max_tokens = self.config.llm_max_tokens
        if self.cancel_event and self.cancel_event.is_set():
            return self._fallback(operation, prompt, fallback, "cancelled", attempts=0)
        if not self.config.llm_configured:
            return self._fallback(operation, prompt, fallback, "model_not_configured", attempts=0)

        messages = ([{"role": "system", "content": system}] if system else [])
        messages.append({"role": "user", "content": prompt})
        request_body = {"model": self.config.llm_model, "messages": messages, "temperature": temperature}
        if max_tokens > 0:
            request_body["max_tokens"] = max_tokens
        if tools:
            request_body["tools"] = tools
            request_body["tool_choice"] = "auto"
        data, attempt, error, retry_after, call_id = self._perform(
            operation, request_body,
            timeout=self.config.llm_timeout_seconds,
            prompt_for_log=prompt, on_event=on_event,
        )
        if data is None:
            result = self._fallback(operation, prompt, fallback, error or "model_request_failed", attempts=attempt)
            result.retry_after = retry_after; result.call_id = call_id
            return result
        normalized = _normalize_response(data)
        if normalized.outcome not in {"text", "native_tool_call"}:
            return self._fallback(operation, prompt, fallback, normalized.outcome, attempts=attempt, response_shape=normalized)
        raw_message = data.get("choices", [{}])[0].get("message", {})
        tool_calls = raw_message.get("tool_calls") if isinstance(raw_message, dict) else None
        self.logger.log(
            provider=self.config.llm_provider, model=self.config.llm_model, operation=operation,
            prompt=prompt, response=normalized.text, status="ok",
            metadata={"attempt": attempt, "remote": True, "call_id": call_id, "response_shape": normalized.metadata()},
        )
        return LLMResult(
            normalized.text, self.config.llm_provider, self.config.llm_model, True,
            operation=operation, attempts=attempt, outcome=normalized.outcome,
            tool_calls=tool_calls if isinstance(tool_calls, list) else None,
            assistant_message=raw_message if isinstance(raw_message, dict) else None,
            usage=data.get("usage") if isinstance(data.get("usage"), dict) else {}, call_id=call_id,
        )

    def chat(
        self,
        operation: str,
        messages: list[dict[str, Any]],
        *,
        system: str = "",
        tools: list[dict[str, Any]] | None = None,
        on_event: EventSink | None = None,
    ) -> LLMResult:
        """Run one native assistant/tool turn without replacing it with a local decision protocol."""
        if self.cancel_event and self.cancel_event.is_set():
            return self._fallback(operation, "", "", "cancelled", attempts=0)
        if not self.config.llm_configured:
            return self._fallback(operation, "", "", "model_not_configured", attempts=0)

        request_messages = ([{"role": "system", "content": system}] if system else []) + list(messages)
        request_body: dict[str, Any] = {"model": self.config.llm_model, "messages": request_messages}
        max_tokens = self.config.llm_max_tokens
        if max_tokens > 0:
            request_body["max_tokens"] = max_tokens
        if tools:
            request_body["tools"] = tools
            request_body["tool_choice"] = "auto"
        prompt_log = json.dumps(request_messages, ensure_ascii=False, default=str)
        data, attempt, error, retry_after, call_id = self._perform(
            operation, request_body, timeout=self.config.llm_timeout_seconds,
            prompt_for_log=prompt_log, on_event=on_event,
        )
        if data is None:
            result = self._fallback(operation, "", "", error or "model_request_failed", attempts=attempt)
            result.retry_after = retry_after; result.call_id = call_id
            return result
        normalized = _normalize_response(data)
        choice = data.get("choices", [{}])[0] if isinstance(data, dict) else {}
        raw_message = choice.get("message") if isinstance(choice, dict) else {}
        raw_message = raw_message if isinstance(raw_message, dict) else {}
        assistant_message = {
            key: raw_message[key]
            for key in ("role", "content", "reasoning_content", "tool_calls")
            if key in raw_message and raw_message[key] is not None
        }
        assistant_message.setdefault("role", "assistant")
        tool_calls = raw_message.get("tool_calls") if isinstance(raw_message.get("tool_calls"), list) else None
        if normalized.outcome not in {"text", "native_tool_call"}:
            return self._fallback(operation, "", "", normalized.outcome, attempts=attempt, response_shape=normalized)
        self.logger.log(
            provider=self.config.llm_provider, model=self.config.llm_model, operation=operation,
            prompt=prompt_log, response=normalized.text, status="ok",
            metadata={"attempt": attempt, "remote": True, "call_id": call_id, "response_shape": normalized.metadata()},
        )
        return LLMResult(
            normalized.text, self.config.llm_provider, self.config.llm_model, True,
            operation=operation, attempts=attempt, outcome=normalized.outcome,
            tool_calls=tool_calls, assistant_message=assistant_message,
            usage=data.get("usage") if isinstance(data.get("usage"), dict) else {}, call_id=call_id,
        )

    def health(self) -> dict[str, object]:
        result = self.complete("model_health", "Reply with exactly: OK", system="Health check.", temperature=0)
        return {
            "ok": result.used_remote_model and result.text.strip().upper() == "OK",
            "provider": self.config.llm_provider,
            "model": self.config.llm_model,
            "error": result.error,
            "attempts": result.attempts,
        }

    def _fallback(
        self,
        operation: str,
        prompt: str,
        fallback: str,
        error: str,
        *,
        attempts: int,
        response_shape: NormalizedResponse | None = None,
    ) -> LLMResult:
        self.logger.log(
            provider=self.config.llm_provider, model=self.config.llm_model, operation=operation,
            prompt=prompt, response=fallback or "", status="failed", error=error,
            metadata={
                "attempts": attempts,
                "max_tokens": self.config.llm_max_tokens,
                "remote": False,
                **({"response_shape": response_shape.metadata()} if response_shape else {}),
            },
        )
        return LLMResult(
            fallback or "",
            self.config.llm_provider,
            self.config.llm_model,
            False,
            error,
            operation,
            attempts,
            outcome=error,
        )


# Kept as an import-compatible name; no caller gets a second implementation.
LLMClient = ModelGateway
