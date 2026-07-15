from __future__ import annotations

import json
import math
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

from research_agent.config import AgentConfig
from research_agent.tools.arxiv import ArxivClient
from research_agent.tools.openalex import OpenAlexClient
from research_agent.tools.pubmed import PubMedClient
from research_agent.tools.semantic_scholar import SemanticScholarClient


STOPWORDS = {
    "about", "analysis", "and", "approach", "based", "for", "from", "method", "model",
    "paper", "research", "results", "study", "system", "the", "this", "using", "with",
    "of", "in", "to", "a", "an", "on", "by", "as", "at", "or", "is", "are",
    "latest", "recent", "best", "review", "literature",
}
ALIASES = {
    "cnn": {"cnn", "convolutional", "convolution"},
    "bci": {"bci", "brain-computer", "braincomputer"},
    "eeg": {"eeg", "electroencephalography", "electroencephalogram"},
    "llm": {"llm", "language-model", "language"},
    "mdd": {"mdd", "depression", "depressive", "depressed"},
    "depression": {"mdd", "depression", "depressive", "depressed"},
    "rag": {"rag", "retrieval-augmented", "retrieval"},
    "review": {"review", "survey", "综述"},
    "preprint": {"preprint", "arxiv", "biorxiv", "medrxiv"},
    "alzheimer": {"alzheimer", "alzheimers", "ad"},
}


def tokens(text: str) -> list[str]:
    values = re.findall(r"[A-Za-z][A-Za-z0-9-]{1,}|[\u4e00-\u9fff]{2,}", text or "")
    return [value.lower() for value in values if value.lower() not in STOPWORDS]


def normalized_title(title: str) -> str:
    return re.sub(r"\W+", " ", (title or "").lower()).strip()


class LiteratureService:
    def __init__(self, config: AgentConfig, session_dir: Path):
        self.config = config
        self.session_dir = session_dir
        self.raw_dir = session_dir / "raw_search"
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def search(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ValueError("Literature search needs a topic or query")
        year_from = self._int(arguments.get("year_from"))
        year_to = self._int(arguments.get("year_to"))
        venues = [str(item).strip() for item in arguments.get("venues") or [] if str(item).strip()]
        sources = [str(item) for item in arguments.get("sources") or ["openalex"]]
        limit = max(1, min(50, self._int(arguments.get("limit")) or 12))
        max_rounds = max(1, min(3, self._int(arguments.get("rounds")) or 1))
        max_requests_per_source = max(1, min(10, self._int(arguments.get("max_requests_per_source")) or 2))
        must_include = [str(item) for item in arguments.get("must_include") or [] if str(item).strip()]
        exclude = [str(item) for item in arguments.get("exclude") or [] if str(item).strip()]
        precise = bool(arguments.get("precise") or must_include or exclude)
        if arguments.get("no_network"):
            raise ValueError("当前请求禁止联网；请先上传资料，或取消不要联网限制")

        pool: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        rounds: list[dict[str, Any]] = []
        current_query = query
        known_terms = set(tokens(query))
        source_attempts: dict[str, int] = {source: 0 for source in sources}
        blocked_sources: set[str] = set()

        for round_number in range(1, max_rounds + 1):
            before = len(pool)
            round_results: list[dict[str, Any]] = []
            source_requests: list[dict[str, Any]] = []
            for source in sources:
                if source in blocked_sources:
                    source_requests.append({"source": source, "status": "skipped_blocked"})
                    continue
                if source_attempts.get(source, 0) >= max_requests_per_source:
                    source_requests.append({"source": source, "status": "skipped_budget"})
                    continue
                client = self._client(source)
                if client is None:
                    errors.append({"source": source, "error": "unsupported source"})
                    source_requests.append({"source": source, "status": "unsupported"})
                    continue
                try:
                    source_attempts[source] = source_attempts.get(source, 0) + 1
                    papers = client.search(
                        current_query,
                        year_from=year_from,
                        year_to=year_to,
                        limit=max(limit, 10),
                    )
                    (self.raw_dir / f"round_{round_number}_{source}.json").write_text(
                        json.dumps(papers, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                    round_results.extend(papers)
                    source_requests.append({"source": source, "status": "ok", "count": len(papers), "attempt": source_attempts[source]})
                    time.sleep(0.3)  # polite pause between API calls
                except Exception as exc:
                    error = str(exc)
                    errors.append({"source": source, "error": error})
                    source_requests.append({"source": source, "status": "error", "error": error, "attempt": source_attempts.get(source, 0)})
                    if "429" in error or "too many" in error.lower() or "rate" in error.lower():
                        blocked_sources.add(source)
            pool = self._dedupe([*pool, *round_results])
            screened, excluded, edge = self.screen_with_edge(pool, query, year_from, year_to, venues, must_include, exclude, precise)
            new_terms = self._expand(screened or pool, known_terms)
            stop_reason = ""
            if len(screened) >= limit:
                stop_reason = "target_reached"
            elif len(pool) == before:
                stop_reason = "no_new_papers"
            elif not any(item.get("status") == "ok" for item in source_requests):
                stop_reason = "all_sources_failed_or_blocked"
            elif not new_terms:
                stop_reason = "no_new_terms"
            rounds.append(
                {
                    "round": round_number,
                    "query": current_query,
                    "new_papers": len(pool) - before,
                    "pool_size": len(pool),
                    "screened": len(screened),
                    "edge": len(edge),
                    "new_terms": new_terms,
                    "source_requests": source_requests,
                    "stop_reason": stop_reason or ("max_rounds" if round_number == max_rounds else "continue"),
                }
            )
            if stop_reason or round_number == max_rounds:
                break
            known_terms.update(new_terms)
            current_query = " ".join([query, *new_terms])

        screened, excluded, edge = self.screen_with_edge(pool, query, year_from, year_to, venues, must_include, exclude, precise)
        screened = screened[:limit]
        paths = self._write_outputs(query, screened, excluded, edge, rounds, errors)
        requested = str(arguments.get("output_path") or "").strip()
        if requested:
            paths["requested_output"] = str(self._save_requested(requested, query, screened))
        return {
            "message": self._search_message(screened, errors, paths),
            "artifacts": paths,
            "data": {"count": len(screened), "papers": screened, "rounds": rounds, "errors": errors},
        }

    def screen_active(self, papers_path: str, arguments: dict[str, Any]) -> dict[str, Any]:
        papers = json.loads(Path(papers_path).read_text(encoding="utf-8-sig"))
        query = str(arguments.get("query") or arguments.get("topic") or "").strip()
        if not query:
            query = str(arguments.get("keywords") or "").strip()
        if not query:
            raise ValueError("Screening needs a query")
        screened, excluded, edge = self.screen_with_edge(
            papers,
            query,
            self._int(arguments.get("year_from")),
            self._int(arguments.get("year_to")),
            [str(item) for item in arguments.get("venues") or []],
            [str(item) for item in arguments.get("must_include") or []],
            [str(item) for item in arguments.get("exclude") or []],
            bool(arguments.get("precise") or arguments.get("must_include") or arguments.get("exclude")),
        )
        active = self.session_dir / "screened_papers.json"
        dropped = self.session_dir / "excluded_papers.json"
        edge_path = self.session_dir / "edge_papers.json"
        active.write_text(json.dumps(screened, ensure_ascii=False, indent=2), encoding="utf-8")
        dropped.write_text(json.dumps(excluded, ensure_ascii=False, indent=2), encoding="utf-8")
        edge_path.write_text(json.dumps(edge, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "message": f"筛选完成：保留 {len(screened)} 篇，边缘 {len(edge)} 篇，排除 {len(excluded)} 篇。",
            "artifacts": {"active_papers": str(active), "excluded_papers": str(dropped), "edge_papers": str(edge_path)},
            "data": {"count": len(screened), "papers": screened, "edge": edge},
        }

    def screen(
        self,
        papers: list[dict[str, Any]],
        query: str,
        year_from: int | None,
        year_to: int | None,
        venues: list[str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        included, excluded, edge = self.screen_with_edge(papers, query, year_from, year_to, venues, [], [], False)
        return included, [*edge, *excluded]

    def screen_with_edge(
        self,
        papers: list[dict[str, Any]],
        query: str,
        year_from: int | None,
        year_to: int | None,
        venues: list[str],
        must_include: list[str],
        exclude: list[str],
        precise: bool,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        included, excluded, edge = [], [], []
        concepts = list(dict.fromkeys(tokens(" ".join(must_include) if must_include else query)))
        exclude_concepts = list(dict.fromkeys(tokens(" ".join(exclude))))
        for raw in papers:
            paper = dict(raw)
            year = self._int(paper.get("year"))
            venue = str(paper.get("venue") or "")
            reason = ""
            if year_from and year and year < year_from:
                reason = "before_year_range"
            elif year_to and year and year > year_to:
                reason = "after_year_range"
            elif venues and not any(item.lower() in venue.lower() for item in venues):
                reason = "venue_not_matched"
            score, reasons = self._score(paper, concepts)
            missing_required = [term for term in concepts if not self._paper_matches(paper, term)]
            excluded_terms = [term for term in exclude_concepts if self._paper_matches(paper, term)]
            if self._is_preprint(paper) and any(term in {"preprint", "arxiv"} for term in exclude_concepts):
                excluded_terms.append("preprint")
            if excluded_terms:
                reason = "excluded_terms:" + ",".join(dict.fromkeys(excluded_terms))
            elif precise and missing_required:
                reason = "missing_required_terms:" + ",".join(missing_required)
            paper["relevance_score"] = score
            paper["screening_reasons"] = reasons
            paper["missing_required_terms"] = missing_required
            paper["matched_required_terms"] = [term for term in concepts if term not in missing_required]
            # The score ranks evidence but never vetoes explicit criteria.
            # Hard exclusion comes only from user/model supplied constraints.
            if reason:
                paper["exclusion_reason"] = reason
                if reason.startswith("missing_required_terms") and paper["matched_required_terms"]:
                    edge.append(paper)
                else:
                    excluded.append(paper)
            else:
                included.append(paper)
        included.sort(key=lambda item: (item.get("relevance_score", 0), item.get("citation_count", 0)), reverse=True)
        excluded.sort(key=lambda item: item.get("relevance_score", 0), reverse=True)
        edge.sort(key=lambda item: item.get("relevance_score", 0), reverse=True)
        return included, excluded, edge

    def _score(self, paper: dict[str, Any], concepts: list[str]) -> tuple[int, list[str]]:
        if not concepts:
            return 50, ["no_query_terms"]
        title_terms = set(tokens(str(paper.get("title") or "")))
        abstract_terms = set(tokens(str(paper.get("abstract") or "")))
        title_hits = [term for term in concepts if self._matches(term, title_terms)]
        abstract_hits = [term for term in concepts if self._matches(term, abstract_terms)]
        title_ratio = len(title_hits) / len(concepts)
        abstract_ratio = len(abstract_hits) / len(concepts)
        score = title_ratio * 50 + abstract_ratio * 35
        if title_hits:
            score += 5
        if paper.get("abstract"):
            score += 3
        if paper.get("doi"):
            score += 2
        citations = max(0, self._int(paper.get("citation_count")) or 0)
        score += min(5, math.log10(citations + 1) * 2)
        reasons = []
        if title_hits:
            reasons.append("title:" + ",".join(title_hits))
        if abstract_hits:
            reasons.append("abstract:" + ",".join(abstract_hits))
        return max(0, min(100, round(score))), reasons

    def _matches(self, concept: str, terms: set[str]) -> bool:
        options = ALIASES.get(concept, {concept})
        return bool(options & terms)

    def _paper_matches(self, paper: dict[str, Any], concept: str) -> bool:
        full_text = " ".join(
            [
                str(paper.get("title") or ""),
                str(paper.get("abstract") or ""),
                str(paper.get("venue") or ""),
            ]
        ).lower()
        if concept.lower() in {"mdd", "depression"} and re.search(r"without\s+(?:depression|mdd)|without[^.]{0,40}(?:depression|mdd)|no\s+(?:depression|mdd)", full_text):
            return False
        terms = set(tokens(" ".join(
            [
                str(paper.get("title") or ""),
                str(paper.get("abstract") or ""),
                str(paper.get("venue") or ""),
                " ".join(str(item.get("display_name", "")) for item in (paper.get("keywords") or []) if isinstance(item, dict)),
            ]
        )))
        return self._matches(concept.lower(), terms)

    def _is_preprint(self, paper: dict[str, Any]) -> bool:
        venue = str(paper.get("venue") or "").lower()
        source = str(paper.get("source") or "").lower()
        raw_type = str((paper.get("raw_metadata") or {}).get("type") or paper.get("type") or "").lower()
        return "arxiv" in venue or "arxiv" in source or "preprint" in raw_type

    def _dedupe(self, papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for paper in papers:
            key = str(paper.get("doi") or "").lower().strip() or normalized_title(str(paper.get("title") or ""))
            if not key:
                continue
            if key not in merged:
                item = dict(paper)
                item["sources"] = [paper.get("source")] if paper.get("source") else []
                merged[key] = item
                continue
            current = merged[key]
            if len(str(paper.get("abstract") or "")) > len(str(current.get("abstract") or "")):
                current["abstract"] = paper.get("abstract")
            current["citation_count"] = max(
                self._int(current.get("citation_count")) or 0,
                self._int(paper.get("citation_count")) or 0,
            )
            for field in ("doi", "url", "venue", "year", "open_access_url"):
                if not current.get(field) and paper.get(field):
                    current[field] = paper[field]
            source = paper.get("source")
            if source and source not in current["sources"]:
                current["sources"].append(source)
        return list(merged.values())

    def _expand(self, papers: list[dict[str, Any]], known: set[str]) -> list[str]:
        counter: Counter[str] = Counter()
        for paper in papers[:10]:
            counter.update(tokens(f"{paper.get('title', '')} {paper.get('abstract', '')}"))
        return [term for term, _ in counter.most_common(30) if term not in known and term not in STOPWORDS][:2]

    def _write_outputs(
        self,
        query: str,
        screened: list[dict[str, Any]],
        excluded: list[dict[str, Any]],
        edge: list[dict[str, Any]],
        rounds: list[dict[str, Any]],
        errors: list[dict[str, str]],
    ) -> dict[str, str]:
        paths = {
            "raw_papers": self.session_dir / "papers_raw.json",
            "active_papers": self.session_dir / "screened_papers.json",
            "excluded_papers": self.session_dir / "excluded_papers.json",
            "edge_papers": self.session_dir / "edge_papers.json",
            "recursive_search_plan": self.session_dir / "recursive_search_plan.json",
            "paper_pool_markdown": self.session_dir / "paper_pool.md",
        }
        paths["raw_papers"].write_text(json.dumps(self._dedupe([*screened, *edge, *excluded]), ensure_ascii=False, indent=2), encoding="utf-8")
        paths["active_papers"].write_text(json.dumps(screened, ensure_ascii=False, indent=2), encoding="utf-8")
        paths["excluded_papers"].write_text(json.dumps(excluded, ensure_ascii=False, indent=2), encoding="utf-8")
        paths["edge_papers"].write_text(json.dumps(edge, ensure_ascii=False, indent=2), encoding="utf-8")
        paths["recursive_search_plan"].write_text(
            json.dumps({"query": query, "rounds": rounds, "errors": errors}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        paths["paper_pool_markdown"].write_text(self._markdown(query, screened, edge), encoding="utf-8")
        if errors:
            error_path = self.session_dir / "literature_search_errors.json"
            error_path.write_text(json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8")
            paths["literature_search_errors"] = error_path
        return {key: str(path) for key, path in paths.items()}

    def _markdown(self, query: str, papers: list[dict[str, Any]], edge: list[dict[str, Any]] | None = None) -> str:
        edge = edge or []
        lines = ["# Screened Literature Pool", "", f"Query: {query}", "", "## Included", ""]
        for index, paper in enumerate(papers, 1):
            title = paper.get("title") or "Untitled"
            url = paper.get("url") or paper.get("open_access_url") or ""
            title_text = f"[{title}]({url})" if url else title
            lines.extend(
                [
                    f"{index}. {title_text}",
                    f"   - Year: {paper.get('year') or 'unknown'}",
                    f"   - Venue: {paper.get('venue') or 'unknown'}",
                    f"   - Score: {paper.get('relevance_score', 0)}",
                    f"   - DOI: {paper.get('doi') or 'not available'}",
                ]
            )
        if edge:
            lines.extend(["", "## Borderline / Edge Papers", ""])
            for index, paper in enumerate(edge, 1):
                lines.extend(
                    [
                        f"{index}. {paper.get('title') or 'Untitled'}",
                        f"   - Year: {paper.get('year') or 'unknown'}",
                        f"   - Venue: {paper.get('venue') or 'unknown'}",
                        f"   - Reason: {paper.get('exclusion_reason') or 'borderline'}",
                    ]
                )
        return "\n".join(lines) + "\n"

    def _save_requested(self, raw: str, query: str, papers: list[dict[str, Any]]) -> Path:
        path = Path(raw).expanduser()
        if not path.suffix:
            path = path / "literature_search.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() == ".docx":
            try:
                from docx import Document
            except ImportError as exc:
                raise RuntimeError("DOCX output requires python-docx") from exc
            document = Document()
            document.add_heading("Screened Literature Pool", level=1)
            document.add_paragraph(f"Query: {query}")
            for index, paper in enumerate(papers, 1):
                document.add_heading(f"{index}. {paper.get('title') or 'Untitled'}", level=2)
                document.add_paragraph(
                    f"Year: {paper.get('year') or 'unknown'}; Venue: {paper.get('venue') or 'unknown'}; "
                    f"DOI: {paper.get('doi') or 'not available'}"
                )
            document.save(path)
        elif path.suffix.lower() == ".json":
            path.write_text(json.dumps(papers, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            if path.suffix.lower() not in {".md", ".txt"}:
                path = path.with_suffix(".md")
            path.write_text(self._markdown(query, papers), encoding="utf-8")
        return path

    def _search_message(self, papers: list[dict[str, Any]], errors: list[dict[str, str]], paths: dict[str, str]) -> str:
        if not papers:
            detail = "；".join(f"{item['source']}: {item['error']}" for item in errors[:3])
            return "没有检索到符合条件的论文。" + (f" 数据源错误：{detail}" if detail else " 请放宽关键词或期刊范围。")
        lines = [f"找到并筛选出 {len(papers)} 篇论文："]
        for index, paper in enumerate(papers[:8], 1):
            lines.append(f"{index}. {paper.get('title')} ({paper.get('year') or '?'}, {paper.get('venue') or 'venue unknown'})")
        if len(papers) > 8:
            lines.append(f"其余 {len(papers) - 8} 篇已写入文献池。")
        if errors:
            lines.append("部分数据源失败，但已保留其他来源结果。")
        lines.append(f"文献池：{paths.get('requested_output') or paths['paper_pool_markdown']}")
        return "\n".join(lines)

    def _client(self, source: str):
        return {
            "openalex": OpenAlexClient(self.config),
            "pubmed": PubMedClient(self.config),
            "semantic_scholar": SemanticScholarClient(self.config),
            "arxiv": ArxivClient(),
        }.get(source)

    def _int(self, value: Any) -> int | None:
        try:
            return int(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None
