from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


class StepStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    NEEDS_USER = "needs_user"
    BLOCKED = "blocked"
    FAILED = "failed"


DEFAULT_STEPS = [
    "upload",
    "literature_search",
    "recursive_screen",
    "matrix_extract",
    "rag_build",
    "review_draft",
    "experiment_analysis",
    "reference_format",
    "final_review",
]


@dataclass
class RunState:
    run_id: str
    topic: str
    keywords: str = ""
    venues: str = ""
    year_from: int | None = None
    year_to: int | None = None
    status: str = "initialized"
    current_step: str = "upload"
    pending_steps: list[str] = field(default_factory=lambda: list(DEFAULT_STEPS))
    completed_steps: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    checkpoints: list[dict[str, Any]] = field(default_factory=list)
    human_decisions: list[dict[str, Any]] = field(default_factory=list)
    execution_log: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        topic: str,
        keywords: str = "",
        venues: str = "",
        year_from: int | None = None,
        year_to: int | None = None,
        run_id: str | None = None,
    ) -> "RunState":
        state = cls(
            run_id=run_id or time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8],
            topic=topic,
            keywords=keywords,
            venues=venues,
            year_from=year_from,
            year_to=year_to,
        )
        state.log("init", StepStatus.COMPLETED, "Run initialized")
        return state

    @classmethod
    def load(cls, path: Path) -> "RunState":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**data)

    def save(self, run_dir: Path) -> Path:
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / "workflow_state.json"
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def log(self, step: str, status: str, summary: str = "", **extra: Any) -> None:
        item = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "step": step,
            "status": status,
            "summary": summary,
        }
        item.update(extra)
        self.execution_log.append(item)

    def mark_running(self, step: str) -> None:
        self.current_step = step
        self.status = StepStatus.RUNNING
        self.log(step, StepStatus.RUNNING)

    def mark_completed(self, step: str, summary: str = "") -> None:
        self.current_step = step
        self.status = StepStatus.COMPLETED
        if step not in self.completed_steps:
            self.completed_steps.append(step)
        self.pending_steps = [s for s in self.pending_steps if s != step]
        self.log(step, StepStatus.COMPLETED, summary)

    def mark_failed(self, step: str, message: str) -> None:
        self.current_step = step
        self.status = StepStatus.FAILED
        self.errors.append({"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "step": step, "message": message})
        self.log(step, StepStatus.FAILED, message)

    def add_artifact(self, key: str, path: Path | str) -> None:
        self.artifacts[key] = str(path)

    def add_checkpoint(self, step: str, prompt: str, payload: dict[str, Any] | None = None) -> None:
        self.current_step = step
        self.status = StepStatus.NEEDS_USER
        self.checkpoints.append(
            {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "step": step,
                "prompt": prompt,
                "payload": payload or {},
                "resolved": False,
            }
        )
        self.log(step, StepStatus.NEEDS_USER, prompt)

    def add_decision(self, step: str, decision: str) -> None:
        self.human_decisions.append(
            {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "step": step, "decision": decision}
        )
        for checkpoint in reversed(self.checkpoints):
            if checkpoint.get("step") == step and not checkpoint.get("resolved"):
                checkpoint["resolved"] = True
                checkpoint["decision"] = decision
                break
        self.log(step, "decision", decision)
