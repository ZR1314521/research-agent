from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any


class ContextManager:
    """Package observations without making semantic routing decisions."""

    def __init__(self, session_dir: Path, context_window: int = 0):
        self.session_dir = Path(session_dir)
        self.context_window = max(0, int(context_window))
        self.observation_dir = self.session_dir / "tool_observations"

    @staticmethod
    def estimate_tokens(value: Any) -> int:
        # Provider-neutral approximation used only for transport sizing.
        text = json.dumps(value, ensure_ascii=False, default=str)
        return max(1, (len(text) + 3) // 4)

    def observation(
        self,
        *,
        tool: str,
        message: str,
        data: Any,
        artifacts: dict[str, Any],
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        full = {
            "ok": True,
            "tool": tool,
            "message": message,
            "data": data,
            "artifacts": artifacts,
        }
        self.observation_dir.mkdir(parents=True, exist_ok=True)
        path = self.observation_dir / f"{uuid.uuid4().hex}.json"
        path.write_text(json.dumps(full, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

        if not self.context_window:
            return full
        available = max(0, self.context_window - self.estimate_tokens(messages))
        if self.estimate_tokens(full) <= available:
            return full
        compact = {
            "ok": True,
            "tool": tool,
            "message": message,
            "artifacts": artifacts,
            "data_ref": str(path),
            "note": "The complete tool observation is stored locally and can be read on demand.",
        }
        if self.estimate_tokens(compact) > available:
            compact["message"] = "Tool completed; read data_ref for the complete result."
        return compact

    def fit_text(
        self,
        text: str,
        *,
        label: str,
        occupied: Any = "",
        reserve_tokens: int = 0,
    ) -> str:
        """Fit evidence to a configured context window without fixed character caps.

        A zero context window means the runtime does not impose a local limit. When a
        window is configured, the complete source is persisted and the returned text
        carries its reference if only a prefix can fit.
        """
        if not self.context_window:
            return text
        available = max(
            0,
            self.context_window - self.estimate_tokens(occupied) - max(0, int(reserve_tokens)),
        )
        if self.estimate_tokens(text) <= available:
            return text
        source_dir = self.session_dir / "context_sources"
        source_dir.mkdir(parents=True, exist_ok=True)
        path = source_dir / f"{uuid.uuid4().hex}-{label}.txt"
        path.write_text(text, encoding="utf-8")
        character_budget = available * 4
        reference = f"\n\n[Complete source: {path}]"
        if character_budget <= len(reference):
            return reference.strip()
        return text[: character_budget - len(reference)] + reference
