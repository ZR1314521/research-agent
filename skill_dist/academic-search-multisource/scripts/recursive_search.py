#!/usr/bin/env python3
import argparse
import json
import re
import time
from collections import Counter
from pathlib import Path


STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "using", "based", "study",
    "research", "paper", "method", "methods", "results", "analysis", "system",
}


def tokens(text: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", text or "") if t.lower() not in STOPWORDS]


def normalize_title(title: str) -> str:
    return re.sub(r"\W+", " ", (title or "").lower()).strip()


def load_papers(paths: list[str]) -> list[dict]:
    papers = []
    for raw in paths:
        data = json.loads(Path(raw).read_text(encoding="utf-8-sig"))
        if isinstance(data, dict):
            data = data.get("papers") or data.get("results") or data.get("references") or [data]
        papers.extend(data)
    return papers


def normalize_paper(item: dict, source: str = "input") -> dict:
    authors = item.get("authors") or item.get("author") or []
    if isinstance(authors, str):
        authors = [x.strip() for x in re.split(r";|,", authors) if x.strip()]
    doi = (item.get("doi") or item.get("DOI") or "").lower().replace("https://doi.org/", "")
    title = item.get("title") or item.get("name") or ""
    year = item.get("year") or item.get("publication_year") or item.get("published") or ""
    if isinstance(year, str) and len(year) >= 4 and year[:4].isdigit():
        year = int(year[:4])
    return {
        "id": item.get("id") or doi or normalize_title(title),
        "title": title,
        "authors": authors,
        "year": year,
        "venue": item.get("venue") or item.get("journal") or item.get("container-title") or "",
        "abstract": item.get("abstract") or item.get("summary") or "",
        "doi": doi,
        "url": item.get("url") or item.get("link") or "",
        "source": item.get("source") or source,
        "keywords": item.get("keywords") or [],
        "raw_metadata": item,
    }


def dedupe(papers: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for p in papers:
        key = p.get("doi") or normalize_title(p.get("title", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def score(paper: dict, query_terms: set[str], include_terms: set[str], exclude_terms: set[str], venues: list[str], years: tuple[int | None, int | None]) -> tuple[int, list[str]]:
    text = " ".join([paper.get("title", ""), paper.get("abstract", ""), paper.get("venue", ""), " ".join(paper.get("keywords") or [])])
    term_set = set(tokens(text))
    score_value = 0
    reasons = []
    overlap = query_terms & term_set
    if overlap:
        score_value += min(50, len(overlap) * 10)
        reasons.append("query_overlap:" + ",".join(sorted(overlap)[:8]))
    inc = include_terms & term_set
    if inc:
        score_value += min(25, len(inc) * 8)
        reasons.append("include_overlap:" + ",".join(sorted(inc)[:6]))
    exc = exclude_terms & term_set
    if exc:
        score_value -= min(70, len(exc) * 25)
        reasons.append("exclude_overlap:" + ",".join(sorted(exc)[:6]))
    if venues:
        venue_text = (paper.get("venue") or "").lower()
        if any(v.lower() in venue_text for v in venues):
            score_value += 20
            reasons.append("venue_match")
        else:
            score_value -= 10
            reasons.append("venue_not_matched")
    year_from, year_to = years
    year = paper.get("year")
    if isinstance(year, int):
        if year_from and year < year_from:
            score_value -= 20
            reasons.append("before_year_range")
        if year_to and year > year_to:
            score_value -= 20
            reasons.append("after_year_range")
    if paper.get("doi"):
        score_value += 5
    if paper.get("abstract"):
        score_value += 10
    return max(0, min(100, score_value)), reasons


def expand_terms(papers: list[dict], existing: set[str], limit: int = 8) -> list[str]:
    counter = Counter()
    for p in papers[:20]:
        counter.update(tokens((p.get("title") or "") + " " + (p.get("abstract") or "")))
    return [term for term, _ in counter.most_common(50) if term not in existing][:limit]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run bounded recursive literature screening over local raw paper pools.")
    parser.add_argument("inputs", nargs="+", help="Raw paper JSON files.")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--keywords", default="")
    parser.add_argument("--include", default="")
    parser.add_argument("--exclude", default="")
    parser.add_argument("--venues", default="", help="Comma-separated venue or journal constraints.")
    parser.add_argument("--year-from", type=int)
    parser.add_argument("--year-to", type=int)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--threshold", type=int, default=60)
    parser.add_argument("--target", type=int, default=30)
    parser.add_argument("--out-dir", default=".")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw = [normalize_paper(p, Path(src).stem) for src in args.inputs for p in load_papers([src])]
    pool = dedupe(raw)
    query_terms = set(tokens(args.topic + " " + args.keywords))
    include_terms = set(tokens(args.include))
    exclude_terms = set(tokens(args.exclude))
    venues = [v.strip() for v in args.venues.split(",") if v.strip()]
    rounds = []
    kept_final: list[dict] = []
    dropped_final: list[dict] = []

    for i in range(1, max(1, args.rounds) + 1):
        scored = []
        dropped = []
        for paper in pool:
            s, reasons = score(paper, query_terms, include_terms, exclude_terms, venues, (args.year_from, args.year_to))
            item = dict(paper)
            item["relevance_score"] = s
            item["screening_reasons"] = reasons
            if s >= args.threshold:
                scored.append(item)
            else:
                item["exclusion_reason"] = "score_below_threshold"
                dropped.append(item)
        scored.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        (out_dir / f"search_round_{i}.json").write_text(json.dumps(scored, ensure_ascii=False, indent=2), encoding="utf-8")
        new_terms = expand_terms(scored, query_terms)
        rounds.append(
            {
                "round": i,
                "query_terms": sorted(query_terms),
                "kept": len(scored),
                "excluded": len(dropped),
                "new_terms": new_terms,
                "stop_reason": "",
            }
        )
        kept_final, dropped_final = scored, dropped
        if len(scored) >= args.target:
            rounds[-1]["stop_reason"] = "target_reached"
            break
        if not new_terms:
            rounds[-1]["stop_reason"] = "no_new_terms"
            break
        query_terms.update(new_terms)

    plan = {
        "topic": args.topic,
        "initial_keywords": args.keywords,
        "venue_scope": venues,
        "year_range": [args.year_from, args.year_to],
        "threshold": args.threshold,
        "target": args.target,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "rounds": rounds,
    }
    (out_dir / "recursive_search_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "papers.json").write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "screened_papers.json").write_text(json.dumps(kept_final, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "excluded_papers.json").write_text(json.dumps(dropped_final, ensure_ascii=False, indent=2), encoding="utf-8")
    log = ["# Recursive Screening Log", "", f"Topic: {args.topic}", ""]
    for r in rounds:
        log.append(f"- Round {r['round']}: kept={r['kept']}, excluded={r['excluded']}, new_terms={', '.join(r['new_terms']) or 'none'}, stop={r['stop_reason'] or 'continue'}")
    (out_dir / "screening_log.md").write_text("\n".join(log) + "\n", encoding="utf-8")
    print(out_dir / "screened_papers.json")


if __name__ == "__main__":
    main()
