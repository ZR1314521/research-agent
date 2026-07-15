from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


CATEGORY_BY_EXT = {
    ".csv": ("data", "experiment-data-analysis"),
    ".tsv": ("data", "experiment-data-analysis"),
    ".xlsx": ("data", "experiment-data-analysis"),
    ".txt": ("text", "rag-vector-knowledge-base"),
    ".md": ("text", "rag-vector-knowledge-base"),
    ".json": ("structured", "file-upload-router"),
    ".bib": ("references", "reference-format-gbt7714"),
    ".ris": ("references", "reference-format-gbt7714"),
    ".nbib": ("references", "reference-format-gbt7714"),
    ".pdf": ("paper", "office-to-md"),
    ".docx": ("document", "agent-decision"),
    ".csl": ("rules", "gbt7714-strict-rules"),
}


class FileService:
    def __init__(self, session_dir: Path):
        self.session_dir = session_dir

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
        upload_dir = self.session_dir / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        records = []
        artifacts: dict[str, str] = {}
        for raw in raw_paths:
            source = Path(str(raw)).expanduser().resolve()
            if not source.exists() or not source.is_file():
                records.append({"source": str(source), "status": "missing"})
                continue
            category, next_skill = CATEGORY_BY_EXT.get(source.suffix.lower(), ("unknown", "manual-review"))
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
                "next_skill": next_skill,
                "size_bytes": target.stat().st_size,
                "sha256": self._sha256(target),
                "status": "registered",
            }
            records.append(record)
            artifacts[f"uploaded_{category}_{len(records)}"] = str(target)
            artifacts[f"latest_{category}"] = str(target)
        manifest = self.session_dir / "upload_manifest.json"
        manifest.write_text(json.dumps({"files": records}, ensure_ascii=False, indent=2), encoding="utf-8")
        artifacts["upload_manifest"] = str(manifest)
        registered = [item for item in records if item.get("status") == "registered"]
        lines = [f"已导入 {len(registered)} 个文件："]
        lines.extend(f"- {item['filename']} -> {item['next_skill']}" for item in registered)
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
