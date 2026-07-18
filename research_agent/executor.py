from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
from threading import Event

from research_agent.capabilities.arxiv_reader import ArxivReaderService
from research_agent.capabilities.data_analysis import ExperimentAnalysisService
from research_agent.capabilities.charting import ChartService
from research_agent.capabilities.data_transform import DataTransformService
from research_agent.capabilities.documents import DocumentService
from research_agent.capabilities.files import FileService
from research_agent.capabilities.literature import LiteratureService
from research_agent.capabilities.quality import QualityAuditService
from research_agent.capabilities.rag import RagService
from research_agent.capabilities.references import ReferenceService
from research_agent.capabilities.writing import WritingService
from research_agent.capabilities.workspace import WorkspaceContext, WorkspaceService
from research_agent.capabilities.papers import PaperAcquisitionService
from research_agent.capabilities.web_search import HttpWebSearchService, WebSearchService
from research_agent.capabilities.code_runner import CodeRunnerService
from research_agent.capabilities.web_fetch import WebFetchService
from research_agent.capabilities.git_ops import GitService
from research_agent.capabilities.shell import ShellService
from research_agent.capabilities.officecli import OfficeCLIService
from research_agent.capabilities.office_and_md import OfficeAndMdService
from research_agent.config import AgentConfig
from research_agent.core.contracts import ContractError, has_required_artifacts, validate_arguments, validate_result_quality
from research_agent.platform_store import DEFAULT_PRIVACY, platform_setting
from research_agent.session import ChatSession
from research_agent.skill_registry import SkillRegistry


class ToolExecutor:
    SENSITIVE_EFFECTS = {
        "credential.read", "external.side_effect", "fs.delete", "fs.overwrite",
        "process.exec", "repo.write", "document.modify",
    }
    def __init__(self, config: AgentConfig, registry: SkillRegistry, session_dir: Path, cancel_event: Event | None = None):
        self.config = config
        self.registry = registry
        self.session_dir = session_dir
        self.workspace_context = WorkspaceContext.for_session(session_dir)
        workspace_root = self.workspace_context.workspace_root
        self.literature = LiteratureService(config, workspace_root, cancel_event)
        self.writing = WritingService(config, session_dir, cancel_event)
        self.files = FileService(self.workspace_context)
        self.documents = DocumentService(workspace_root)
        self.rag = RagService(config, workspace_root, cancel_event)
        self.references = ReferenceService(config, workspace_root)
        self.data = ExperimentAnalysisService(workspace_root)
        self.charts = ChartService(self.workspace_context)
        self.data_transform = DataTransformService(workspace_root)
        self.quality = QualityAuditService(session_dir)
        self.arxiv = ArxivReaderService(config, workspace_root, cancel_event)
        self.workspace = WorkspaceService(config.root_dir, session_dir, self.workspace_context)
        self.papers = PaperAcquisitionService(workspace_root)
        self.web_search = WebSearchService()
        self.http_web_search = HttpWebSearchService()
        self.code_runner = CodeRunnerService(self.workspace_context)
        self.web_fetch = WebFetchService(self.workspace_context)
        self.git = GitService(self.workspace_context)
        self.shell = ShellService(self.workspace_context)
        self.officecli = OfficeCLIService(self.workspace_context)
        self.office_md = OfficeAndMdService(workspace_root)
        self.confirmation_policies: dict[str, Callable[[dict[str, Any]], bool]] = {
            "workspace_files": self.workspace.requires_confirmation,
        }
        self.effect_policies: dict[str, Callable[[dict[str, Any]], set[str]]] = {
            "workspace_files": self.workspace.effects,
        }
        self.handlers: dict[str, Callable[[dict[str, Any], ChatSession], dict[str, Any]]] = {
            "search_literature": self._search,
            "search_openalex": lambda args, session: self._source_search("openalex", args),
            "search_pubmed": lambda args, session: self._source_search("pubmed", args),
            "search_semantic_scholar": lambda args, session: self._source_search("semantic_scholar", args),
            "search_crossref": lambda args, session: self._source_search("crossref", args),
            "search_arxiv": lambda args, session: self._source_search("arxiv", args),
            "screen_papers": self._screen,
            "summarize_papers": self._summarize,
            "analyze_experiment": self._analyze,
            "generate_chart": self._chart,
            "format_references": self._references,
            "write_review": self._review,
            "compose_manuscript": lambda args, session: self.writing.compose_manuscript(args, session.artifacts),
            "read_arxiv": lambda args, session: self.arxiv.read(args),
            "write_paper_section": lambda args, session: self.writing.transform("write_paper_section", args, session.artifacts),
            "revise_document": lambda args, session: self.writing.transform("revise_document", args, session.artifacts),
            "humanize_text": lambda args, session: self.writing.transform("humanize_text", args, session.artifacts),
            "design_visual": lambda args, session: self.writing.transform("design_visual", args, session.artifacts),
            "export_docx": lambda args, session: self.documents.export_docx(args, session.artifacts),
            "document_convert": lambda args, session: self.documents.convert(args, session.artifacts),
            "document_summary": self._document_summary,
            "register_files": lambda args, session: self.files.register(args),
            "rag_query": lambda args, session: self.rag.query(args, session.artifacts),
            "session_status": lambda args, session: self.status(session),
            "workflow_state": self._workflow_state,
            "transform_data": self._data_transform,
            "quality_audit": self._quality_audit,
            "workspace_files": lambda args, session: self.workspace.operate(args),
            "acquire_open_access_papers": self._acquire_papers,
            "create_reading_copy": lambda args, session: self.papers.reading_docx(args, session.artifacts),
            "web_search": lambda args, session: self.web_search.search(args),
            "web_search_http": lambda args, session: self.http_web_search.search(args),
            "run_code": lambda args, session: self.code_runner.run(args),
            "web_fetch": lambda args, session: self.web_fetch.fetch(args),
            "git": lambda args, session: self.git.run(args),
            "shell": lambda args, session: self.shell.run(args),
            "officecli": lambda args, session: self.officecli.run(args),
            "office_to_md": lambda args, session: self.office_md.to_markdown(args, session.artifacts),
            "md_to_office": lambda args, session: self.office_md.to_office(args, session.artifacts),
        }

    def requires_confirmation(self, skill_name: str, arguments: dict[str, Any], session: ChatSession | None = None) -> bool:
        """Return the tool-owned permission policy for this exact operation."""
        spec = self.registry.get(skill_name)
        privacy = {
            **DEFAULT_PRIVACY,
            **dict(platform_setting(self.config.runs_dir, "privacy", {}) or {}),
        }
        if not privacy["approval_required"]:
            return False
        effects = set(spec.effects)
        if spec.network_access:
            effects.add("network.read")
        if spec.write_access:
            effects.add("artifact.create")
        effect_policy = self.effect_policies.get(spec.handler or "")
        if effect_policy:
            effects.update(effect_policy(arguments))
        mode = str(getattr(session, "metadata", {}).get("approval_mode", "manual") if session else "manual")
        if mode == "auto":
            return bool(effects & self.SENSITIVE_EFFECTS)
        if effects & {"credential.read", "external.side_effect", "process.exec", "repo.write"}:
            return True
        if not spec.requires_confirmation:
            return False
        policy = self.confirmation_policies.get(spec.handler or "")
        return policy(arguments) if policy else True

    def execute(self, skill_name: str, arguments: dict[str, Any], session: ChatSession) -> dict[str, Any]:
        spec = self.registry.get(skill_name)
        if getattr(session, "status", "") == "planning":
            if spec.write_access:
                raise ValueError("规划模式不允许写操作或下载，请改用搜索或读取工具。")
        if not spec.handler:
            raise ValueError(f"Skill is design-only and cannot execute directly: {skill_name}")
        privacy = {
            **DEFAULT_PRIVACY,
            **dict(platform_setting(self.config.runs_dir, "privacy", {}) or {}),
        }
        if spec.network_access and not privacy["external_network_access"]:
            raise ValueError("权限与隐私设置已关闭外部网络访问")
        handler = self.handlers.get(spec.handler)
        if handler is None:
            raise ValueError(f"No local handler for skill: {skill_name}")
        scoped_arguments = self._scope_workspace_paths(spec.workspace_paths, arguments)
        validate_arguments(spec.input_schema, scoped_arguments)
        missing_artifacts = has_required_artifacts(session, spec.consumes, self.registry)
        if missing_artifacts:
            producers = {
                artifact_type: self.registry.producers_for(artifact_type)
                for artifact_type in missing_artifacts
            }
            raise ContractError(
                "missing_artifact",
                f"工具需要的成果物不存在: {', '.join(missing_artifacts)}",
                details={"required": missing_artifacts, "available_producers": producers},
            )
        result = handler(scoped_arguments, session)
        if not isinstance(result, dict) or "message" not in result:
            raise TypeError(f"Invalid handler result from {skill_name}")
        result.setdefault("artifacts", {})
        result.setdefault("data", {})
        outcome = str(result.get("outcome") or "success")
        if outcome not in {"success", "empty", "partial", "rate_limited", "failed", "cancelled"}:
            raise ContractError("invalid_tool_outcome", f"工具 {skill_name} 返回了未知状态: {outcome}")
        result["outcome"] = outcome
        if spec.output_schema and (
            not isinstance(result.get("message"), str)
            or not isinstance(result.get("artifacts"), dict)
            or not isinstance(result.get("data"), dict)
        ):
            raise ContractError("invalid_tool_output", f"工具 {skill_name} 返回了无效结果")
        validate_result_quality(result)
        return result

    def _scope_workspace_paths(self, fields: tuple[str, ...], arguments: dict[str, Any]) -> dict[str, Any]:
        scoped = dict(arguments)
        for field in fields:
            value = scoped.get(field)
            if value in (None, "", []):
                continue
            if isinstance(value, list):
                scoped[field] = [str(self.workspace_context.resolve(str(item))) for item in value if str(item).strip()]
            elif isinstance(value, str):
                scoped[field] = str(self.workspace_context.resolve(value))
            else:
                raise ValueError(f"{field} 必须是工作区路径或路径列表")
        return scoped

    def status(self, session: ChatSession) -> dict[str, Any]:
        lines = [
            f"会话：{session.session_id}",
            f"状态：{session.status}",
            f"消息：{len(session.messages)}",
            f"成果：{len(session.artifacts)}",
        ]
        if session.metadata.get("last_skill"):
            lines.append(f"上个 skill：{session.metadata['last_skill']}")
        if session.pending_action:
            lines.append(f"等待确认：{session.pending_action.get('skill', 'unknown')}")
        if session.artifacts:
            lines.append("最近成果：")
            lines.extend(f"- {key}: {value}" for key, value in list(session.artifacts.items())[-6:])
        return {"message": "\n".join(lines), "artifacts": {}, "data": {}}

    def _search(self, arguments: dict[str, Any], session: ChatSession) -> dict[str, Any]:
        return self.literature.search(arguments)

    def _source_search(self, source: str, arguments: dict[str, Any]) -> dict[str, Any]:
        arguments = dict(arguments)
        arguments["sources"] = [source]
        arguments["rounds"] = 1
        return self.literature.search(arguments)

    def _screen(self, arguments: dict[str, Any], session: ChatSession) -> dict[str, Any]:
        path = session.artifacts.get("active_papers")
        if not path:
            raise ValueError("当前会话没有论文池，请先检索或导入论文")
        return self.literature.screen_active(path, arguments)

    def _summarize(self, arguments: dict[str, Any], session: ChatSession) -> dict[str, Any]:
        path = session.artifacts.get("active_papers")
        if not path:
            raise ValueError("当前会话没有论文池，请先检索论文")
        return self.writing.summarize_papers(path, arguments)

    def _analyze(self, arguments: dict[str, Any], session: ChatSession) -> dict[str, Any]:
        if not arguments.get("path"):
            arguments["path"] = session.artifacts.get("latest_data", "")
        return self.data.analyze(arguments)

    def _chart(self, arguments: dict[str, Any], session: ChatSession) -> dict[str, Any]:
        if not arguments.get("path"):
            arguments["path"] = session.artifacts.get("latest_data", "")
        return self.charts.render(arguments)

    def _references(self, arguments: dict[str, Any], session: ChatSession) -> dict[str, Any]:
        if not arguments.get("path"):
            arguments["path"] = session.artifacts.get("latest_references") or session.artifacts.get("latest_document", "")
        return self.references.format(arguments, session.artifacts)

    def _document_summary(self, arguments: dict[str, Any], session: ChatSession) -> dict[str, Any]:
        return self.writing.summarize_document(self.documents.readable_text(str(arguments["path"])), arguments)

    def _review(self, arguments: dict[str, Any], session: ChatSession) -> dict[str, Any]:
        papers = session.artifacts.get("active_papers")
        if not papers:
            raise ValueError("当前会话没有论文池，请先检索论文")
        return self.writing.write_review(papers, session.artifacts.get("literature_matrix_md"), arguments)

    def _data_transform(self, arguments: dict[str, Any], session: ChatSession) -> dict[str, Any]:
        return self.data_transform.transform(arguments, session.artifacts)

    def _quality_audit(self, arguments: dict[str, Any], session: ChatSession) -> dict[str, Any]:
        return self.quality.answer(arguments, session.artifacts, session.events)

    def _acquire_papers(self, arguments: dict[str, Any], session: ChatSession) -> dict[str, Any]:
        active = session.artifacts.get("active_papers")
        if not active:
            raise ValueError("no active paper pool is available")
        return self.papers.acquire(arguments, active)

    def _workflow_state(self, arguments: dict[str, Any], session: ChatSession) -> dict[str, Any]:
        command = str(arguments.get("command") or "status").lower()
        if command == "pause":
            session.status = "paused"
            return {"message": "会话已暂停并保存。", "artifacts": {}, "data": {"status": session.status}}
        if command == "resume":
            session.status = "active"
            return {"message": "会话已恢复。", "artifacts": {}, "data": {"status": session.status}}
        if command == "change":
            if arguments.get("limit"):
                session.metadata["target_limit"] = arguments["limit"]
            session.metadata["needs_rerun_from"] = "recursive_screen"
            stale = [key for key in session.artifacts if key.startswith(("literature_matrix", "review_", "reference_", "nature_", "citation_"))]
            session.invalidated_artifacts = sorted(set(session.invalidated_artifacts + stale))
            return {
                "message": "已记录条件变更：后续会从筛选相关步骤重跑，并标记矩阵、综述、引用等下游产物需要重建。",
                "artifacts": {},
                "data": {"needs_rerun_from": "recursive_screen"},
            }
        return self.status(session)
