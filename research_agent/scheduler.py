from __future__ import annotations

import threading
import time
from typing import Any

from research_agent.platform_store import PlatformStore
from research_agent.turns import TERMINAL_STATES, ActiveTurnError, TurnCoordinator


class ScheduleService:
    """Small single-process scheduler for the local FastAPI runtime."""

    def __init__(self, agent: Any, coordinator: TurnCoordinator, store: PlatformStore, poll_seconds: float = 1.0):
        self.agent = agent
        self.coordinator = coordinator
        self.store = store
        self.poll_seconds = max(0.2, float(poll_seconds))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._workers: set[threading.Thread] = set()
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.store.mark_overdue_missed()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="research-agent-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop.wait(self.poll_seconds):
            try:
                for schedule in self.store.claim_due_schedules():
                    self._launch(schedule)
            except Exception:
                # A malformed schedule or transient SQLite lock must not stop future plans.
                continue

    def run_now(self, schedule_id: str) -> dict[str, Any]:
        schedule = self.store.begin_manual_schedule_run(schedule_id)
        self._launch(schedule)
        return schedule

    def _launch(self, schedule: dict[str, Any]) -> None:
        worker = threading.Thread(
            target=self._execute,
            args=(schedule,),
            name=f"schedule-{schedule['id'][-8:]}",
            daemon=True,
        )
        with self._lock:
            self._workers.add(worker)
        worker.start()

    def _execute(self, schedule: dict[str, Any]) -> None:
        execution_id = schedule["execution_id"]
        schedule_id = schedule["id"]
        run_id = ""
        try:
            session = self.agent.new_session()
            run_id = session.session_id
            self.store.update_schedule_execution(
                execution_id, schedule_id, "running", run_id=run_id
            )
            try:
                control = self.coordinator.start(run_id, schedule["prompt"])
            except ActiveTurnError as error:
                raise RuntimeError(str(error)) from error

            waiting_recorded = False
            while control.state not in TERMINAL_STATES and not self._stop.is_set():
                if control.state == "waiting_approval" and not waiting_recorded:
                    self.store.update_schedule_execution(
                        execution_id, schedule_id, "waiting_approval", run_id=run_id
                    )
                    waiting_recorded = True
                time.sleep(0.25)

            if control.state == "completed":
                payload_status = str((control.final_payload or {}).get("status") or "completed")
                status = "failed" if payload_status == "failed" else "completed"
                error = str((control.final_payload or {}).get("error") or "")
            elif control.state == "cancelled":
                status, error = "cancelled", "任务已取消"
            else:
                status = "failed"
                error = str((control.final_payload or {}).get("error") or "任务执行失败")
            self.store.update_schedule_execution(
                execution_id, schedule_id, status, run_id=run_id, error=error, finished=True
            )
        except Exception as error:
            self.store.update_schedule_execution(
                execution_id,
                schedule_id,
                "failed",
                run_id=run_id,
                error=f"{type(error).__name__}: {error}",
                finished=True,
            )
        finally:
            current = threading.current_thread()
            with self._lock:
                self._workers.discard(current)
