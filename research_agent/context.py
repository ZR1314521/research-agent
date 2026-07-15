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

    def __init__(self, session_dir: Path, context_window: int = 0):
        self.session_dir = Path(session_dir)
        self.context_window = max(0, int(context_window))
        self.observation_dir = self.session_dir / "tool_observations"
        self._effective_window = self.context_window or 128_000

    # ── helpers ────────────────────────────────────────────────────────

    @staticmethod
    def estimate_tokens(value: Any) -> int:
        text = json.dumps(value, ensure_ascii=False, default=str)
        return max(1, (len(text) + 3) // 4)

    @staticmethod
    def _payload(msg: dict[str, Any]) -> dict[str, Any] | None:
        try:
            return json.loads(msg.get("content", "{}"))
        except (json.JSONDecodeError, TypeError):
            return None

    # ── observation ────────────────────────────────────────────────────

    def observation(
        self,
        *,
        tool: str,
        message: str,
        data: Any,
        artifacts: dict[str, Any],
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        full: dict[str, Any] = {
            "ok": True, "tool": tool, "message": message,
            "data": data, "artifacts": artifacts,
        }
        self.observation_dir.mkdir(parents=True, exist_ok=True)
        path = self.observation_dir / f"{uuid.uuid4().hex}.json"
        path.write_text(json.dumps(full, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

        room = self._effective_window - self.estimate_tokens(messages)
        if self.estimate_tokens(full) <= room:
            return full
        compact: dict[str, Any] = {
            "ok": True, "tool": tool, "message": message,
            "artifacts": artifacts, "data_ref": str(path),
            "note": "The complete tool observation is stored locally and can be read on demand.",
        }
        if self.estimate_tokens(compact) > room:
            compact["message"] = "Tool completed; read data_ref for the complete result."
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
        room = self._effective_window - self.estimate_tokens(occupied) - max(0, int(reserve_tokens))
        if self.estimate_tokens(text) <= room:
            return text
        source_dir = self.session_dir / "context_sources"
        source_dir.mkdir(parents=True, exist_ok=True)
        path = source_dir / f"{uuid.uuid4().hex}-{label}.txt"
        path.write_text(text, encoding="utf-8")
        budget = max(1, room) * 4
        ref = f"\n\n[Complete source: {path}]"
        if budget <= len(ref):
            return ref.strip()
        return text[: budget - len(ref)] + ref

    # ── budget-driven compaction ───────────────────────────────────────

    def fit_to_budget(
        self,
        messages: list[dict[str, Any]],
        *,
        summarizer: "Any | None" = None,
    ) -> list[dict[str, Any]]:
        """Ensure messages fit within the effective window.

        Tries progressively: as-is → strip old tool data → summarise.
        Every decision is driven by a single question: does it fit?
        """
        total = self.estimate_tokens(messages)
        if total <= self._effective_window:
            return messages

        # Stage 1: strip data from tool results, oldest first.
        stripped = list(messages)
        for msg in stripped:
            if self.estimate_tokens(stripped) <= self._effective_window:
                break
            if msg.get("role") != "tool":
                continue
            payload = self._payload(msg)
            if payload and "data" in payload:
                payload.pop("data", None)
                msg["content"] = json.dumps(payload, ensure_ascii=False, default=str)

        if self.estimate_tokens(stripped) <= self._effective_window:
            return stripped

        # Stage 2: strip message from all tool results, oldest first.
        for msg in stripped:
            if self.estimate_tokens(stripped) <= self._effective_window:
                break
            if msg.get("role") != "tool":
                continue
            payload = self._payload(msg)
            if payload:
                payload.pop("message", None)
                payload.pop("artifacts", None)
                msg["content"] = json.dumps(payload, ensure_ascii=False, default=str)

        if self.estimate_tokens(stripped) <= self._effective_window:
            return stripped

        # Stage 3: summarise oldest messages into a single roll-up.
        if not summarizer:
            return stripped

        # Walk forward until the tail fits, summarise the head.
        recent: list[dict[str, Any]] = []
        for msg in reversed(stripped):
            if self.estimate_tokens(recent + [msg]) > self._effective_window:
                break
            recent.insert(0, msg)
        older = stripped[: len(stripped) - len(recent)]
        if len(older) < 4:
            return stripped

        summary_text = summarizer(older)
        return [{"role": "user", "content": f"[Earlier]\n{summary_text}"}] + recent
