from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class ModelCallLogger:
    def __init__(self, run_dir: Path):
        self.path = run_dir / "model_call_log.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        *,
        provider: str,
        model: str,
        operation: str,
        prompt: str,
        response: str = "",
        status: str = "completed",
        error: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        record = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "provider": provider,
            "model": model,
            "operation": operation,
            "prompt_chars": len(prompt),
            "response_chars": len(response),
            "prompt_preview": prompt[:500],
            "response_preview": response[:500],
            "status": status,
            "error": error,
            "metadata": metadata or {},
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
