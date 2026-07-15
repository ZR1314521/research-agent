from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any


def _schema(properties: dict[str, str], *, required: tuple[str, ...] = (), any_of: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {name: {"type": kind} for name, kind in properties.items()},
        "required": list(required),
        "required_any_of": list(any_of),
        "additionalProperties": False,
    }


# This is intentionally data, not routing logic.  It is the executable contract
# of every public handler, shared by the prompt catalog and execution boundary.
DECLARED_CONTRACTS: dict[str, dict[str, Any]] = {
    "workflow_state": {"input_schema": _schema({"command": "string", "limit": "integer"}), "produces": ("SessionState",)},
    "search_literature": {"input_schema": _schema({"query": "string", "year_from": "integer", "year_to": "integer", "venues": "array", "sources": "array", "limit": "integer", "rounds": "integer", "max_requests_per_source": "integer", "must_include": "array", "exclude": "array", "sort_by": "string", "precise": "boolean", "output_path": "string"}, required=("query",)), "produces": ("PaperPool",), "artifact_types": {"active_papers": "ScreenedPaperPool", "raw_papers": "PaperPool", "paper_pool_markdown": "PaperPool"}},
    "search_openalex": {"input_schema": _schema({"query": "string", "year_from": "integer", "year_to": "integer", "limit": "integer", "must_include": "array", "exclude": "array", "venues": "array", "precise": "boolean"}, required=("query",)), "produces": ("PaperPool",)},
    "search_pubmed": {"input_schema": _schema({"query": "string", "year_from": "integer", "year_to": "integer", "limit": "integer", "must_include": "array", "exclude": "array", "venues": "array", "precise": "boolean"}, required=("query",)), "produces": ("PaperPool",)},
    "search_semantic_scholar": {"input_schema": _schema({"query": "string", "year_from": "integer", "year_to": "integer", "limit": "integer", "must_include": "array", "exclude": "array", "venues": "array", "precise": "boolean"}, required=("query",)), "produces": ("PaperPool",)},
    "screen_papers": {"input_schema": _schema({"query": "string", "topic": "string", "keywords": "string", "year_from": "integer", "year_to": "integer", "venues": "array", "must_include": "array", "exclude": "array", "precise": "boolean"}), "consumes": ("PaperPool",), "produces": ("ScreenedPaperPool",), "artifact_types": {"active_papers": "ScreenedPaperPool"}},
    "summarize_papers": {"input_schema": _schema({"limit": "integer"}), "consumes": ("PaperPool",), "produces": ("EvidenceMatrix",), "artifact_types": {"literature_matrix_json": "EvidenceMatrix", "literature_matrix_csv": "EvidenceMatrix", "literature_matrix_md": "EvidenceMatrix"}},
    "analyze_experiment": {"input_schema": _schema({"path": "string", "group_column": "string", "metrics": "array", "outlier_method": "string"}), "produces": ("AnalysisReport",)},
    "generate_chart": {"input_schema": _schema({"path": "string", "chart_type": "string", "x": "string", "y": "array", "group": "string", "title": "string", "x_label": "string", "y_label": "string", "output_format": "string"}, required=("chart_type", "y")), "produces": ("Image",)},
    "transform_data": {"input_schema": _schema({"path": "string", "ops": "array", "transform_ops": "array", "keep_columns": "array", "output_path": "string"}), "produces": ("Dataset",)},
    "format_references": {"input_schema": _schema({"path": "string", "styles": "array", "output_path": "string", "output_mode": "string", "convert_in_text": "boolean"}), "produces": ("ReferenceList", "NormalizedBibliography", "WordDocument"), "artifact_types": {"reference_input_normalized": "NormalizedBibliography", "references_bib": "NormalizedBibliography", "citation_check_report": "ReferenceList", "nature_document": "WordDocument"}},
    "write_review": {"input_schema": _schema({"stage": "string", "confirmed": "boolean"}), "consumes": ("EvidenceMatrix",), "produces": ("ReviewOutline", "ReviewDraft"), "artifact_types": {"review_framework": "ReviewOutline", "review_draft": "ReviewDraft"}},
    "read_arxiv": {"input_schema": _schema({"url": "string", "identifier": "string"}, any_of=("url", "identifier")), "produces": ("PaperPool",)},
    "write_paper_section": {"input_schema": _schema({"text": "string", "path": "string"}), "produces": ("ResearchText",)},
    "revise_document": {"input_schema": _schema({"text": "string", "path": "string"}), "produces": ("ResearchText",)},
    "humanize_text": {"input_schema": _schema({"text": "string", "path": "string"}), "produces": ("ResearchText",)},
    "design_visual": {"input_schema": _schema({"text": "string", "path": "string"}), "produces": ("ResearchText",)},
    "export_docx": {"input_schema": _schema({"path": "string", "output_path": "string"}), "produces": ("WordDocument",), "artifact_types": {"docx_output": "WordDocument"}},
    "document_convert": {"input_schema": _schema({"path": "string", "target_format": "string", "output_path": "string", "confirmed": "boolean"}, required=("path",)), "produces": ("WordDocument", "ResearchText"), "artifact_types": {"converted_document": "WordDocument", "conversion_report": "File"}},
    "document_summary": {"input_schema": _schema({"path": "string"}, required=("path",)), "produces": ("ResearchText",), "artifact_types": {"document_summary": "ResearchText"}},
    "register_files": {"input_schema": _schema({"paths": "array", "path": "string", "local_file_path": "string"}, any_of=("paths", "path", "local_file_path")), "produces": ("File",)},
    "rag_query": {"input_schema": _schema({"query": "string", "paths": "array", "scope": "string", "top_k": "integer"}, required=("query",)), "produces": ("EvidenceMatrix",)},
    "quality_audit": {"input_schema": _schema({}), "produces": ("AuditReport",)},
    "session_status": {"input_schema": _schema({}), "produces": ("SessionState",)},
    "workspace_files": {"input_schema": _schema({"operation": "string", "path": "string", "target_path": "string", "text": "string", "query": "string", "offset": "integer", "limit": "integer", "tail": "boolean", "max_results": "integer", "confirmed": "boolean"}, required=("operation",)), "produces": ("File",), "artifact_types": {"workspace_file": "File", "recycled_file": "File"}},
    "acquire_open_access_papers": {"input_schema": _schema({"indexes": "array", "output_dir": "string"}), "consumes": ("PaperPool",), "produces": ("OpenAccessPDF",), "artifact_types": {"open_access_manifest": "File"}},
    "create_reading_copy": {"input_schema": _schema({"output_name": "string"}), "consumes": ("OpenAccessPDF",), "produces": ("WordDocument",), "artifact_types": {"reading_copy_docx": "WordDocument"}},
    "web_search": {"input_schema": _schema({"query": "string", "site": "string", "limit": "integer"}, required=("query",)), "produces": ("WebSearchResults",)},
    "run_code": {"input_schema": _schema({"code": "string", "timeout": "integer"}, required=("code",)), "produces": ("AnalysisReport",)},
    "web_fetch": {"input_schema": _schema({"url": "string", "output_dir": "string", "timeout": "integer"}, required=("url",)), "produces": ("OpenAccessPDF", "ResearchText")},
    "git": {"input_schema": _schema({"command": "string", "cwd": "string"}, required=("command",)), "produces": ("File",)},
    "shell": {"input_schema": _schema({"command": "string"}, required=("command",)), "produces": ("File",)},
    "office_to_md": {"input_schema": _schema({"path": "string", "output_path": "string"}, required=("path",)), "produces": ("ResearchText",), "artifact_types": {"markdown_output": "ResearchText"}},
    "md_to_office": {"input_schema": _schema({"path": "string", "text": "string", "target_format": "string", "template": "string", "output_path": "string"}), "produces": ("WordDocument", "ResearchText"), "artifact_types": {"office_docx": "WordDocument", "office_pptx": "File", "office_pdf": "File"}},
}
OUTPUT_SCHEMA = {"required": ["message", "artifacts", "data"]}


@dataclass(frozen=True)
class SkillSpec:
    name: str
    kind: str
    handler: str | None
    planner_visible: bool
    description: str
    network_access: bool = False
    write_access: bool = False
    requires_confirmation: bool = False
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    consumes: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    artifact_types: dict[str, str] = field(default_factory=dict)
    idempotent: bool = True
    parallel_safe: bool = False
    direct_delivery: bool = False
    timeout_seconds: int = 60


class SkillRegistry:
    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        payload = json.loads((skills_dir / "registry.json").read_text(encoding="utf-8"))
        specs = []
        for item in payload.get("skills", []):
            spec = SkillSpec(**item)
            declared = DECLARED_CONTRACTS.get(spec.handler or "", {})
            merged = {key: value for key, value in declared.items() if not getattr(spec, key)}
            if not spec.output_schema:
                merged["output_schema"] = OUTPUT_SCHEMA
            specs.append(replace(spec, **merged))
        self._skills = {spec.name: spec for spec in specs}
        if len(self._skills) != len(specs):
            raise ValueError("Duplicate skill name in skills/registry.json")
        self.validate()

    def validate(self) -> None:
        if not self._skills:
            raise ValueError("No local skills registered")
        for spec in self._skills.values():
            skill_file = self.skills_dir / spec.name / "SKILL.md"
            if not skill_file.exists():
                raise FileNotFoundError(f"Missing local skill: {skill_file}")

    def get(self, name: str) -> SkillSpec:
        try:
            return self._skills[name]
        except KeyError as exc:
            raise KeyError(f"Unknown local skill: {name}") from exc

    def resolve(self, name: str) -> SkillSpec:
        try:
            return self.get(name)
        except KeyError:
            matches = [item for item in self._skills.values() if item.handler == name]
            if len(matches) == 1:
                return matches[0]
            raise

    def all(self) -> list[SkillSpec]:
        return list(self._skills.values())

    def planner_catalog(self) -> list[dict[str, Any]]:
        return [
            {"name": item.name, "description": item.description}
            for item in self._skills.values()
            if item.planner_visible
        ]

    def tool_catalog(self) -> list[dict[str, Any]]:
        """Declarative capability catalog for the model; execution stays local."""
        return [
            {
                "name": item.name,
                "description": item.description,
                "kind": item.kind,
                "handler": item.handler,
                "executable": bool(item.handler and item.planner_visible),
                "network_access": item.network_access,
                "write_access": item.write_access,
                "requires_confirmation": item.requires_confirmation,
                "input_schema": item.input_schema,
                "output_schema": item.output_schema,
                "consumes": list(item.consumes),
                "produces": list(item.produces),
                "idempotent": item.idempotent,
                "parallel_safe": item.parallel_safe,
                "direct_delivery": item.direct_delivery,
            }
            for item in self._skills.values()
            if item.planner_visible
        ]

    def instructions(self, name: str) -> str:
        self.get(name)
        return (self.skills_dir / name / "SKILL.md").read_text(encoding="utf-8")
