from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any


class OfficeAndMdService:
    """Two-directional document conversion: O→M (markitdown) and M→O (pandoc)."""

    def __init__(self, session_dir: Path):
        self.session_dir = session_dir

    # ── O → M ────────────────────────────────────────────────────────────────

    def to_markdown(self, arguments: dict[str, Any], _artifacts: dict[str, str]) -> dict[str, Any]:
        path = Path(str(arguments.get("path") or "")).expanduser().resolve()
        if not path.is_file():
            raise ValueError("请提供有效的文件路径")

        output = self._output_path(arguments, path, ".md")
        artifacts: dict[str, str] = {}

        suffix = path.suffix.lower()
        if suffix in {".docx", ".pptx", ".xlsx", ".pdf", ".html", ".htm", ".csv", ".json", ".xml", ".zip"}:
            self._markitdown(path, output)
        elif suffix in {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".mp3", ".wav", ".ogg", ".flac"}:
            self._markitdown(path, output)
        else:
            raise ValueError(f"不支持的文件格式: {suffix}")

        artifacts["markdown_output"] = str(output)
        return {
            "message": f"已转换为 Markdown: {output}",
            "artifacts": artifacts,
            "data": {"source": str(path), "output": str(output), "direction": "o-to-m"},
        }

    # ── M → O ────────────────────────────────────────────────────────────────

    def to_office(self, arguments: dict[str, Any], artifacts: dict[str, str]) -> dict[str, Any]:
        target_format = str(arguments.get("target_format") or "docx").lower().lstrip(".")
        if target_format not in {"docx", "pptx", "pdf", "html", "epub", "tex", "rst", "odt"}:
            raise ValueError(f"不支持的目标格式: {target_format}")

        source = self._resolve_markdown_source(arguments, artifacts)
        output = self._output_path(arguments, source, f".{target_format}")
        template = str(arguments.get("template") or "").strip()

        self._pandoc_convert(source, output, target_format, template)

        result_artifacts = {f"office_{target_format}": str(output)}
        return {
            "message": f"已转换为 {target_format.upper()}: {output}",
            "artifacts": result_artifacts,
            "data": {"source": str(source), "output": str(output), "direction": "m-to-o", "format": target_format},
        }

    # ── internals ────────────────────────────────────────────────────────────

    def _markitdown(self, source: Path, output: Path) -> None:
        try:
            from markitdown import MarkItDown
        except ImportError:
            raise RuntimeError("markitdown 未安装，请执行: pip install markitdown")

        result = MarkItDown().convert(str(source))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(result.text_content, encoding="utf-8")

    def _pandoc_convert(self, source: Path, output: Path, fmt: str, template: str) -> None:
        pandoc = self._find_pandoc()
        output.parent.mkdir(parents=True, exist_ok=True)
        cmd = [str(pandoc), str(source), "-o", str(output)]
        if template:
            ref = Path(template).expanduser().resolve()
            if ref.is_file():
                cmd.extend(["--reference-doc", str(ref)])
        if fmt == "pdf":
            cmd.extend(["--pdf-engine", "xelatex"])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode or not output.exists():
            raise RuntimeError((result.stderr or result.stdout or "pandoc conversion failed").strip())

    def _resolve_markdown_source(self, arguments: dict[str, Any], artifacts: dict[str, str]) -> Path:
        raw = str(arguments.get("path") or "").strip()
        if raw:
            p = Path(raw).expanduser().resolve()
            if p.is_file():
                return p
        text = str(arguments.get("text") or "").strip()
        if text:
            drafts = self.session_dir / "drafts"
            drafts.mkdir(parents=True, exist_ok=True)
            path = drafts / "draft.md"
            path.write_text(text, encoding="utf-8")
            return path
        for key in (
            "markdown_output", "review_draft", "review_framework",
            "literature_matrix_md", "paper_pool_markdown", "document_summary",
            "converted_document",
        ):
            candidate = artifacts.get(key)
            if candidate and Path(candidate).is_file():
                return Path(candidate)
        raise ValueError("没有找到可转换的 Markdown，请提供 path 或 text")

    def _output_path(self, arguments: dict[str, Any], source: Path, suffix: str) -> Path:
        raw = str(arguments.get("output_path") or "").strip()
        if raw:
            p = Path(raw).expanduser()
            if not p.is_absolute():
                p = self.session_dir / p.name
            if p.suffix.lower() != suffix.lower():
                p = p.with_suffix(suffix)
            return p
        out = self.session_dir / "conversions"
        out.mkdir(parents=True, exist_ok=True)
        base = source.stem
        candidate = out / f"{base}{suffix}"
        if candidate.exists():
            for n in range(2, 1000):
                candidate = out / f"{base}_v{n}{suffix}"
                if not candidate.exists():
                    break
        return candidate

    def _find_pandoc(self) -> Path:
        import os
        winget = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
        candidates = [
            shutil.which("pandoc"),
            str(Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Pandoc" / "pandoc.exe"),
        ]
        if winget.exists():
            candidates.extend(
                str(p) for p in winget.glob("JohnMacFarlane.Pandoc_*/*/pandoc.exe")
            )
        for raw in candidates:
            if raw and Path(raw).exists():
                return Path(raw)
        raise RuntimeError("Pandoc 未安装，请执行: choco install pandoc 或从 https://pandoc.org 下载")
