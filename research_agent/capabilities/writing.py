from __future__ import annotations

import csv
import json
import re
import uuid
from pathlib import Path
from threading import Event
from typing import Any

from research_agent.config import AgentConfig
from research_agent.context import ContextManager
from research_agent.logging import ModelCallLogger
from research_agent.tools.llm_client import LLMClient
from research_agent.capabilities.workspace import WorkspaceContext


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
    "evidence_map",
    "extraction_status",
]

EVIDENCE_FIELDS = [
    "abstract_summary",
    "research_question",
    "method",
    "dataset",
    "innovation",
    "key_findings",
    "conclusion",
    "limitations",
]


class WritingService:
    def __init__(self, config: AgentConfig, session_dir: Path, cancel_event: Event | None = None):
        self.config = config
        self.session_dir = session_dir
        self.workspace = WorkspaceContext.for_session(session_dir)
        self.client = LLMClient(config, ModelCallLogger(session_dir), cancel_event)
        self.context = ContextManager(session_dir, config.context_window)

    def summarize_papers(self, papers_path: str, arguments: dict[str, Any]) -> dict[str, Any]:
        papers = json.loads(Path(papers_path).read_text(encoding="utf-8-sig"))
        if arguments.get("limit") is not None:
            papers = papers[: max(1, int(arguments["limit"]))]
        if not papers:
            raise ValueError("当前会话没有可总结的论文")
        unavailable_rows = [self._merge_row(paper, {}, index) for index, paper in enumerate(papers, 1)]
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
            "Return one valid JSON array with one item. For every field abstract_summary, "
            "research_question, method, dataset, innovation, key_findings, conclusion, and limitations, return an "
            "object {status: reported|not_reported, value: string, evidence_quote: exact substring from that paper's "
            "abstract}. A reported value without an exact supporting quote is invalid. Do not infer absent facts."
        )

        def _paper_prompt(paper):
            return instruction + "\n" + json.dumps([paper], ensure_ascii=False)

        results = self.client.map_complete(
            "literature_matrix_extraction",
            compact,
            _paper_prompt,
            system="Conservative academic evidence extraction; valid JSON only.",
            temperature=0,
            fallback_fn=lambda p: json.dumps([], ensure_ascii=False),
        )
        extracted_all: list[dict[str, Any]] = []
        for result in results:
            try:
                parsed = self._json_array(result.text)
                extracted_all.extend(parsed)
            except (ValueError, json.JSONDecodeError):
                pass
        rows = [
            self._merge_row(paper, extracted_all[index] if index < len(extracted_all) else {}, index + 1)
            for index, paper in enumerate(papers)
        ]
        paths = self._write_matrix(rows)
        lines = [f"已整理 {len(rows)} 篇论文："]
        for index, row in enumerate(rows[:8], 1):
            summary = row["abstract_summary"] or "摘要不可用"
            lines.append(f"{index}. {row['title']}\n   {summary[:260]}")
        if len(rows) > 8:
            lines.append(f"其余 {len(rows) - 8} 篇见文献矩阵。")
        lines.append(f"文献矩阵：{paths['literature_matrix_md']}")
        model_rows = self._matrix_model_rows(rows)
        return {
            "message": "\n".join(lines),
            "artifacts": paths,
            "data": {"rows": rows},
            "model_data": {
                "answer_ready": bool(model_rows),
                "missing_evidence": [] if model_rows else ["No grounded evidence was extracted."],
                "row_count": len(rows),
                "rows": model_rows,
                "completion_guidance": (
                    "Use these grounded rows to answer the user's research question now. "
                    "Do not return the matrix files as the answer."
                ),
            },
            "progress": {
                "summary": f"文献证据提取完成：整理 {len(rows)} 篇",
                "metrics": {"extracted": len(rows), "grounded": len(model_rows)},
            },
        }

    def _matrix_model_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep grounded synthesis evidence inside the configured observation budget."""
        keys = (
            "citation_key", "title", "year", "venue", "method", "dataset",
            "innovation", "key_findings", "conclusion", "limitations",
            "evidence_scope", "doi", "source_url", "extraction_status",
        )
        budget = max(256, int(self.config.context_observation_budget * 0.72))
        selected: list[dict[str, Any]] = []
        for row in rows:
            grounded = any(
                str(row.get(field) or "").strip() not in {"", "NOT_REPORTED", "NEEDS_FULLTEXT"}
                for field in EVIDENCE_FIELDS
            )
            if not grounded:
                continue
            candidate = {key: row.get(key) for key in keys}
            if ContextManager.estimate_tokens([*selected, candidate]) > budget:
                break
            selected.append(candidate)
        return selected

    def summarize_document(self, source: str, arguments: dict[str, Any]) -> dict[str, Any]:
        request = str(arguments.get("request") or "请用中文概述该文档")
        prompt = (
            f"用户请求：{request}\n"
            "请按用户要求给出证据可追溯的说明。只依据以下文档内容，禁止编造未出现的事实、实验结果或局限。"
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
        path = self.workspace.artifacts_root / "document_summary.md"
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
            framework = self.workspace.artifacts_root / "review_framework.md"
            if not framework.exists():
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
        path = self.workspace.artifacts_root / ("review_framework.md" if stage == "outline" else "review_draft.md")
        path.write_text(result.text.strip() + "\n", encoding="utf-8")
        preview = result.text.strip()[:1600]
        return {
            "message": (f"综述大纲已生成：{path}" if stage == "outline" else f"综述初稿已生成：{path}") + f"\n\n{preview}",
            "artifacts": {"review_framework" if stage == "outline" else "review_draft": str(path)},
            "data": {"preview": preview, "stage": stage, "requires_confirmation": stage == "outline"},
        }

    def compose_manuscript(self, arguments: dict[str, Any], artifacts: dict[str, str]) -> dict[str, Any]:
        """Create one evidence-audited manuscript draft without imposing a tool sequence."""
        title = str(arguments.get("title") or "Untitled manuscript").strip()
        paper_type = str(arguments.get("paper_type") or "research").strip().lower()
        language = str(arguments.get("language") or "follow the user's language").strip()
        target_venue = str(arguments.get("target_venue") or "unspecified").strip()
        evidence, citations, skipped = self._manuscript_evidence(arguments, artifacts)
        if not evidence:
            raise ValueError("没有可用于完整论文写作的会话证据；请提供材料、文献矩阵或实验结果")

        evidence_text = self.context.fit_text(
            json.dumps(evidence, ensure_ascii=False, indent=2),
            label="manuscript-evidence",
            occupied={"title": title, "paper_type": paper_type, "target_venue": target_venue},
            reserve_tokens=self.config.context_window // 3,
        )
        known_keys = sorted(citations)
        prompt = (
            f"Title: {title}\nPaper type: {paper_type}\nLanguage: {language}\nTarget venue: {target_venue}\n"
            f"User request: {str(arguments.get('request') or '')}\n\n"
            "Write a complete scholarly manuscript with title, abstract, keywords, body sections appropriate to the "
            "paper type, limitations, conclusion, and references. Decide the section structure from the paper type and "
            "target venue; do not follow a fixed tool workflow. Every factual result or literature claim must be grounded "
            "in the supplied evidence. Cite only the supplied citation keys using [@key]. Never invent citations, datasets, "
            "metrics, experiments, or findings. When required evidence is absent, write [EVIDENCE NEEDED: concise reason] "
            "instead of filling the gap. Distinguish metadata, abstract, full-text, and user-analysis evidence.\n"
            f"Allowed citation keys: {', '.join(known_keys) or '(none)'}\n\nEvidence:\n{evidence_text}"
        )
        result = self.client.complete(
            "manuscript_writing",
            prompt,
            fallback="",
            system="You write complete evidence-grounded academic manuscripts and never fabricate claims or references.",
            temperature=0.2,
        )
        if not result.used_remote_model or not result.text.strip():
            raise RuntimeError("模型不可用，未生成论文；会话证据仍然保留")

        manuscript = result.text.strip()
        cited = sorted(set(re.findall(r"\[@([A-Za-z0-9_.:-]+)\]", manuscript)))
        unknown = sorted(set(cited) - set(known_keys))
        placeholders = re.findall(r"\[(?:EVIDENCE NEEDED|待补|TODO|TBD)[^\]]*\]", manuscript, flags=re.IGNORECASE)
        headings = len(re.findall(r"^#{1,4}\s+", manuscript, flags=re.MULTILINE))
        has_references = bool(re.search(r"^#{1,4}\s+(?:References|参考文献)\s*$", manuscript, flags=re.MULTILINE | re.IGNORECASE))
        status = "review_ready" if (
            len(manuscript) >= self.config.manuscript_min_chars
            and headings >= self.config.manuscript_min_headings
            and has_references and not unknown and not placeholders
        ) else "draft_with_gaps"

        requested_id = re.sub(r"[^A-Za-z0-9._-]+", "-", str(arguments.get("manuscript_id") or "").strip()).strip(".-")
        manuscript_id = requested_id or f"manuscript-{uuid.uuid4().hex[:12]}"
        output_dir = self.workspace.artifacts_root / "manuscripts" / manuscript_id
        output_dir.mkdir(parents=True, exist_ok=True)
        manuscript_path = output_dir / "manuscript.md"
        ledger_path = output_dir / "evidence_ledger.json"
        citation_path = output_dir / "citation_audit.md"
        quality_path = output_dir / "manuscript_quality_report.md"
        manuscript_path.write_text(manuscript + "\n", encoding="utf-8")
        ledger_path.write_text(json.dumps({
            "manuscript_id": manuscript_id, "sources": evidence, "citations": list(citations.values()),
            "skipped_sources": skipped,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        citation_path.write_text(
            "# Citation audit\n\n"
            f"- Allowed citation keys: {len(known_keys)}\n- Used citation keys: {len(cited)}\n"
            f"- Unknown citation keys: {', '.join(unknown) or 'none'}\n",
            encoding="utf-8",
        )
        quality_path.write_text(
            "# Manuscript quality report\n\n"
            f"- Status: {status}\n- Characters: {len(manuscript)}\n- Headings: {headings}\n"
            f"- Configured minimum characters: {self.config.manuscript_min_chars}\n"
            f"- Configured minimum headings: {self.config.manuscript_min_headings}\n"
            f"- References section: {'yes' if has_references else 'no'}\n"
            f"- Evidence placeholders: {len(placeholders)}\n- Unknown citations: {len(unknown)}\n"
            f"- Skipped unsupported document sources: {len(skipped)}\n",
            encoding="utf-8",
        )
        output_artifacts = {
            "manuscript": str(manuscript_path),
            "manuscript_evidence_ledger": str(ledger_path),
            "manuscript_citation_audit": str(citation_path),
            "manuscript_quality_report": str(quality_path),
        }
        return {
            "message": f"完整论文第一版已生成（{status}）：{manuscript_path}\n\n{manuscript[:1400]}",
            "artifacts": output_artifacts,
            "data": {
                "manuscript_id": manuscript_id, "status": status, "citation_keys": cited,
                "unknown_citations": unknown, "evidence_placeholders": len(placeholders), "skipped_sources": skipped,
            },
            "progress": {"summary": f"论文第一版已生成：{status}", "metrics": {"citations": len(cited), "gaps": len(placeholders)}},
        }

    def _manuscript_evidence(
        self,
        arguments: dict[str, Any],
        artifacts: dict[str, str],
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[str]]:
        evidence: list[dict[str, Any]] = []
        citations: dict[str, dict[str, Any]] = {}
        skipped: list[str] = []
        direct = str(arguments.get("text") or "").strip()
        if direct:
            evidence.append({"source": "user_text", "scope": "user_supplied", "content": direct})
        raw_paths = list(arguments.get("evidence_paths") or []) + list(artifacts.values())
        seen: set[Path] = set()
        for raw in raw_paths:
            if not isinstance(raw, (str, Path)) or not str(raw).strip():
                continue
            path = Path(str(raw)).expanduser().resolve()
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            if path != self.workspace.session_root and self.workspace.session_root not in path.parents:
                skipped.append(str(path))
                continue
            if path.suffix.lower() in {".docx", ".pdf", ".pptx", ".xlsx"}:
                skipped.append(str(path))
                continue
            try:
                text = path.read_text(encoding="utf-8-sig", errors="ignore")
            except OSError:
                skipped.append(str(path))
                continue
            record: dict[str, Any] = {"source": path.name, "path": str(path), "scope": "session_artifact"}
            try:
                payload = json.loads(text) if path.suffix.lower() == ".json" else None
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, list):
                rows = [item for item in payload if isinstance(item, dict)]
                record["content"] = rows
                for row in rows:
                    key = str(row.get("citation_key") or "").strip()
                    if key:
                        citations[key] = {
                            "citation_key": key, "title": row.get("title"), "year": row.get("year"),
                            "doi": row.get("doi"), "source_url": row.get("source_url"),
                            "evidence_scope": row.get("evidence_scope"),
                        }
            else:
                record["content"] = text[:12000]
            evidence.append(record)
        return evidence, citations, skipped

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
        path = self.workspace.artifacts_root / names[operation]
        path.write_text(result.text.strip() + "\n", encoding="utf-8")
        return {
            "message": f"处理完成：{path}\n\n{result.text.strip()[:1200]}",
            "artifacts": {operation: str(path)},
            "data": {},
        }

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
        abstract = str(paper.get("abstract") or "")
        normalized_abstract = " ".join(abstract.split())
        evidence_map: dict[str, dict[str, str]] = {}
        reported = 0
        for field in EVIDENCE_FIELDS:
            item = extracted.get(field)
            if not isinstance(item, dict):
                row[field] = "NOT_REPORTED"
                evidence_map[field] = {"status": "not_reported", "quote": ""}
                continue
            status = str(item.get("status") or "").strip().lower()
            value = str(item.get("value") or "").strip()
            quote = str(item.get("evidence_quote") or "").strip()
            quote_is_supported = bool(quote and " ".join(quote.split()) in normalized_abstract)
            if status == "reported" and value and quote_is_supported:
                row[field] = value
                evidence_map[field] = {"status": "reported", "quote": quote}
                reported += 1
            else:
                row[field] = "NOT_REPORTED"
                evidence_map[field] = {
                    "status": "invalid_evidence" if status == "reported" else "not_reported",
                    "quote": quote if quote_is_supported else "",
                }
        row["evidence_scope"] = "abstract" if reported else ("abstract_unextracted" if abstract else "metadata_only")
        row["evidence_map"] = json.dumps(evidence_map, ensure_ascii=False, sort_keys=True)
        row["extraction_status"] = "complete" if reported == len(EVIDENCE_FIELDS) else ("partial" if reported else "unavailable")
        for field in MATRIX_FIELDS:
            row.setdefault(field, "NOT_REPORTED")
        row["index"] = index
        return row

    def _write_matrix(self, rows: list[dict[str, Any]]) -> dict[str, str]:
        json_path = self.workspace.artifacts_root / "literature_matrix.json"
        csv_path = self.workspace.artifacts_root / "literature_matrix.csv"
        md_path = self.workspace.artifacts_root / "literature_matrix.md"
        notes_path = self.workspace.artifacts_root / "summary_notes.md"
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
        return f"模型不可用，未执行语义改写；以下为保留的原始材料。\n\n{source[:8000]}"

    def _document_summary_fallback(self, source: str) -> str:
        text = re.sub(r"\s+", " ", source).strip()
        return (
            "模型不可用，未执行语义总结。以下为原文摘录，不代表问题、方法或结论抽取：\n\n"
            + (text[:2000] or "文档为空。")
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
