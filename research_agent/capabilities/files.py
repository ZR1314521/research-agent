from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from research_agent.capabilities.workspace import WorkspaceContext


CATEGORY_BY_EXT = {
    ".csv": "data", ".tsv": "data", ".xlsx": "data",
    ".txt": "text", ".md": "text", ".json": "structured",
    ".bib": "references", ".ris": "references", ".nbib": "references",
    ".pdf": "paper", ".docx": "document", ".csl": "rules",
}


class FileService:
    def __init__(self, session_dir: Path | WorkspaceContext):
        self.context = session_dir if isinstance(session_dir, WorkspaceContext) else WorkspaceContext.for_session(session_dir)
        self.session_dir = self.context.session_root

    def register(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raw_paths = arguments.get("paths") or [
            value
            for value in (
                arguments.get("path"),
                arguments.get("local_file_path"),
            )
            if value
        ]
        if not raw_paths:
            raise ValueError("请提供至少一个本地文件路径")
        upload_dir = self.context.uploads_root
        records = []
        artifacts: dict[str, str] = {}
        for raw in raw_paths:
            source = Path(str(raw)).expanduser().resolve()
            if not source.exists() or not source.is_file():
                records.append({"source": str(source), "status": "missing"})
                continue
            category = CATEGORY_BY_EXT.get(source.suffix.lower(), "unknown")
            target = upload_dir / source.name
            if target.exists() and self._sha256(target) != self._sha256(source):
                target = upload_dir / f"{source.stem}-{self._sha256(source)[:8]}{source.suffix}"
            if not target.exists():
                shutil.copy2(source, target)
            record = {
                "source": str(source),
                "stored_path": str(target),
                "filename": target.name,
                "extension": target.suffix.lower(),
                "category": category,
                "size_bytes": target.stat().st_size,
                "sha256": self._sha256(target),
                "status": "registered",
            }
            records.append(record)
            artifacts[f"uploaded_{category}_{len(records)}"] = str(target)
            artifacts[f"latest_{category}"] = str(target)
        manifest = self.context.artifacts_root / "upload_manifest.json"
        manifest.write_text(json.dumps({"files": records}, ensure_ascii=False, indent=2), encoding="utf-8")
        artifacts["upload_manifest"] = str(manifest)
        registered = [item for item in records if item.get("status") == "registered"]
        lines = [f"已导入 {len(registered)} 个文件："]
        lines.extend(f"- {item['filename']}（{item['category']}；由模型根据当前目标决定是否使用工具）" for item in registered)
        missing = len(records) - len(registered)
        if missing:
            lines.append(f"另有 {missing} 个路径不存在。")
        return {"message": "\n".join(lines), "artifacts": artifacts, "data": {"files": records}}

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
