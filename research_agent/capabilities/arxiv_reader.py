from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from threading import Event
from typing import Any

from research_agent.config import AgentConfig
from research_agent.context import ContextManager
from research_agent.logging import ModelCallLogger
from research_agent.tools.llm_client import LLMClient


class ArxivReaderService:
    def __init__(self, config: AgentConfig, session_dir: Path, cancel_event: Event | None = None):
        self.config = config
        self.session_dir = session_dir
        self.cancel_event = cancel_event

    def read(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raw = str(arguments.get("url") or arguments.get("id") or arguments.get("request") or "")
        match = re.search(r"(?:arxiv\.org/(?:abs|pdf)/)?(\d{4}\.\d{4,5})(?:v\d+)?", raw, re.IGNORECASE)
        if not match:
            raise ValueError("请提供有效 arXiv URL 或编号")
        arxiv_id = match.group(1)
        url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode({"id_list": arxiv_id})
        with urllib.request.urlopen(url, timeout=30) as response:
            root = ET.fromstring(response.read())
        ns = {"a": "http://www.w3.org/2005/Atom"}
        entry = root.find("a:entry", ns)
        if entry is None:
            raise ValueError(f"arXiv paper not found: {arxiv_id}")
        metadata = {
            "id": arxiv_id,
            "title": (entry.findtext("a:title", default="", namespaces=ns) or "").strip(),
            "authors": [node.findtext("a:name", default="", namespaces=ns) for node in entry.findall("a:author", ns)],
            "abstract": (entry.findtext("a:summary", default="", namespaces=ns) or "").strip(),
            "published": entry.findtext("a:published", default="", namespaces=ns),
            "url": f"https://arxiv.org/abs/{arxiv_id}",
        }
        pdf_path = self.session_dir / f"arxiv_{arxiv_id}.pdf"
        text_path = self.session_dir / f"arxiv_{arxiv_id}.txt"
        full_text = ""
        try:
            urllib.request.urlretrieve(f"https://arxiv.org/pdf/{arxiv_id}", pdf_path)
            from pypdf import PdfReader

            full_text = "\n".join(page.extract_text() or "" for page in PdfReader(pdf_path).pages)
            text_path.write_text(full_text, encoding="utf-8")
        except Exception:
            if pdf_path.exists() and pdf_path.stat().st_size == 0:
                pdf_path.unlink()
        evidence = full_text if full_text else metadata["abstract"]
        evidence = ContextManager(self.session_dir, self.config.context_window).fit_text(
            evidence,
            label=f"arxiv-{arxiv_id}",
            occupied=metadata,
            reserve_tokens=self.config.context_window // 4,
        )
        fallback = (
            f"# {metadata['title']}\n\n"
            f"Authors: {', '.join(metadata['authors'])}\n\n"
            f"Evidence scope: {'full text' if full_text else 'abstract'}\n\n"
            f"## Abstract\n\n{metadata['abstract']}\n"
        )
        result = LLMClient(self.config, ModelCallLogger(self.session_dir), self.cancel_event).complete(
            "read_arxiv_paper",
            f"Summarize this paper in Chinese: research question, method, data, key findings, contribution, limitations. "
            f"Use only evidence below.\n\nMetadata: {json.dumps(metadata, ensure_ascii=False)}\n\nEvidence:\n{evidence}",
            fallback=fallback,
            system="You summarize academic papers conservatively and distinguish abstract evidence from full-text evidence.",
            temperature=0,
        )
        summary_path = self.session_dir / f"arxiv_{arxiv_id}_summary.md"
        summary_path.write_text(result.text.strip() + "\n", encoding="utf-8")
        artifacts = {"arxiv_summary": str(summary_path)}
        if text_path.exists():
            artifacts["arxiv_full_text"] = str(text_path)
        if pdf_path.exists():
            artifacts["arxiv_pdf"] = str(pdf_path)
        return {
            "message": f"已阅读 {metadata['title']}：\n\n{result.text.strip()[:1800]}\n\n总结：{summary_path}",
            "artifacts": artifacts,
            "data": metadata,
        }
