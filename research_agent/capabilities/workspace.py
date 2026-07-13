from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


class WorkspaceService:
    """Safe, explicit file operations scoped to the project or session folder."""

    def __init__(self, root_dir: Path, session_dir: Path):
        self.root_dir = root_dir.resolve()
        self.session_dir = session_dir.resolve()

    @staticmethod
    def requires_confirmation(arguments: dict[str, Any]) -> bool:
        return str(arguments.get("operation") or "").lower() in {"copy", "move", "write", "delete"}

    def operate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        operation = str(arguments.get("operation") or "").lower()
        if operation == "list":
            folder = self._path(str(arguments.get("path") or "."))
            if not folder.is_dir():
                raise ValueError("list requires an existing directory")
            limit = max(1, int(arguments.get("limit") or 200))
            entries = sorted(folder.iterdir())
            files = [str(item.relative_to(self.root_dir)) for item in entries[:limit]]
            return {
                "message": "\n".join(files) or "Directory is empty.",
                "artifacts": {},
                "data": {"files": files, "truncated": len(entries) > len(files)},
            }
        if operation == "read":
            path = self._existing_file(arguments)
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            limit = max(1, int(arguments.get("limit") or 400))
            if arguments.get("tail"):
                start = max(0, len(lines) - limit)
            else:
                start = max(0, int(arguments.get("offset") or 0))
            selected = lines[start : start + limit]
            numbered = "\n".join(f"{index}: {line}" for index, line in enumerate(selected, start=start + 1))
            return {
                "message": numbered,
                "artifacts": {},
                "data": {
                    "path": str(path),
                    "start_line": start + 1 if selected else 0,
                    "end_line": start + len(selected),
                    "total_lines": len(lines),
                    "truncated": start > 0 or start + len(selected) < len(lines),
                },
            }
        if operation == "search":
            folder = self._path(str(arguments.get("path") or "."))
            query = str(arguments.get("query") or "").lower()
            if not query:
                raise ValueError("search requires query")
            max_results = max(1, int(arguments.get("max_results") or arguments.get("limit") or 80))
            matches: list[dict[str, Any]] = []
            for file in folder.rglob("*"):
                if len(matches) >= max_results:
                    break
                if not file.is_file():
                    continue
                try:
                    with file.open("r", encoding="utf-8", errors="ignore") as handle:
                        for line_number, line in enumerate(handle, 1):
                            if query in line.lower():
                                matches.append({
                                    "path": str(file.relative_to(self.root_dir)),
                                    "line": line_number,
                                    "text": line.strip(),
                                })
                                if len(matches) >= max_results:
                                    break
                except (OSError, UnicodeError):
                    continue
            return {"message": json.dumps(matches, ensure_ascii=False), "artifacts": {}, "data": {"matches": matches}}
        if operation in {"copy", "move"}:
            source = self._existing_file(arguments)
            target = self._path(str(arguments.get("target_path") or ""))
            if not target.name:
                raise ValueError("copy/move requires target_path")
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and not arguments.get("confirmed"):
                raise ValueError("target exists; set confirmed=true to replace it")
            if operation == "copy":
                shutil.copy2(source, target)
            else:
                shutil.move(str(source), str(target))
            return {"message": f"{operation} completed: {target}", "artifacts": {"workspace_file": str(target)}, "data": {"operation": operation}}
        if operation == "write":
            target = self._path(str(arguments.get("path") or ""))
            if not target.name:
                raise ValueError("write requires path")
            if target.exists() and not arguments.get("confirmed"):
                raise ValueError("target exists; set confirmed=true to replace it")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(arguments.get("text") or ""), encoding="utf-8")
            return {"message": f"written: {target}", "artifacts": {"workspace_file": str(target)}, "data": {"operation": operation}}
        if operation == "delete":
            source = self._existing_file(arguments)
            if not arguments.get("confirmed"):
                raise ValueError("delete is reversible but requires confirmed=true")
            recycle = self.session_dir / ".recycle"
            recycle.mkdir(parents=True, exist_ok=True)
            target = recycle / source.name
            suffix = 2
            while target.exists():
                target = recycle / f"{source.stem}_{suffix}{source.suffix}"
                suffix += 1
            shutil.move(str(source), str(target))
            return {"message": f"moved to session recycle bin: {target}", "artifacts": {"recycled_file": str(target)}, "data": {"operation": operation}}
        raise ValueError("unsupported workspace operation")

    def _existing_file(self, arguments: dict[str, Any]) -> Path:
        path = self._path(str(arguments.get("path") or ""))
        if not path.is_file():
            raise ValueError("path must be an existing file")
        return path

    def _path(self, raw: str) -> Path:
        if raw.strip() in {"", ".", "/", "\\"}:
            return self.root_dir
        path = Path(raw).expanduser()
        return path.resolve() if path.is_absolute() else (self.root_dir / path).resolve()
