from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any


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
        self.observation_dir = self.session_dir / "tool_observations"
        self._budget = self.context_window or 128_000
        # The budget is the harness working-set ceiling.  When configured it
        # drives compaction and observation sizing.  When unset, the full
        # window is used — everything fits until it doesn't.
        self._budget = max(0, int(context_budget)) if context_budget else self._budget
        self._observation_budget = max(256, int(observation_budget))

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
        model_observation = {**full, "data_ref": str(path)}
        if self.estimate_tokens(model_observation) <= allowance:
            return model_observation
        delivery = {
            key: data[key]
            for key in ("answer_ready", "missing_evidence", "completion_guidance")
            if isinstance(data, dict) and key in data
        }
        compact: dict[str, Any] = {
            "ok": ok, "outcome": outcome, "tool": tool, "message": message,
            "artifacts": artifacts, "data_ref": str(path),
            "note": "The complete tool observation is stored locally and can be read on demand.",
            **delivery,
        }
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
                "data_ref": str(path),
                "note": "Complete tool observation stored locally.",
                **delivery,
            }
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
        source_dir = self.session_dir / "context_sources"
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
        Every decision is driven by a single question: does it fit?
        """
        message_budget = max(
            1,
            self._budget
            - self.estimate_tokens(fixed_context)
            - max(0, int(reserve_tokens)),
        )
        total = self.estimate_tokens(messages)
        if total <= message_budget:
            return messages

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
            return stripped

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
            return stripped

        # Stage 3: summarise oldest messages into a single roll-up.
        if not summarizer:
            return stripped

        # Walk forward until the tail fits, summarise the head.
        recent: list[dict[str, Any]] = []
        for msg in reversed(stripped):
            if self.estimate_tokens(recent + [msg]) > message_budget:
                break
            recent.insert(0, msg)
        older = stripped[: len(stripped) - len(recent)]
        if len(older) < 4:
            return stripped

        summary_text = summarizer(older)
        return [{"role": "user", "content": f"[Earlier]\n{summary_text}"}] + recent
