from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from pathlib import Path
from typing import Any


class PaperAcquisitionService:
    """Acquire only explicitly supplied open-access URLs and preserve provenance."""

    def __init__(self, session_dir: Path):
        self.session_dir = session_dir

    def acquire(self, arguments: dict[str, Any], active_papers: str) -> dict[str, Any]:
        papers = json.loads(Path(active_papers).read_text(encoding="utf-8-sig")) if active_papers else []
        requested = arguments.get("indexes") or []
        selected = [paper for index, paper in enumerate(papers, 1) if not requested or index in requested]
        if not selected:
            raise ValueError("no papers selected from the active paper pool")
        requested = str(arguments.get("output_dir") or "").strip()
        output = Path(requested).expanduser().resolve() if requested else self.session_dir / "artifacts" / "downloads"
        output.mkdir(parents=True, exist_ok=True)
        records = []
        artifacts: dict[str, str] = {}
        for index, paper in enumerate(selected, 1):
            url = str(paper.get("open_access_url") or "")
            if not url.startswith("https://"):
                arxiv_id = str(paper.get("arxiv_id") or paper.get("id") or "")
                if arxiv_id and ("arxiv" in arxiv_id.lower() or re.match(r"^\d{4}\.\d{4,5}", arxiv_id)):
                    arxiv_id = arxiv_id.replace("arxiv:", "").replace("arXiv:", "").strip()
                    url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
            record = {"title": paper.get("title"), "doi": paper.get("doi"), "source_url": url, "status": "not_downloaded"}
            if not url.startswith("https://"):
                record["error"] = "no_verified_open_access_url"
                records.append(record)
                continue
            try:
                with urllib.request.urlopen(url, timeout=30) as response:
                    content = response.read(50 * 1024 * 1024 + 1)
                if len(content) > 50 * 1024 * 1024 or not content.startswith(b"%PDF"):
                    raise ValueError("response_is_not_a_pdf")
                path = output / f"paper_{index}.pdf"
                path.write_bytes(content)
                record.update({"status": "downloaded", "path": str(path), "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)})
                artifacts[f"open_access_pdf_{index}"] = str(path)
            except Exception as exc:
                record["error"] = f"{type(exc).__name__}: {exc}"
            records.append(record)
        manifest = output / "open_access_manifest.json"
        manifest.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        artifacts["open_access_manifest"] = str(manifest)
        done = sum(record["status"] == "downloaded" for record in records)
        return {"message": f"Downloaded {done}/{len(records)} verified open-access PDFs. See {manifest} for per-paper facts.", "artifacts": artifacts, "data": {"records": records}}

    def reading_docx(self, arguments: dict[str, Any], artifacts: dict[str, str]) -> dict[str, Any]:
        try:
            from docx import Document
        except ImportError as exc:
            raise RuntimeError("reading-copy DOCX requires python-docx") from exc
        pdfs = [Path(value) for key, value in artifacts.items() if key.startswith("open_access_pdf_") and Path(value).is_file()]
        if not pdfs:
            raise ValueError("no downloaded open-access PDF is available")
        from pypdf import PdfReader
        document = Document()
        document.add_heading("Reading copy", level=0)
        document.add_paragraph("Extracted from open-access PDFs. This is not an original publisher Word file.")
        for pdf in pdfs:
            document.add_heading(pdf.stem, level=1)
            document.add_paragraph("Source file: " + str(pdf))
            text = "\n".join(page.extract_text() or "" for page in PdfReader(pdf).pages)
            for chunk in [text[index:index + 3500] for index in range(0, min(len(text), 60000), 3500)]:
                document.add_paragraph(chunk)
        target = self.session_dir / str(arguments.get("output_name") or "open_access_reading_copy.docx")
        target = target.with_suffix(".docx")
        document.save(target)
        return {"message": f"Reading copy created: {target}. It is extracted text, not an original publisher DOCX.", "artifacts": {"reading_copy_docx": str(target)}, "data": {"pdf_count": len(pdfs)}}
