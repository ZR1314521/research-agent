from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from fnmatch import fnmatchcase
from typing import Any


class ContractError(ValueError):
    """A recoverable tool-boundary error that the model can act on."""

    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}

    def as_observation(self, tool: str) -> dict[str, Any]:
        return {"ok": False, "outcome": "failed", "tool": tool, "error": str(self), "error_code": self.code, "details": self.details}


@dataclass(frozen=True)
class ToolContract:
    """Small, local contract used at the only tool execution boundary."""

    input_schema: dict[str, Any] = field(default_factory=dict)
    consumes: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    artifact_types: dict[str, str] = field(default_factory=dict)
    artifact_profiles: dict[str, dict[str, str]] = field(default_factory=dict)
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


def classify_artifact(
    key: str,
    value: str,
    declared: dict[str, str],
    produces: tuple[str, ...] = (),
) -> str:
    declared_type = declared_artifact_type(key, declared)
    if declared_type:
        return declared_type
    if len(produces) == 1:
        return produces[0]
    return "File"


def declared_artifact_type(key: str, declared: dict[str, str]) -> str:
    """Resolve only explicit producer declarations, including wildcard keys."""
    if key in declared:
        return declared[key]
    for pattern, artifact_type in declared.items():
        if "*" in pattern and fnmatchcase(key, pattern):
            return artifact_type
    return ""


def register_artifacts(session: Any, spec: Any, artifacts: dict[str, Any]) -> None:
    records = getattr(session, "artifact_records", None)
    if records is None:
        session.artifact_records = {}
        records = session.artifact_records
    declared = dict(getattr(spec, "artifact_types", {}) or {})
    profiles = dict(getattr(spec, "artifact_profiles", {}) or {})
    produces = tuple(getattr(spec, "produces", ()) or ())
    for key, value in artifacts.items():
        matching_profiles = [
            dict(profile or {})
            for pattern, profile in profiles.items()
            if pattern != "*" and "*" in pattern and fnmatchcase(key, pattern)
        ]
        profile = dict(profiles.get("*", {}) or {})
        for matching in matching_profiles:
            profile.update(matching)
        profile.update(dict(profiles.get(key, {}) or {}))
        presentation = str(profile.get("presentation") or "internal")
        if presentation not in {"primary", "supporting", "internal"}:
            raise ContractError("invalid_artifact_profile", f"Invalid artifact presentation for {key}: {presentation}")
        records[key] = {
            "type": classify_artifact(key, str(value), declared, produces),
            "path": str(value),
            "producer": spec.name,
            "presentation": presentation,
            "label": str(profile.get("label") or key.replace("_", " ")),
            "summary": str(profile.get("summary") or ""),
        }


def public_artifacts(records: dict[str, dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    """Return only outputs that a producer explicitly marked for end users."""
    return {
        key: dict(record)
        for key, record in (records or {}).items()
        if record.get("presentation") in {"primary", "supporting"}
    }


def refresh_artifact_profiles(session: Any, registry: Any) -> bool:
    """Upgrade older ledger records using their declared producer contract."""
    changed = False
    records = dict(getattr(session, "artifact_records", {}) or {})
    for key, record in records.items():
        if record.get("presentation") in {"primary", "supporting", "internal"}:
            continue
        producer = str(record.get("producer") or "").strip()
        path = record.get("path") or getattr(session, "artifacts", {}).get(key)
        if not producer or not path:
            continue
        try:
            spec = registry.resolve(producer)
        except KeyError:
            continue
        register_artifacts(session, spec, {key: path})
        changed = True
    return changed


def has_required_artifacts(session: Any, required: tuple[str, ...], registry: Any | None = None) -> list[str]:
    if not required:
        return []
    present = {item.get("type") for item in getattr(session, "artifact_records", {}).values()}
    if registry is not None:
        declarations = [dict(getattr(spec, "artifact_types", {}) or {}) for spec in registry.all()]
        for key in getattr(session, "artifacts", {}):
            present.update(
                artifact_type
                for declared in declarations
                if (artifact_type := declared_artifact_type(key, declared))
            )
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
        if not isinstance(payload, list) or (key == "literature_matrix_json" and not payload):
            raise ContractError("quality_gate_failed", f"Artifact {key} is empty or invalid")
        if key == "active_papers":
            identities = [str(item.get("doi") or item.get("title") or "").lower() for item in payload if isinstance(item, dict)]
            if len(identities) != len(set(identities)):
                raise ContractError("quality_gate_failed", "Paper pool contains duplicate identifiers")
        if key == "literature_matrix_json" and any(not item.get("title") or not item.get("evidence_scope") for item in payload if isinstance(item, dict)):
            raise ContractError("quality_gate_failed", "Evidence matrix has rows without paper identity or evidence scope")
    if artifacts.get("analysis_report") and not result.get("data", {}).get("row_count"):
        raise ContractError("quality_gate_failed", "Analysis report has no verified input row count")
