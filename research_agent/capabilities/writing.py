from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from threading import Event
from typing import Any

from research_agent.config import AgentConfig
from research_agent.context import ContextManager
from research_agent.logging import ModelCallLogger
from research_agent.tools.llm_client import LLMClient


MATRIX_FIELDS = [
    "citation_key",
    "title",
    "authors",
    "year",
    "venue",
    "abstract_summary",
    "research_question",
    "method",
    "dataset",
    "innovation",
    "key_findings",
    "conclusion",
    "limitations",
    "evidence_scope",
    "relevance_score",
    "source_url",
    "doi",
]


class WritingService:
    def __init__(self, config: AgentConfig, session_dir: Path, cancel_event: Event | None = None):
        self.config = config
        self.session_dir = session_dir
        self.client = LLMClient(config, ModelCallLogger(session_dir), cancel_event)
        self.context = ContextManager(session_dir, config.context_window)

    def summarize_papers(self, papers_path: str, arguments: dict[str, Any]) -> dict[str, Any]:
        papers = json.loads(Path(papers_path).read_text(encoding="utf-8-sig"))
        if arguments.get("limit") is not None:
            papers = papers[: max(1, int(arguments["limit"]))]
        if not papers:
            raise ValueError("当前会话没有可总结的论文")
        fallback_rows = [self._fallback_row(paper, index) for index, paper in enumerate(papers, 1)]
        compact = [
            {
                "index": index,
                "title": paper.get("title"),
                "authors": paper.get("authors"),
                "year": paper.get("year"),
                "venue": paper.get("venue"),
                "abstract": str(paper.get("abstract") or ""),
                "doi": paper.get("doi"),
                "url": paper.get("url"),
            }
            for index, paper in enumerate(papers, 1)
        ]
        instruction = (
            "Return one JSON array. Extract abstract_summary, research_question, method, dataset, innovation, "
            "key_findings, conclusion, limitations, evidence_scope from supplied abstracts only. "
            "Use NEEDS_FULLTEXT where absent."
        )
        evidence = self.context.fit_text(
            json.dumps(compact, ensure_ascii=False),
            label="literature-matrix-input",
            occupied=instruction,
            reserve_tokens=self.config.context_window // 3,
        )
        result = self.client.complete(
            "literature_matrix_extraction",
            instruction + "\n" + evidence,
            fallback=json.dumps(fallback_rows, ensure_ascii=False),
            system="Conservative academic evidence extraction; valid JSON only.",
            temperature=0,
        )
        try:
            extracted = self._json_array(result.text)
            rows = [
                self._merge_row(paper, extracted[index] if index < len(extracted) else {}, index + 1)
                for index, paper in enumerate(papers)
            ]
        except (ValueError, json.JSONDecodeError):
            rows = fallback_rows
        paths = self._write_matrix(rows)
        lines = [f"已整理 {len(rows)} 篇论文："]
        for index, row in enumerate(rows[:8], 1):
            summary = row["abstract_summary"] or "摘要不可用"
            lines.append(f"{index}. {row['title']}\n   {summary[:260]}")
        if len(rows) > 8:
            lines.append(f"其余 {len(rows) - 8} 篇见文献矩阵。")
        lines.append(f"文献矩阵：{paths['literature_matrix_md']}")
        return {"message": "\n".join(lines), "artifacts": paths, "data": {"rows": rows}}

    def summarize_document(self, source: str, arguments: dict[str, Any]) -> dict[str, Any]:
        request = str(arguments.get("request") or "请用中文概述该文档")
        detail = "详细" if re.search(r"详细|展开|具体|深入", request) else "简洁"
        prompt = (
            f"用户请求：{request}\n"
            f"请用中文给出{detail}、证据可追溯的说明。只依据以下文档内容，禁止编造未出现的事实、实验结果或局限。"
            "分别说明：问题、方法、证据、局限。信息缺失时明确写‘文档未说明’。\n\n文档内容：\n"
            + self.context.fit_text(
                source,
                label="document-summary-input",
                occupied=request,
                reserve_tokens=self.config.context_window // 4,
            )
        )
        fallback = self._document_summary_fallback(source)
        result = self.client.complete(
            "document_summary",
            prompt,
            fallback=fallback,
            system="You summarize supplied document evidence only. Never invent facts.",
            temperature=0.1,
        )
        summary = result.text.strip() or fallback
        path = self.session_dir / "document_summary.md"
        path.write_text(summary + "\n", encoding="utf-8")
        return {"message": summary, "artifacts": {"document_summary": str(path)}, "data": {"source_chars": len(source)}}

    def write_review(self, papers_path: str, matrix_path: str | None, arguments: dict[str, Any]) -> dict[str, Any]:
        papers = json.loads(Path(papers_path).read_text(encoding="utf-8-sig"))
        matrix = ""
        if matrix_path and Path(matrix_path).exists():
            matrix = Path(matrix_path).read_text(encoding="utf-8", errors="ignore")
        else:
            matrix = json.dumps(
                [
                    {"title": item.get("title"), "year": item.get("year"), "abstract": str(item.get("abstract") or "")}
                    for item in papers
                ],
                ensure_ascii=False,
            )
        request = str(arguments.get("request") or "生成文献综述大纲与初稿框架")
        stage = str(arguments.get("stage") or "outline").strip().lower()
        if stage not in {"outline", "draft"}:
            raise ValueError("综述阶段只能是 outline 或 draft")
        if stage == "draft" and arguments.get("confirmed") is not True:
            raise ValueError("生成综述初稿前需要用户确认大纲")
        if stage == "draft":
            framework = self.session_dir / "review_framework.md"
            if not framework.exists():
                raise ValueError("a confirmed review outline is required before drafting")
            matrix = framework.read_text(encoding="utf-8", errors="ignore") + "\n\nEvidence:\n" + matrix
        matrix = self.context.fit_text(
            matrix,
            label="review-evidence",
            occupied={"request": request, "stage": stage},
            reserve_tokens=self.config.context_window // 3,
        )
        prompt = (
            f"User request: {request}\n"
            f"Stage: {stage}. If stage is outline, produce a concrete outline with paper-grounded themes and comparison slots. "
            "If stage is draft, write the requested first draft from the confirmed outline.\n"
            "Write a Chinese literature-review outline or draft grounded only in the supplied evidence. "
            "Use the requested scope and themes, compare methods/datasets/metrics when present, cite supplied paper titles "
            "or citation keys, distinguish abstract-only evidence, and never invent unsupported claims. "
            "If the evidence is insufficient, return a concise evidence-gap report instead of generic filler.\n\n"
            + matrix
        )
        result = self.client.complete(
            "systematic_literature_review",
            prompt,
            fallback="",
            system="You write grounded academic reviews. Never invent citations, results, or limitations.",
            temperature=0.2,
        )
        if not result.used_remote_model or not result.text.strip():
            raise RuntimeError("模型不可用，未生成综述；已有论文和矩阵已保留。")
        self._validate_review(result.text, papers, matrix)
        path = self.session_dir / ("review_framework.md" if stage == "outline" else "review_draft.md")
        path.write_text(result.text.strip() + "\n", encoding="utf-8")
        preview = result.text.strip()[:1600]
        return {
            "message": (f"综述大纲已生成：{path}" if stage == "outline" else f"综述初稿已生成：{path}") + f"\n\n{preview}",
            "artifacts": {"review_framework" if stage == "outline" else "review_draft": str(path)},
            "data": {"preview": preview, "stage": stage, "requires_confirmation": stage == "outline"},
        }

    def _validate_review(self, text: str, papers: list[dict[str, Any]], matrix: str) -> None:
        """Reject empty/template-only drafts before they become artifacts."""
        headings = len(re.findall(r"^#{1,4}\s+", text, flags=re.MULTILINE))
        titles = [str(item.get("title") or "").strip() for item in papers[:20]]
        title_mentions = sum(1 for title in titles if title and title[:24].lower() in text.lower())
        generic_markers = ("仅在论文池包含相关论文时展开", "逐篇比较方法、数据集、指标、结论和局限")
        if len(text.strip()) < 240 or headings < 2:
            raise ValueError("综述结果过短或缺少结构，未通过证据质量门禁")
        if papers and matrix and title_mentions == 0 and not re.search(r"\b(?:20\d{2}|NEEDS_FULLTEXT)\b", text):
            raise ValueError("综述没有引用当前论文池中的证据，未写入文件")
        if all(marker in text for marker in generic_markers):
            raise ValueError("综述结果疑似通用模板，未写入文件")

    def transform(self, operation: str, arguments: dict[str, Any], artifacts: dict[str, str]) -> dict[str, Any]:
        source = self._source_text(arguments, artifacts)
        if not source:
            raise ValueError("没有找到可处理的文本或文档")
        instructions = {
            "write_paper_section": "Draft the requested ML paper section in Chinese or the user's language. Ground all claims in the source and mark missing citations.",
            "revise_document": "Revise only what the request asks. Preserve factual meaning, citations, and accepted structure.",
            "humanize_text": "Remove formulaic model language. Preserve technical meaning, numbers, citations, and uncertainty. Return edited text only.",
            "design_visual": "Create a concise research-figure specification with layout, labels, visual hierarchy, dimensions, and accessible color guidance.",
        }
        request = str(arguments.get("request") or arguments.get("text") or "")
        fitted_source = self.context.fit_text(
            source,
            label=f"{operation}-source",
            occupied=request,
            reserve_tokens=self.config.context_window // 4,
        )
        prompt = f"Request: {request}\n\nSource:\n{fitted_source}"
        fallback = self._transform_fallback(operation, request, source)
        result = self.client.complete(
            operation,
            prompt,
            fallback=fallback,
            system=instructions[operation],
            temperature=0.2,
        )
        names = {
            "write_paper_section": "paper_section.md",
            "revise_document": "revised_document.md",
            "humanize_text": "humanized_text.md",
            "design_visual": "visual_specification.md",
        }
        path = self.session_dir / names[operation]
        path.write_text(result.text.strip() + "\n", encoding="utf-8")
        return {
            "message": f"处理完成：{path}\n\n{result.text.strip()[:1200]}",
            "artifacts": {operation: str(path)},
            "data": {},
        }

    def _fallback_row(self, paper: dict[str, Any], index: int) -> dict[str, Any]:
        abstract = re.sub(r"\s+", " ", str(paper.get("abstract") or "")).strip()
        method = self._sentence(abstract, r"propos|using|use |method|network|model|cnn|transformer|lstm|classification")
        dataset = self._sentence(abstract, r"dataset|deap|mahnob|modma|public|cohort|subjects?|patients?")
        findings = self._sentence(abstract, r"result|achiev|outperform|accuracy|f1|auc|kappa|show|indicat")
        extracted = {
            "abstract_summary": abstract[:500] if abstract else "NEEDS_FULLTEXT",
            "research_question": self._sentence(abstract, r"challenge|objective|aim|problem|address") or "NEEDS_FULLTEXT",
            "method": method or "NEEDS_FULLTEXT",
            "dataset": dataset or "NEEDS_FULLTEXT",
            "innovation": method or "NEEDS_FULLTEXT",
            "key_findings": findings or "NEEDS_FULLTEXT",
            "conclusion": findings or "NEEDS_FULLTEXT",
            "limitations": "NEEDS_FULLTEXT",
            "evidence_scope": "abstract" if abstract else "metadata_only",
        }
        return self._merge_row(paper, extracted, index)

    def _sentence(self, text: str, pattern: str) -> str:
        if not text:
            return ""
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            if re.search(pattern, sentence, re.IGNORECASE):
                return sentence[:420]
        return ""

    def _merge_row(self, paper: dict[str, Any], extracted: dict[str, Any], index: int) -> dict[str, Any]:
        authors = paper.get("authors") or []
        first = re.sub(r"\W+", "", str(authors[0]).split()[-1].lower()) if authors else "paper"
        row = {
            "citation_key": f"{first or 'paper'}{paper.get('year') or 'nd'}",
            "title": paper.get("title") or "",
            "authors": "; ".join(str(item) for item in authors),
            "year": paper.get("year") or "",
            "venue": paper.get("venue") or "",
            "relevance_score": paper.get("relevance_score") or "",
            "source_url": paper.get("url") or paper.get("open_access_url") or "",
            "doi": paper.get("doi") or "",
        }
        for field in MATRIX_FIELDS:
            if field not in row:
                value = extracted.get(field)
                row[field] = str(value).strip() if value not in (None, "") else "NEEDS_FULLTEXT"
        row["index"] = index
        return row

    def _write_matrix(self, rows: list[dict[str, Any]]) -> dict[str, str]:
        json_path = self.session_dir / "literature_matrix.json"
        csv_path = self.session_dir / "literature_matrix.csv"
        md_path = self.session_dir / "literature_matrix.md"
        notes_path = self.session_dir / "summary_notes.md"
        json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=MATRIX_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        lines = [
            "# Literature Matrix",
            "",
            "| Citation | Title | Year | Method | Innovation | Findings | Evidence |",
            "|---|---|---:|---|---|---|---|",
        ]
        notes = ["# Literature Summary Notes", ""]
        for row in rows:
            clean = {key: str(value).replace("|", "\\|").replace("\n", " ") for key, value in row.items()}
            lines.append(
                f"| {clean['citation_key']} | {clean['title']} | {clean['year']} | {clean['method']} | "
                f"{clean['innovation']} | {clean['key_findings']} | {clean['evidence_scope']} |"
            )
            notes.append(f"## {row['title']}\n\n{row['abstract_summary']}\n")
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        notes_path.write_text("\n".join(notes) + "\n", encoding="utf-8")
        return {
            "literature_matrix_json": str(json_path),
            "literature_matrix_csv": str(csv_path),
            "literature_matrix_md": str(md_path),
            "summary_notes": str(notes_path),
        }

    def _transform_fallback(self, operation: str, request: str, source: str) -> str:
        if operation == "humanize_text":
            return self._humanize_local(source)
        if operation == "write_paper_section":
            return self._paper_section_local(request, source)
        return f"模型不可用，已保留原始材料并标记证据边界。\n\n{source[:8000]}"

    def _document_summary_fallback(self, source: str) -> str:
        text = re.sub(r"\s+", " ", source).strip()
        return (
            "## 问题\n\n" + (text[:500] or "文档未说明。") +
            "\n\n## 方法\n\n文档未说明。\n\n## 证据\n\n文档未说明。\n\n## 局限\n\n文档未说明。"
        )

    def _humanize_local(self, source: str) -> str:
        text = source.replace("综上所述，", "").replace("值得注意的是，", "")
        text = re.sub(r"本文旨在深入探讨", "本文讨论", text)
        text = re.sub(r"具有重要意义", "有研究价值", text)
        return text.strip() or source

    def _paper_section_local(self, request: str, source: str) -> str:
        title = "Related Work" if re.search(r"related\s+work|ieee", request, re.IGNORECASE) else "引言"
        citation_keys = re.findall(r"\|\s*([a-zA-Z][a-zA-Z0-9_-]*(?:20\d{2}|nd))\s*\|", source)
        citations = ", ".join(dict.fromkeys(citation_keys[:8])) or "待补引用"
        return (
            f"# {title}\n\n"
            "以下草稿仅依据当前会话中的文献矩阵和摘要材料生成；摘要没有支持的结论均保留为待核验。\n\n"
            "现有研究表明，EEG 相关任务中常见的深度学习方法会围绕时序、空间或频谱表示进行建模。"
            "在写作时应区分疾病识别、情绪识别、运动想象和 BCI 控制等不同任务，不能把跨任务结果直接当作同一证据链。"
            f"当前可引用证据包括：{citations}。\n\n"
            "待补证据：具体数据集规模、实验指标、统计显著性、消融实验和局限性需要阅读全文后确认。"
        )

    def _source_text(self, arguments: dict[str, Any], artifacts: dict[str, str]) -> str:
        direct = str(arguments.get("text") or "").strip()
        if direct:
            return direct
        raw_path = str(arguments.get("path") or "").strip()
        if raw_path and Path(raw_path).exists():
            return Path(raw_path).read_text(encoding="utf-8", errors="ignore")
        for key in ("review_framework", "write_paper_section", "revise_document", "summary_notes", "literature_matrix_md"):
            path = artifacts.get(key)
            if path and Path(path).exists():
                return Path(path).read_text(encoding="utf-8", errors="ignore")
        return ""

    def _json_array(self, text: str) -> list[dict[str, Any]]:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
        start, end = cleaned.find("["), cleaned.rfind("]")
        if start < 0 or end < start:
            raise ValueError("No JSON array returned")
        data = json.loads(cleaned[start : end + 1])
        if not isinstance(data, list):
            raise ValueError("Expected a JSON array")
        return [item if isinstance(item, dict) else {} for item in data]
