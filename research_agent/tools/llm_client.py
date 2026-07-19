from __future__ import annotations

import http.client
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import time as _time
import urllib.error
import urllib.request
from dataclasses import dataclass
from threading import Event
from typing import Any, Callable, Iterable, Protocol

from research_agent.config import AgentConfig
from research_agent.logging import ModelCallLogger
from research_agent.provider_runtime import (
    CallLedger,
    ProviderEvent,
    current_event_sink,
)


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


# DeepSeek and some other providers stream tool calls as text inside
# ``content`` rather than using the native ``tool_calls`` array.  These
# patterns match the known serialisation styles so we can extract the
# payload, convert it to a native tool-call object, and strip it from
# the user-visible response.
# Known formats:
#   <function_calls><invoke …>…</invoke></function_calls>
#   <tool_calls><invoke …>…</invoke></tool_calls>
#   <||DSML||tool_calls><||DSML||invoke …>…</||DSML||invoke></||DSML||tool_calls>
_DB = "｜｜"  # fullwidth double bar ｜｜
_DSML_OPEN = re.compile(
    r"<(?:function_calls|tool_calls|" + _DB + r"DSML" + _DB + r"\w+)>[\s\S]*"
    r"</(?:function_calls|tool_calls|" + _DB + r"DSML" + _DB + r"\w+)>",
    re.IGNORECASE,
)
_DSML_INVOKE = re.compile(
    r"<invoke\s+name\s*=\s*\"([^\"]+)\">[\s\S]*?</invoke>"
    r"|<" + _DB + r"DSML" + _DB + r"invoke\s+name\s*=\s*\"([^\"]+)\">[\s\S]*?</" + _DB + r"DSML" + _DB + r"invoke>",
    re.IGNORECASE,
)
_DSML_PARAM = re.compile(
    r"<parameter\s+name\s*=\s*\"([^\"]+)\"(?:\s+string\s*=\s*\"(true|false)\")?>([\s\S]*?)</parameter>"
    r"|<" + _DB + r"DSML" + _DB + r"parameter\s+name\s*=\s*\"([^\"]+)\"(?:\s+string\s*=\s*\"(true|false)\")?>([\s\S]*?)</" + _DB + r"DSML" + _DB + r"parameter>",
    re.IGNORECASE,
)


def _strip_tool_call_text(text: str) -> str:
    if not text:
        return ""
    return _DSML_OPEN.sub("", text).strip()


def _coerce_param_value(raw: str) -> Any:
    """Auto-detect the intended type of a DSML parameter value.
    Not hardcoded to any tool or field name — purely value-driven."""
    if not raw:
        return ""
    if raw.startswith("[") and raw.endswith("]"):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            pass
    stripped = raw.strip()
    if re.match(r"^-?\d+$", stripped):
        return int(stripped)
    if re.match(r"^-?\d+\.\d+$", stripped):
        return float(stripped)
    if stripped.lower() in ("true", "false"):
        return stripped.lower() == "true"
    return raw


def _extract_xml_tool_calls(text: str) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for block in _DSML_OPEN.findall(text):
        for invoke in _DSML_INVOKE.finditer(block):
            name = invoke.group(1) or invoke.group(2)
            params: dict[str, Any] = {}
            for param in _DSML_PARAM.finditer(invoke.group(0)):
                key = param.group(1) or param.group(4)
                is_json = param.group(2) or param.group(5)
                raw = (param.group(3) or param.group(6) or "").strip()
                if is_json == "true":
                    try:
                        params[key] = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        params[key] = raw
                else:
                    params[key] = _coerce_param_value(raw)
            if name:
                calls.append({
                    "id": f"dsml-{len(calls)}",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(params, ensure_ascii=False)},
                })
    return calls


def _extract_tool_calls_from_content(text: str) -> tuple[str, list[dict[str, Any]]]:
    if not text:
        return "", []
    extra = _extract_xml_tool_calls(text)
    cleaned = _strip_tool_call_text(text)
    if _is_inside_fence(cleaned):
        positions = [position for opener in _ToolCallStreamFilter._OPENERS if (position := cleaned.find(opener)) >= 0]
        if positions:
            cleaned = cleaned[: min(positions)].strip()
    return cleaned, extra


def _merge_tool_calls(*groups: Any) -> list[dict[str, Any]]:
    """Merge native and serialized calls without executing the same call twice."""
    merged: list[dict[str, Any]] = []
    signatures: set[tuple[str, str]] = set()
    for group in groups:
        if not isinstance(group, list):
            continue
        for call in group:
            if not isinstance(call, dict):
                continue
            function = call.get("function") if isinstance(call.get("function"), dict) else {}
            name = str(function.get("name") or "").strip()
            arguments = function.get("arguments")
            if not name:
                continue
            try:
                canonical = json.dumps(json.loads(arguments or "{}"), ensure_ascii=False, sort_keys=True)
            except (json.JSONDecodeError, TypeError):
                canonical = str(arguments or "")
            signature = (name, canonical)
            if signature in signatures:
                continue
            signatures.add(signature)
            merged.append(call)
    return merged


def _is_inside_fence(text: str) -> bool:
    if not text:
        return False
    opened = any(p in text for p in (
        "<function_calls>", "<tool_calls>",
        "<" + _DB + "DSML" + _DB,
        _DB + "DSML" + _DB,
    ))
    closed = any(p in text for p in (
        "</function_calls>", "</tool_calls>",
        "</" + _DB + "DSML" + _DB,
    ))
    return opened and not closed


class _ToolCallStreamFilter:
    """Keep provider-serialized tool calls out of user-visible text deltas."""

    _OPENERS = ("<function_calls", "<tool_calls", "<" + _DB + "DSML" + _DB)

    def __init__(self) -> None:
        self.buffer = ""
        self.inside_protocol = False

    def feed(self, fragment: str) -> str:
        self.buffer += fragment
        visible: list[str] = []
        while self.buffer:
            if self.inside_protocol:
                complete = _DSML_OPEN.match(self.buffer)
                if complete is None:
                    break
                self.buffer = self.buffer[complete.end():]
                self.inside_protocol = False
                continue

            positions = [position for opener in self._OPENERS if (position := self.buffer.find(opener)) >= 0]
            if positions:
                start = min(positions)
                if start:
                    visible.append(self.buffer[:start])
                    self.buffer = self.buffer[start:]
                self.inside_protocol = True
                continue

            held = self._possible_opener_suffix(self.buffer)
            if held:
                visible.append(self.buffer[:-held])
                self.buffer = self.buffer[-held:]
            else:
                visible.append(self.buffer)
                self.buffer = ""
            break
        return "".join(visible)

    def finish(self) -> str:
        if self.inside_protocol:
            self.buffer = ""
            return ""
        visible = self.buffer
        self.buffer = ""
        return visible

    def _possible_opener_suffix(self, text: str) -> int:
        maximum = 0
        for opener in self._OPENERS:
            for length in range(1, min(len(text), len(opener) - 1) + 1):
                if text.endswith(opener[:length]):
                    maximum = max(maximum, length)
        return maximum


def _normalize_response(data: Any) -> NormalizedResponse:
#   <｜｜DSML｜｜tool_calls><｜｜DSML｜｜invoke …>…(data: Any) -> NormalizedResponse:
    choices = data.get("choices") if isinstance(data, dict) else None
    choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    content = message.get("content")
    reasoning = message.get("reasoning_content")
    text, serialized_calls = _extract_tool_calls_from_content(_message_text(content))
    tool_calls = _merge_tool_calls(message.get("tool_calls"), serialized_calls)
    if message:
        message["content"] = text or None
        if tool_calls:
            message["tool_calls"] = tool_calls
        else:
            message.pop("tool_calls", None)
    tool_call_count = len(tool_calls) if isinstance(tool_calls, list) else int(bool(tool_calls))
    finish_reason = choice.get("finish_reason") if isinstance(choice.get("finish_reason"), str) else ""
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
        protocol_filter = _ToolCallStreamFilter()
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
                visible = protocol_filter.feed(text)
                if visible:
                    on_event(ProviderEvent("assistant_delta", {"text": visible}))
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
        remaining = protocol_filter.finish()
        if remaining:
            on_event(ProviderEvent("assistant_delta", {"text": remaining}))
        raw_content = "".join(content)
        cleaned, extra_calls = _extract_tool_calls_from_content(raw_content)
        merged_calls = _merge_tool_calls([calls[index] for index in sorted(calls)], extra_calls)
        message: dict[str, Any] = {"role": "assistant", "content": cleaned or None}
        if reasoning:
            message["reasoning_content"] = "".join(reasoning)
        if merged_calls:
            message["tool_calls"] = merged_calls
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
        inherited_sink = current_event_sink()
        sink = on_event or inherited_sink
        # A turn-level sink is inherited by nested capability clients so their
        # lifecycle and usage remain observable. Their streamed payload is an
        # internal protocol, however, and must never become assistant chat.
        # Only an explicitly supplied sink opts a model call into user-visible
        # token streaming (the main AgentLoop does this).
        adapter_sink = sink if on_event is not None else (lambda _event: None) if sink else None
        attempts = 1 + max(0, self.config.llm_retry)
        last_error = ""
        for attempt in range(1, attempts + 1):
            request_body = dict(body)
            if attempt > 1:
                _time.sleep(min(30.0, 0.5 * (2 ** (attempt - 1))))  # exponential back-off
            call = self.ledger.begin(self.config.llm_provider, self.config.llm_model, operation, attempt)
            if sink:
                sink(ProviderEvent("provider_call_started", {
                    "call_id": call.call_id, "turn_id": call.turn_id, "operation": operation,
                    "attempt": attempt, "parent_call_id": call.parent_call_id,
                    "trigger_event_id": call.trigger_event_id,
                }))
            try:
                data = self.adapter.request(request_body, timeout=timeout, on_event=adapter_sink)
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

    @staticmethod
    def _estimate_request_tokens(body: dict[str, Any]) -> int:
        """Conservatively reserve provider-neutral input tokens before an HTTP call."""
        payload = dict(body)
        payload.pop("max_tokens", None)
        encoded = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        return max(1, (len(encoded) + 2) // 3)

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

    def map_complete(
        self,
        operation: str,
        items: list[dict[str, Any]],
        prompt_fn,
        *,
        system: str = "",
        temperature: float = 0.0,
        fallback_fn=None,
    ) -> list[LLMResult]:
        """One ``complete()`` call per item, all sent concurrently.

        Concurrency is naturally bounded by the provider max-concurrency
        semaphore that every ``complete()`` acquires in ``_perform()``.
        No extra throttling — one item, one request, fire all at once.
        """
        if not items:
            return []
        max_workers = len(items)

        def _one(item):
            if self.cancel_event and self.cancel_event.is_set():
                return LLMResult("", self.config.llm_provider, self.config.llm_model, False, "cancelled", operation)
            prompt = prompt_fn(item)
            result = self.complete(operation, prompt, fallback="" if fallback_fn is None else fallback_fn(item),
                                   system=system, temperature=temperature)
            if result.error == "rate_limited" and result.retry_after is not None:
                import time as _time
                _time.sleep(min(result.retry_after, 10.0))
                result = self.complete(operation, prompt, fallback="" if fallback_fn is None else fallback_fn(item),
                                       system=system, temperature=temperature)
            return result

        results: list[LLMResult] = []
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_index = {pool.submit(_one, item): i for i, item in enumerate(items)}
            indexed: dict[int, LLMResult] = {}
            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                try:
                    indexed[idx] = future.result()
                except Exception:
                    item = items[idx]
                    indexed[idx] = LLMResult(
                        fallback_fn(item) if fallback_fn else "",
                        self.config.llm_provider, self.config.llm_model, False,
                        "map_item_failed", operation,
                    )
        for i in range(len(items)):
            results.append(indexed[i])
        return results

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
