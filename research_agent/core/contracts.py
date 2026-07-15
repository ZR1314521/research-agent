from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any


class ContractError(ValueError):
    """A recoverable tool-boundary error that the model can act on."""

    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}

    def as_observation(self, tool: str) -> dict[str, Any]:
        return {"ok": False, "tool": tool, "error": str(self), "error_code": self.code, "details": self.details}


@dataclass(frozen=True)
class ToolContract:
    """Small, local contract used at the only tool execution boundary."""

    input_schema: dict[str, Any] = field(default_factory=dict)
    consumes: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    artifact_types: dict[str, str] = field(default_factory=dict)
    idempotent: bool = True
    timeout_seconds: int = 60


def validate_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> None:
    if not schema:
        return
    properties = schema.get("properties") or {}
    internal = {"request", "no_network"}
    unknown = sorted(set(arguments) - set(properties) - internal)
    if unknown and schema.get("additionalProperties", False) is False:
        raise ContractError(
            "unknown_argument",
            f"工具不接受参数: {', '.join(unknown)}",
            details={"allowed": sorted(properties), "unknown": unknown},
        )
    missing = [name for name in schema.get("required", []) if arguments.get(name) in (None, "", [])]
    if missing:
        raise ContractError("missing_argument", f"工具缺少必填参数: {', '.join(missing)}", details={"missing": missing})
    any_of = schema.get("required_any_of") or []
    if any_of and not any(arguments.get(name) not in (None, "", []) for name in any_of):
        raise ContractError("missing_argument", f"工具至少需要一个参数: {', '.join(any_of)}", details={"one_of": any_of})
    for name, value in arguments.items():
        if name not in properties or value is None:
            continue
        expected = properties[name].get("type")
        if expected == "string" and not isinstance(value, str):
            raise ContractError("invalid_argument_type", f"参数 {name} 必须是字符串")
        if expected == "array" and not isinstance(value, list):
            raise ContractError("invalid_argument_type", f"参数 {name} 必须是数组")
        if expected == "boolean" and not isinstance(value, bool):
            raise ContractError("invalid_argument_type", f"参数 {name} 必须是布尔值")
        if expected == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
            raise ContractError("invalid_argument_type", f"参数 {name} 必须是整数")


def classify_artifact(key: str, value: str, declared: dict[str, str]) -> str:
    if key in declared:
        return declared[key]
    suffix = Path(value).suffix.lower()
    if suffix == ".docx":
        return "WordDocument"
    if suffix in {".png", ".svg", ".jpg", ".jpeg", ".webp"}:
        return "Image"
    if suffix in {".bib", ".ris", ".nbib"} or "reference" in key or "citation" in key:
        return "ReferenceList"
    if "paper" in key:
        return "PaperPool"
    if "open_access_pdf" in key:
        return "OpenAccessPDF"
    if "matrix" in key or "summary" in key:
        return "EvidenceMatrix"
    if "analysis" in key:
        return "AnalysisReport"
    if suffix in {".csv", ".tsv", ".xlsx"} or "data" in key:
        return "Dataset"
    if "review" in key:
        return "ReviewDraft" if "draft" in key else "ReviewOutline"
    return "File"


def register_artifacts(session: Any, spec: Any, artifacts: dict[str, Any]) -> None:
    records = getattr(session, "artifact_records", None)
    if records is None:
        session.artifact_records = {}
        records = session.artifact_records
    declared = dict(getattr(spec, "artifact_types", {}) or {})
    for key, value in artifacts.items():
        records[key] = {
            "type": classify_artifact(key, str(value), declared),
            "path": str(value),
            "producer": spec.name,
        }


def has_required_artifacts(session: Any, required: tuple[str, ...]) -> list[str]:
    if not required:
        return []
    present = {item.get("type") for item in getattr(session, "artifact_records", {}).values()}
    present.update(classify_artifact(key, value, {}) for key, value in getattr(session, "artifacts", {}).items())
    def available(required_type: str) -> bool:
        return required_type in present or (required_type == "PaperPool" and "ScreenedPaperPool" in present)
    return [artifact_type for artifact_type in required if not available(artifact_type)]


def validate_result_quality(result: dict[str, Any]) -> None:
    """Minimal cross-tool proof that returned artifacts are real and usable."""
    artifacts = result.get("artifacts") or {}
    missing = [key for key, value in artifacts.items() if value and not Path(str(value)).exists()]
    if missing:
        raise ContractError("quality_gate_failed", f"Tool reported missing artifacts: {', '.join(missing)}")
    for key in ("active_papers", "literature_matrix_json"):
        path = artifacts.get(key)
        if not path:
            continue
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ContractError("quality_gate_failed", f"Artifact {key} is unreadable: {exc}") from exc
        if not isinstance(payload, list) or not payload:
            raise ContractError("quality_gate_failed", f"Artifact {key} is empty or invalid")
        if key == "active_papers":
            identities = [str(item.get("doi") or item.get("title") or "").lower() for item in payload if isinstance(item, dict)]
            if len(identities) != len(set(identities)):
                raise ContractError("quality_gate_failed", "Paper pool contains duplicate identifiers")
        if key == "literature_matrix_json" and any(not item.get("title") or not item.get("evidence_scope") for item in payload if isinstance(item, dict)):
            raise ContractError("quality_gate_failed", "Evidence matrix has rows without paper identity or evidence scope")
    if artifacts.get("analysis_report") and not result.get("data", {}).get("row_count"):
        raise ContractError("quality_gate_failed", "Analysis report has no verified input row count")
