from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from research_agent.capabilities.workspace import WorkspaceContext


class ContextManager:
    """Budget-driven context management.

    There is one constraint: messages must fit within the effective
    window.  When they don't, the harness applies progressively tighter
    compaction until they do.  No fixed ratios, no round counts.
    """

    def __init__(
        self,
        session_dir: Path,
        context_window: int = 0,
        *,
        context_budget: int = 0,
        observation_budget: int = 4_000,
    ):
        self.session_dir = Path(session_dir)
        self.context_window = max(0, int(context_window))
        workspace = WorkspaceContext.for_session(self.session_dir)
        self.workspace = workspace
        self.context_storage_dir = workspace.temp_root / "context"
        self.observation_dir = self.context_storage_dir / "tool_observations"
        self._budget = self.context_window or 128_000
        # The budget is the harness working-set ceiling.  When configured it
        # drives compaction and observation sizing.  When unset, the full
        # window is used — everything fits until it doesn't.
        self._budget = max(0, int(context_budget)) if context_budget else self._budget
        self._observation_budget = max(256, int(observation_budget))
        self._total_bytes = 65_536  # provider-agnostic HTTP body ceiling

    # ── helpers ────────────────────────────────────────────────────────

    @staticmethod
    def estimate_tokens(value: Any) -> int:
        text = json.dumps(value, ensure_ascii=False, default=str)
        # Provider-neutral fallback. UTF-8 bytes / 3 is deliberately more
        # conservative than the common English-only chars / 4 heuristic and
        # tracks mixed JSON/CJK payloads without embedding model-specific rules.
        size = len(text.encode("utf-8"))
        return max(1, (size + 2) // 3)

    @staticmethod
    def _payload(msg: dict[str, Any]) -> dict[str, Any] | None:
        try:
            return json.loads(msg.get("content", "{}"))
        except (json.JSONDecodeError, TypeError):
            return None

    @classmethod
    def _text_prefix_within(cls, text: str, suffix: str, token_budget: int) -> str:
        """Return the longest prefix plus suffix that fits the estimate."""
        if token_budget <= 0 or cls.estimate_tokens(suffix) > token_budget:
            return suffix.strip()
        low, high = 0, len(text)
        while low < high:
            middle = (low + high + 1) // 2
            if cls.estimate_tokens(text[:middle] + suffix) <= token_budget:
                low = middle
            else:
                high = middle - 1
        return text[:low] + suffix

    # ── observation ────────────────────────────────────────────────────

    def _pageable_source(
        self,
        data: Any,
        message: str,
        allowance: int,
    ) -> dict[str, Any] | None:
        """Point oversized text reads back to their source instead of nesting refs."""
        if not isinstance(data, dict) or not data.get("path"):
            return None
        try:
            source = self.workspace.resolve(str(data["path"]))
            total_lines = max(0, int(data.get("total_lines") or 0))
            start_line = max(0, int(data.get("start_line") or 0))
            end_line = max(start_line, int(data.get("end_line") or start_line))
        except (OSError, TypeError, ValueError):
            return None
        if not source.is_file() or total_lines <= 0:
            return None
        returned_lines = max(1, end_line - start_line + 1)
        tokens_per_line = max(1, self.estimate_tokens(message) // returned_lines)
        page_budget = max(1, allowance // 2)
        suggested_limit = max(1, min(total_lines, page_budget // tokens_per_line))
        return {
            "data_ref": str(source),
            "read_hint": {
                "offset": 0,
                "limit": suggested_limit,
                "total_lines": total_lines,
            },
            "note": "The text result exceeded the observation budget. Read data_ref in pages using read_hint.",
        }

    def tool_payload(
        self,
        payload: dict[str, Any],
        *,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Keep arbitrary tool messages within the observation boundary."""
        room = max(0, self._budget - self.estimate_tokens(messages))
        allowance = min(room, self._observation_budget)
        if self.estimate_tokens(payload) <= allowance:
            return payload

        self.observation_dir.mkdir(parents=True, exist_ok=True)
        path = self.observation_dir / f"{uuid.uuid4().hex}.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        compact = {
            key: payload[key]
            for key in ("ok", "tool", "error_code")
            if key in payload
        }
        summary = payload.get("error") or payload.get("message") or "Tool result stored locally."
        compact["error" if payload.get("ok") is False else "message"] = str(summary)[:500]
        compact["data_ref"] = str(path)
        compact["note"] = "Complete tool payload stored locally."
        if self.estimate_tokens(compact) > allowance:
            compact.pop("error", None)
            compact.pop("message", None)
            compact["note"] = "Tool payload too large; read data_ref."
        return compact

    def observation(
        self,
        *,
        tool: str,
        message: str,
        data: Any,
        artifacts: dict[str, Any],
        messages: list[dict[str, Any]],
        ok: bool = True,
        outcome: str = "success",
    ) -> dict[str, Any]:
        full: dict[str, Any] = {
            "ok": ok, "outcome": outcome, "tool": tool, "message": message,
            "data": data, "artifacts": artifacts,
        }
        self.observation_dir.mkdir(parents=True, exist_ok=True)
        path = self.observation_dir / f"{uuid.uuid4().hex}.json"
        path.write_text(json.dumps(full, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

        room = max(0, self._budget - self.estimate_tokens(messages))
        allowance = min(room, self._observation_budget)
        pageable = self._pageable_source(data, message, allowance)
        delivery = {
            key: data[key]
            for key in ("answer_ready", "missing_evidence", "completion_guidance")
            if isinstance(data, dict) and key in data
        }
        compact: dict[str, Any] = {
            "ok": ok, "outcome": outcome, "tool": tool, "message": message,
            "artifacts": artifacts,
            "data_ref": str(pageable["data_ref"] if pageable else path),
            "note": str(pageable["note"] if pageable else "The complete tool observation is stored locally and can be read on demand."),
            **delivery,
        }
        if pageable:
            compact["read_hint"] = pageable["read_hint"]
            compact["message"] = "Tool result is available from data_ref in bounded pages."
        if self.estimate_tokens(compact) > allowance:
            compact["message"] = "Tool completed; read data_ref for the complete result."
        if self.estimate_tokens(compact) > allowance:
            compact.pop("artifacts", None)
            compact["artifact_keys"] = list(artifacts)
        if self.estimate_tokens(compact) > allowance:
            compact = {
                "ok": ok,
                "outcome": outcome,
                "tool": tool,
                "data_ref": str(pageable["data_ref"] if pageable else path),
                "note": str(pageable["note"] if pageable else "Complete tool observation stored locally."),
                **delivery,
            }
            if pageable:
                compact["read_hint"] = pageable["read_hint"]
        return compact

    # ── evidence ───────────────────────────────────────────────────────

    def fit_text(
        self,
        text: str,
        *,
        label: str,
        occupied: Any = "",
        reserve_tokens: int = 0,
    ) -> str:
        room = self._budget - self.estimate_tokens(occupied) - max(0, int(reserve_tokens))
        if self.estimate_tokens(text) <= room:
            return text
        source_dir = self.context_storage_dir / "sources"
        source_dir.mkdir(parents=True, exist_ok=True)
        path = source_dir / f"{uuid.uuid4().hex}-{label}.txt"
        path.write_text(text, encoding="utf-8")
        ref = f"\n\n[Complete source: {path}]"
        return self._text_prefix_within(text, ref, max(1, room))

    # ── budget-driven compaction ───────────────────────────────────────

    def fit_to_budget(
        self,
        messages: list[dict[str, Any]],
        *,
        summarizer: "Any | None" = None,
        fixed_context: Any = "",
        reserve_tokens: int = 0,
    ) -> list[dict[str, Any]]:
        """Ensure messages fit within the effective window.

        Tries progressively: as-is → strip old tool data → summarise.
        After token-based trimming, also enforces a raw-byte safety cap
        so the provider's HTTP body limit is never exceeded.
        """
        message_budget = max(
            1,
            self._budget
            - self.estimate_tokens(fixed_context)
            - max(0, int(reserve_tokens)),
        )
        total = self.estimate_tokens(messages)
        if total <= message_budget:
            return self._fit_bytes(messages, fixed_context, summarizer)

        # Stage 1: strip data from tool results, oldest first.
        stripped = [dict(message) for message in messages]
        for msg in stripped:
            if self.estimate_tokens(stripped) <= message_budget:
                break
            if msg.get("role") != "tool":
                continue
            payload = self._payload(msg)
            if payload and "data" in payload:
                payload.pop("data", None)
                msg["content"] = json.dumps(payload, ensure_ascii=False, default=str)

        if self.estimate_tokens(stripped) <= message_budget:
            return self._fit_bytes(stripped, fixed_context, summarizer)

        # Stage 2: strip message from all tool results, oldest first.
        for msg in stripped:
            if self.estimate_tokens(stripped) <= message_budget:
                break
            if msg.get("role") != "tool":
                continue
            payload = self._payload(msg)
            if payload:
                payload.pop("message", None)
                payload.pop("artifacts", None)
                msg["content"] = json.dumps(payload, ensure_ascii=False, default=str)

        if self.estimate_tokens(stripped) <= message_budget:
            return self._fit_bytes(stripped, fixed_context, summarizer)

        # Stage 3: summarise oldest messages into a single roll-up.
        if not summarizer:
            return self._fit_bytes(stripped, fixed_context, summarizer)

        # Walk forward until the tail fits, summarise the head.
        recent: list[dict[str, Any]] = []
        for msg in reversed(stripped):
            if self.estimate_tokens(recent + [msg]) > message_budget:
                break
            recent.insert(0, msg)
        older = stripped[: len(stripped) - len(recent)]
        if len(older) < 4:
            return self._fit_bytes(stripped, fixed_context, summarizer)

        summary_text = summarizer(older)
        return self._fit_bytes(
            [{"role": "user", "content": f"[Earlier]\n{summary_text}"}] + recent,
            fixed_context, summarizer,
        )

    def _fit_bytes(
        self,
        messages: list[dict[str, Any]],
        fixed_context: Any,
        summarizer: "Any | None",
    ) -> list[dict[str, Any]]:
        # Build the full request body once to check the real byte size.
        # This mirrors what the provider actually receives — no token
        # estimation, no guesswork.
        body = self._build_body(messages, fixed_context)
        actual = len(body.encode())
        if actual <= self._total_bytes:
            return messages
        trimmed = list(messages)
        need = actual
        while len(trimmed) > 2:
            if trimmed[0].get("role") == "tool":
                payload = self._payload(trimmed[0])
                if payload:
                    before = len(json.dumps(trimmed, ensure_ascii=False, default=str).encode())
                    payload.pop("data", None)
                    payload.pop("message", None)
                    payload.pop("artifacts", None)
                    trimmed[0]["content"] = json.dumps(payload, ensure_ascii=False, default=str)
                    after = len(json.dumps(trimmed, ensure_ascii=False, default=str).encode())
                    if after < before:
                        continue
            trimmed.pop(0)
            body = self._build_body(trimmed, fixed_context)
            if len(body.encode()) <= self._total_bytes:
                return trimmed
        return trimmed

    def _build_body(
        self,
        messages: list[dict[str, Any]],
        fixed_context: Any,
    ) -> str:
        req: dict[str, Any] = {"messages": messages}
        if isinstance(fixed_context, dict):
            if fixed_context.get("system"):
                req["system"] = fixed_context["system"]
            if fixed_context.get("tools"):
                req["tools"] = fixed_context["tools"]
        return json.dumps(req, ensure_ascii=False, default=str)
