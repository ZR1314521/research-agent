from __future__ import annotations

import atexit
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
import urllib.error
import urllib.request

from research_agent.chat import ResearchChatAgent
from research_agent.config import _load_dotenv
from research_agent.core.contracts import public_artifacts, refresh_artifact_profiles, register_artifacts
from research_agent.executor import ToolExecutor
from research_agent.version import RUNTIME_VERSION
from research_agent.provider_runtime import CallLedger
from research_agent.platform_store import PlatformStore
from research_agent.scheduler import ScheduleService
from research_agent.turns import ActiveTurnError, TurnCoordinator
from research_agent.usage import UsageService


try:
    from fastapi import FastAPI, File, HTTPException, Request, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, StreamingResponse
    from pydantic import BaseModel
except Exception:  # pragma: no cover - supports the terminal-only installation
    FastAPI = None
    BaseModel = object


class ChatRequest(BaseModel):
    message: str
    session_id: str = ""
    resume_latest: bool = True


class RunCreateRequest(BaseModel):
    run_id: str = ""


class MessageRequest(BaseModel):
    message: str


def create_app(agent: ResearchChatAgent | None = None) -> Any:
    """Create the localhost-only workbench API without optional multipart/http clients."""
    if FastAPI is None:
        raise RuntimeError("FastAPI is not installed. Install fastapi and uvicorn to run the HTTP API.")
    owns_agent = agent is None
    agent = agent or ResearchChatAgent()
    coordinator = TurnCoordinator(agent)
    platform_store = PlatformStore(agent.config.runs_dir)
    usage_service = UsageService(agent.config.runs_dir, platform_store)
    schedule_service = ScheduleService(agent, coordinator, platform_store)

    @asynccontextmanager
    async def lifespan(_app):
        schedule_service.start()
        try:
            yield
        finally:
            schedule_service.stop()
            if owns_agent:
                agent.close()

    app = FastAPI(title="AI Research Agent", version=RUNTIME_VERSION, lifespan=lifespan)
    app.state.platform_store = platform_store
    app.state.agent = agent
    app.state.usage_service = usage_service
    app.state.schedule_service = schedule_service
    app.state.turn_coordinator = coordinator
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    def load_run(run_id: str):
        try:
            session = agent.sessions.load(run_id)
            if refresh_artifact_profiles(session, agent.registry):
                agent.sessions.save(session)
            return session
        except (FileNotFoundError, ValueError) as error:
            raise HTTPException(status_code=404, detail="Run not found") from error

    def payload_or_400(action):
        try:
            return action()
        except KeyError as error:
            raise HTTPException(status_code=404, detail="记录不存在") from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    async def save_upload(run_id: str, files: list[UploadFile]) -> dict[str, Any]:
        session = load_run(run_id)
        incoming = agent.sessions.directory(run_id) / "incoming_uploads"
        incoming.mkdir(parents=True, exist_ok=True)
        paths: list[str] = []
        for upload in files:
            path = incoming / Path(upload.filename or "upload.bin").name
            path.write_bytes(await upload.read())
            paths.append(str(path))
        executor = ToolExecutor(agent.config, agent.registry, agent.sessions.directory(run_id))
        result = executor.execute("file-upload-router", {"paths": paths}, session)
        session.artifacts.update({key: str(value) for key, value in result["artifacts"].items()})
        register_artifacts(session, agent.registry.get("file-upload-router"), result["artifacts"])
        agent.sessions.event(session, "tool_observed", "file-upload-router", result["message"], ok=True)
        session.metadata["last_upload"] = result.get("message", "")
        agent.sessions.save(session)
        return {**result, **_run_payload(session)}

    @app.post("/setup/apply")
    async def setup_apply(request: Request):
        body = await request.json()
        updates = {}
        for key in ("llm_provider", "llm_model", "llm_base_url", "llm_api_key"):
            val = str(body.get(key, "")).strip()
            if val:
                updates[key] = val
        numeric_fields = {
            "context_window": (0, None),
            "llm_timeout": (5, None),
            "max_concurrency": (1, 10),
        }
        numeric_values: dict[str, str] = {}
        for key, (minimum, maximum) in numeric_fields.items():
            raw = str(body.get(key, "")).strip()
            if not raw:
                continue
            try:
                value = int(raw)
            except ValueError as error:
                raise HTTPException(400, f"{key} must be an integer") from error
            if value < minimum or (maximum is not None and value > maximum):
                raise HTTPException(400, f"{key} is outside the supported range")
            numeric_values[key] = str(value)
        if not updates and not numeric_values:
            raise HTTPException(400, "no fields to update")
        env_path = agent.config.root_dir / ".env"
        env_map = {"RESEARCH_AGENT_LLM_PROVIDER": updates.get("llm_provider", ""),
                   "RESEARCH_AGENT_LLM_MODEL": updates.get("llm_model", ""),
                   "RESEARCH_AGENT_LLM_BASE_URL": updates.get("llm_base_url", ""),
                   "RESEARCH_AGENT_LLM_API_KEY": updates.get("llm_api_key", ""),
                   "RESEARCH_AGENT_CONTEXT_WINDOW": numeric_values.get("context_window", ""),
                   "RESEARCH_AGENT_LLM_TIMEOUT": numeric_values.get("llm_timeout", ""),
                   "RESEARCH_AGENT_PROVIDER_MAX_CONCURRENCY": numeric_values.get("max_concurrency", "")}
        if env_path.exists():
            lines = env_path.read_text(encoding="utf-8").splitlines()
            new_lines = []
            written: set[str] = set()
            for line in lines:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    new_lines.append(line)
                    continue
                for env_name, new_val in env_map.items():
                    if stripped.startswith(env_name + "=") and new_val:
                        new_lines.append(f"{env_name}={new_val}")
                        written.add(env_name)
                        break
                else:
                    new_lines.append(line)
            new_lines.extend(
                f"{name}={value}" for name, value in env_map.items() if value and name not in written
            )
            env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        else:
            env_path.write_text("\n".join(f"{k}={v}" for k, v in env_map.items() if v) + "\n", encoding="utf-8")
        return {"written": True}

    @app.get("/setup/presets")
    def setup_presets():
        return [
            {"name": "DeepSeek", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-v4-pro", "context": 1000000},
            {"name": "OpenAI", "base_url": "https://api.openai.com/v1", "model": "gpt-4o", "context": 128000},
            {"name": "Qwen (通义千问)", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-max", "context": 131072},
            {"name": "Moonshot (月之暗面)", "base_url": "https://api.moonshot.cn/v1", "model": "moonshot-v1-128k", "context": 128000},
            {"name": "Zhipu (智谱)", "base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4-plus", "context": 128000},
            {"name": "Custom", "base_url": "", "model": "", "context": 0},
        ]

    @app.get("/usage")
    def usage_report(
        provider: str = "",
        model: str = "",
        status: str = "",
        date_from: str = "",
        date_to: str = "",
        limit: int = 200,
    ):
        return usage_service.report(
            provider=provider,
            model=model,
            status=status,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )

    @app.get("/data-sources")
    def data_sources():
        return platform_store.list_data_sources()

    @app.post("/data-sources")
    async def create_data_source(request: Request):
        body = await request.json()
        return payload_or_400(lambda: platform_store.create_data_source(body))

    @app.post("/data-sources/{source_id}")
    async def update_data_source(source_id: str, request: Request):
        body = await request.json()
        return payload_or_400(lambda: platform_store.update_data_source(source_id, body))

    @app.post("/data-sources/{source_id}/delete")
    def delete_data_source(source_id: str):
        return {"deleted": payload_or_400(lambda: platform_store.delete_data_source(source_id))}

    @app.post("/data-sources/{source_id}/check")
    def check_data_source(source_id: str):
        if not platform_store.privacy()["external_network_access"]:
            raise HTTPException(status_code=403, detail="权限与隐私设置已关闭外部网络访问")
        try:
            source = platform_store.get_data_source(source_id)
            url = platform_store.source_check_url(source_id)
            request = urllib.request.Request(url, headers={"User-Agent": "Research-Agent/0.6"})
            try:
                with urllib.request.urlopen(request, timeout=8) as response:
                    status_code = int(getattr(response, "status", 200))
                    response.read(1)
                ok = status_code < 500
                message = f"连接正常（HTTP {status_code}）"
            except urllib.error.HTTPError as error:
                ok = error.code < 500
                message = f"地址可访问（HTTP {error.code}）" if ok else f"连接失败（HTTP {error.code}）"
            if ok and source["kind"] == "paid":
                message += "；凭据已本机加密，专属登录连接器待后续接入"
            return platform_store.record_source_check(source_id, ok, message)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="数据源不存在") from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            message = f"连接失败：{getattr(error, 'reason', error)}"
            return platform_store.record_source_check(source_id, False, message)

    @app.get("/settings/privacy")
    def privacy_settings():
        return platform_store.privacy()

    @app.post("/settings/privacy")
    async def update_privacy(request: Request):
        body = await request.json()
        value = payload_or_400(lambda: platform_store.save_privacy(body))
        removed = usage_service.prune(value["log_retention_days"])
        return {**value, "pruned_records": removed}

    @app.get("/settings/account")
    def account_settings():
        return platform_store.account()

    @app.post("/settings/account")
    async def update_account(request: Request):
        body = await request.json()
        return platform_store.save_account(body)

    @app.post("/settings/clear-logs")
    def clear_usage_logs():
        return {"cleared_files": usage_service.clear()}

    @app.get("/settings/approvals")
    def approval_history(limit: int = 100):
        items: list[dict[str, Any]] = []
        sessions_root = agent.config.runs_dir / "sessions"
        if sessions_root.exists():
            for path in sorted(sessions_root.glob("*/session.json"), key=lambda item: item.stat().st_mtime, reverse=True):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                for event in reversed(data.get("events") or []):
                    if event.get("event") not in {"approval_requested", "approval_resolved"}:
                        continue
                    items.append({
                        "run_id": path.parent.name,
                        "time": event.get("timestamp", ""),
                        "event": event.get("event", ""),
                        "skill": event.get("skill", ""),
                        "summary": event.get("summary", ""),
                        "approved": event.get("approved"),
                    })
                    if len(items) >= max(1, min(500, int(limit))):
                        return items
        return items

    @app.get("/schedules")
    def schedules():
        return platform_store.list_schedules()

    @app.post("/schedules")
    async def create_schedule(request: Request):
        body = await request.json()
        return payload_or_400(lambda: platform_store.create_schedule(body))

    @app.post("/schedules/{schedule_id}")
    async def update_schedule(schedule_id: str, request: Request):
        body = await request.json()
        return payload_or_400(lambda: platform_store.update_schedule(schedule_id, body))

    @app.post("/schedules/{schedule_id}/delete")
    def delete_schedule(schedule_id: str):
        return {"deleted": platform_store.delete_schedule(schedule_id)}

    @app.post("/schedules/{schedule_id}/run")
    def run_schedule_now(schedule_id: str):
        return payload_or_400(lambda: schedule_service.run_now(schedule_id))

    @app.get("/schedule-runs")
    def schedule_runs(schedule_id: str = "", limit: int = 100):
        return platform_store.schedule_runs(schedule_id, limit)

    @app.get("/sessions")
    def list_sessions():
        sessions_dir = agent.config.runs_dir / "sessions"
        if not sessions_dir.exists():
            return []
        result = []
        for d in sorted(sessions_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not d.is_dir(): continue
            sj = d / "session.json"
            if not sj.exists(): continue
            try:
                data = json.loads(sj.read_text(encoding="utf-8"))
                title = (data.get("goal") or data.get("metadata", {}).get("current_goal") or "")
                if not title and data.get("messages"):
                    first = data["messages"][0].get("content", "")[:60]
                    title = first
                active = coordinator.active(d.name)
                public_status = _public_status(
                    data.get("status", ""),
                    data.get("pending_action"),
                    active.state if active else "",
                )
                result.append({
                    "run_id": d.name,
                    "created_at": data.get("created_at", ""),
                    "updated_at": data.get("updated_at", ""),
                    "status": public_status,
                    "session_status": data.get("status", ""),
                    "progress": 100 if public_status == "completed" else None,
                    "title": title or "new session",
                })
            except Exception:
                result.append({"run_id": d.name, "title": "unreadable", "status": "error"})
        return result[:50]

    @app.get("/styles")
    def list_styles():
        profiles = json.loads((agent.config.rules_dir / "style_profiles.json").read_text(encoding="utf-8"))
        groups: dict[str, list] = {}
        for p in profiles:
            g = p.get("group", "其他")
            groups.setdefault(g, []).append({"key": p["key"], "name": p.get("display_name", p["key"])})
        return [{"group": k, "items": v} for k, v in groups.items()]

    @app.get("/health")
    def health():
        config = agent.config
        return {
            "status": "ok",
            "version": RUNTIME_VERSION,
            "bind_host": "127.0.0.1",
            "public_network": False,
            "llm_configured": config.llm_configured,
            "provider": config.llm_provider,
            "model": config.llm_model,
            "context_window": config.context_window,
        }

    @app.get("/quality/outcomes")
    def quality_outcomes():
        path = agent.outcomes.report_path
        return {
            "report_path": str(path),
            "markdown": path.read_text(encoding="utf-8") if path.exists() else "# 用户结果验收报告\n\n尚无记录。\n",
        }

    @app.post("/runs")
    def create_run(request: RunCreateRequest):
        session = load_run(request.run_id) if request.run_id else agent.new_session()
        if not request.run_id:
            agent.sessions.event(session, "run_created", summary="localhost workbench run created")
        return _run_payload(session)

    @app.post("/runs/{run_id}/trim/{index}")
    def trim_message(run_id: str, index: int):
        session = load_run(run_id)
        if 0 <= index < len(session.messages):
            session.messages.pop(index)
            # Rebuild model_messages from the trimmed messages so the
            # deleted content does not persist in the LLM context.
            session.model_messages.clear()
            agent.sessions.save(session)
            return {"trimmed": True, "index": index}
        return {"trimmed": False, "detail": "index out of range"}

    @app.post("/runs/{run_id}/delete")
    def delete_run(run_id: str):
        import shutil
        session_dir = agent.config.runs_dir / "sessions" / run_id
        if session_dir.exists():
            shutil.rmtree(session_dir)
            return {"deleted": True, "run_id": run_id}
        return {"deleted": False, "run_id": run_id, "detail": "not found"}

    @app.post("/runs/{run_id}/cancel")
    def cancel_run(run_id: str):
        session = load_run(run_id)
        state = coordinator.cancel(run_id)
        if state == "cancelled":
            session.status = "waiting_user"
            session.pending_action = {"type": "cancelled"}
            app.state.agent.sessions.event(session, "cancel_requested", summary="user cancelled active turn")
            app.state.agent.sessions.save(session)
        return {"cancelled": state == "cancelled", "run_id": run_id, "status": state}

    @app.post("/runs/{run_id}/pause")
    def pause_run(run_id: str):
        load_run(run_id)
        return {"run_id": run_id, "status": coordinator.pause(run_id)}

    @app.post("/runs/{run_id}/resume")
    def resume_run(run_id: str):
        load_run(run_id)
        return {"run_id": run_id, "status": coordinator.resume(run_id)}

    @app.post("/runs/{run_id}/intervene")
    def intervene_run(run_id: str, request: MessageRequest):
        load_run(run_id)
        active = coordinator.active(run_id)
        if not active or active.state not in {"paused", "pause_requested"}:
            raise HTTPException(status_code=409, detail="Run is not paused")
        return {
            "run_id": run_id,
            "turn_id": active.turn_id,
            "status": coordinator.intervene(run_id, request.message),
        }

    @app.get("/runs/{run_id}")
    def run_status(run_id: str):
        session = load_run(run_id)
        active = coordinator.active(run_id)
        payload = _run_payload(session, active.state if active else "")
        payload["active_turn"] = ({"turn_id": active.turn_id, "status": active.state} if active else None)
        return payload

    @app.get("/runs/{run_id}/artifacts/{artifact_name}")
    def run_artifact(run_id: str, artifact_name: str):
        session = load_run(run_id)
        record = session.artifact_records.get(artifact_name)
        if not record:
            raise HTTPException(status_code=404, detail="Artifact not found")
        path = Path(str(record.get("path") or "")).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="Artifact file not found")
        return FileResponse(path)

    @app.post("/runs/{run_id}/messages")
    def submit_message(run_id: str, request: MessageRequest):
        session = load_run(run_id)
        agent.sessions.event(session, "message_submitted", summary=request.message[:300])
        try:
            control = coordinator.start(run_id, request.message)
        except ActiveTurnError as error:
            raise HTTPException(status_code=409, detail={"message": str(error), "turn_id": error.turn_id}) from error
        control.wait_for_result_boundary()
        current = load_run(run_id)
        final = control.final_payload or {}
        return {
            **_run_payload(current),
            "assistant_message": final.get("assistant_message") or _run_payload(current)["latest_assistant_message"],
            "skill": final.get("skill", ""),
            "turn_id": control.turn_id,
            "turn_status": control.state,
        }

    @app.post("/runs/{run_id}/turns/stream")
    def stream_turn(run_id: str, request: MessageRequest):
        session = load_run(run_id)
        agent.sessions.event(session, "message_submitted", summary=request.message[:300])
        try:
            control = coordinator.start(run_id, request.message)
        except ActiveTurnError as error:
            raise HTTPException(status_code=409, detail={"message": str(error), "turn_id": error.turn_id}) from error

        def lines():
            for item in control.stream():
                yield json.dumps(item, ensure_ascii=False, default=str) + "\n"

        return StreamingResponse(lines(), media_type="application/x-ndjson", headers={"Cache-Control": "no-cache"})

    @app.get("/runs/{run_id}/turns/{turn_id}/events")
    def reconnect_turn(run_id: str, turn_id: str, after: int = 0):
        load_run(run_id)
        try:
            control = coordinator.get(turn_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Turn not found") from error
        if control.run_id != run_id:
            raise HTTPException(status_code=404, detail="Turn not found")

        def lines():
            for item in control.stream(after=after):
                yield json.dumps(item, ensure_ascii=False, default=str) + "\n"

        return StreamingResponse(lines(), media_type="application/x-ndjson", headers={"Cache-Control": "no-cache"})

    @app.get("/runs/{run_id}/provider-calls")
    def provider_calls(run_id: str):
        load_run(run_id)
        return CallLedger(agent.sessions.directory(run_id)).records()

    @app.post("/runs/{run_id}/approve")
    def approve_pending(run_id: str):
        active = coordinator.active(run_id)
        if active and active.state == "waiting_approval":
            coordinator.approve(run_id, True)
            boundary = active.wait_for_result_boundary()
            current = load_run(run_id)
            final = active.final_payload or {}
            # When the turn hit another approval boundary (nested),
            # final_payload is still empty — use the session state instead.
            assistant = final.get("assistant_message") or current.metadata.get("last_approval_message", "")
            return {**_run_payload(current), "assistant_message": assistant, "skill": final.get("skill", ""), "turn_id": active.turn_id, "turn_status": boundary}
        response = agent.resolve_pending(load_run(run_id), True)
        return {**_run_payload(response.session), "assistant_message": response.message, "skill": response.skill}

    @app.post("/runs/{run_id}/reject")
    def reject_pending(run_id: str):
        active = coordinator.active(run_id)
        if active and active.state == "waiting_approval":
            coordinator.approve(run_id, False)
            boundary = active.wait_for_result_boundary()
            current = load_run(run_id)
            final = active.final_payload or {}
            assistant = final.get("assistant_message") or current.metadata.get("last_approval_message", "")
            return {**_run_payload(current), "assistant_message": assistant, "skill": final.get("skill", ""), "turn_id": active.turn_id, "turn_status": boundary}
        response = agent.resolve_pending(load_run(run_id), False)
        return {**_run_payload(response.session), "assistant_message": response.message, "skill": response.skill}

    @app.get("/runs/{run_id}/events.json")
    def run_events_json(run_id: str, after: int = 0):
        session = load_run(run_id)
        items = []
        for sequence, item in enumerate(session.events, start=1):
            if sequence > max(after, 0):
                items.append({"sequence": sequence, **item})
        return items

    @app.get("/runs/{run_id}/events")
    def run_events(run_id: str, after: int = 0, follow: bool = False):
        import time as _time

        def lines():
            seen = max(after, 0)
            while True:
                session = load_run(run_id)
                for sequence, item in enumerate(session.events, start=1):
                    if sequence > seen:
                        payload = {"sequence": sequence, **item}
                        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                        seen = sequence
                if not follow:
                    return
                _time.sleep(0.5)

        return StreamingResponse(lines(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.post("/runs/{run_id}/files")
    async def upload_run_file(run_id: str, files: list[UploadFile] = File(...)):
        return await save_upload(run_id, files)

    @app.post("/chat")
    def chat(request: ChatRequest):
        session = agent.load_or_create(request.session_id, resume_latest=request.resume_latest)
        try:
            control = coordinator.start(session.session_id, request.message)
        except ActiveTurnError as error:
            raise HTTPException(status_code=409, detail={"message": str(error), "turn_id": error.turn_id}) from error
        control.wait_for_result_boundary()
        current = load_run(session.session_id)
        final = control.final_payload or {}
        return {
            "session_id": current.session_id,
            "message": final.get("assistant_message") or _run_payload(current)["latest_assistant_message"],
            "skill": final.get("skill", ""),
            "status": current.status,
            "waiting": bool(current.pending_action),
            "events": current.events[-20:],
            "artifacts": current.artifact_records,
            "task_ledger": current.task_ledger[-12:],
            "outcome_report": current.metadata.get("outcome_report", ""),
            "turn_id": control.turn_id,
            "turn_status": control.state,
        }

    @app.post("/chat/stream")
    def chat_stream(request: ChatRequest):
        session = agent.load_or_create(request.session_id, resume_latest=request.resume_latest)
        try:
            control = coordinator.start(session.session_id, request.message)
        except ActiveTurnError as error:
            raise HTTPException(status_code=409, detail={"message": str(error), "turn_id": error.turn_id}) from error

        def lines():
            for item in control.stream():
                yield json.dumps(item, ensure_ascii=False) + "\n"

        return StreamingResponse(lines(), media_type="application/x-ndjson")

    @app.post("/sessions/{session_id}/files")
    async def upload_files(session_id: str, files: list[UploadFile] = File(...)):
        return await save_upload(session_id, files)

    @app.get("/sessions/{session_id}")
    def session_status(session_id: str):
        return load_run(session_id).__dict__

    @app.get("/sessions/{session_id}/events")
    def session_events(session_id: str):
        return load_run(session_id).events

    @app.post("/sessions/{session_id}/resume")
    def session_resume(session_id: str, request: ChatRequest):
        load_run(session_id)
        try:
            control = coordinator.start(session_id, request.message)
        except ActiveTurnError as error:
            raise HTTPException(status_code=409, detail={"message": str(error), "turn_id": error.turn_id}) from error
        control.wait_for_result_boundary()
        current = load_run(session_id)
        final = control.final_payload or {}
        return {
            "session_id": session_id,
            "message": final.get("assistant_message") or _run_payload(current)["latest_assistant_message"],
            "status": current.status,
            "waiting": bool(current.pending_action),
            "turn_id": control.turn_id,
            "turn_status": control.state,
        }

    @app.post("/sessions/{session_id}/reset")
    def session_reset(session_id: str):
        session = agent.sessions.reset_context(load_run(session_id))
        return {"session_id": session.session_id, "status": session.status, "message": "context reset"}

    return app


def _public_status(session_status: str, pending_action: Any = None, active_turn_status: str = "") -> str:
    if active_turn_status:
        return active_turn_status
    pending_type = pending_action.get("type") if isinstance(pending_action, dict) else ""
    if pending_type in {"tool_approval", "plan_approval"}:
        return "waiting_approval"
    if pending_type == "cancelled":
        return "cancelled"
    status = str(session_status or "").lower()
    if status == "active":
        return "idle"
    return status or "idle"


def _workflow_projection(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for sequence, event in enumerate(events, start=1):
        event_type = str(event.get("event") or "")
        skill = str(event.get("skill") or "")
        if event_type == "tool_requested":
            steps.append({
                "id": f"tool-{sequence}",
                "skill": skill,
                "status": "queued",
                "summary": "",
                "turn": event.get("turn"),
                "started_at": event.get("timestamp", ""),
            })
            continue
        if event_type in {"cancelled", "failed"}:
            terminal_status = "cancelled" if event_type == "cancelled" else "failed"
            for item in steps:
                if item["status"] in {"queued", "running"}:
                    item["status"] = terminal_status
                    item["finished_at"] = event.get("timestamp", "")
            continue
        if event_type not in {"tool_started", "tool_observed"}:
            continue
        step = next(
            (item for item in reversed(steps) if item["skill"] == skill and item["status"] != "completed"),
            None,
        )
        if step is None:
            step = {
                "id": f"tool-{sequence}", "skill": skill, "status": "queued",
                "summary": "", "turn": event.get("turn"), "started_at": event.get("timestamp", ""),
            }
            steps.append(step)
        if event_type == "tool_started":
            step["status"] = "running"
        else:
            step["status"] = "completed" if event.get("ok", True) else "failed"
            step["summary"] = str(event.get("summary") or "")
            step["finished_at"] = event.get("timestamp", "")
    return steps[-50:]


def _run_payload(session: Any, active_turn_status: str = "") -> dict[str, Any]:
    latest_assistant = next((item["content"] for item in reversed(session.messages) if item.get("role") == "assistant"), "")
    start = max(1, len(session.events) - 49)
    events = [{"sequence": sequence, **item} for sequence, item in enumerate(session.events[-50:], start=start)]
    context_size = 0
    log = Path(__file__).resolve().parents[1] / "runs" / "sessions" / session.session_id / "provider_calls.jsonl"
    if log.exists():
        for line in log.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.strip(): continue
            try:
                call = json.loads(line)
                prompt = call.get("usage", {}).get("prompt_tokens", 0)
                if prompt:
                    context_size = prompt
            except Exception: pass
    window = max(0, int(_load_dotenv(Path(__file__).resolve().parents[1] / ".env").get("RESEARCH_AGENT_CONTEXT_WINDOW", "") or 0))
    public_status = _public_status(session.status, session.pending_action, active_turn_status)
    return {
        "run_id": session.session_id,
        "session_id": session.session_id,
        "status": public_status,
        "session_status": session.status,
        "progress": 100 if public_status == "completed" else None,
        "created_at": session.created_at,
        "events": events,
        "artifacts": public_artifacts(session.artifact_records),
        "latest_assistant_message": latest_assistant,
        "pending_action": session.pending_action,
        "plan_mode": session.metadata.get("plan_mode", False),
        "context_size": context_size,
        "window_size": window,
        "messages": [{"role": m.get("role"), "content": m.get("content", "")} for m in session.messages[-30:]],
        "outcome_report": session.metadata.get("outcome_report", ""),
        "workflow_steps": _workflow_projection(session.events),
    }


def _chat_payload(response: Any) -> dict[str, Any]:
    session = response.session
    return {
        "session_id": session.session_id,
        "message": response.message,
        "skill": response.skill,
        "status": session.status,
        "waiting": bool(session.pending_action),
        "events": session.events[-20:],
        "artifacts": public_artifacts(session.artifact_records),
        "task_ledger": session.task_ledger[-12:],
        "outcome_report": session.metadata.get("outcome_report", ""),
    }


app = create_app() if FastAPI is not None else None
if app is not None:
    atexit.register(app.state.agent.close)
