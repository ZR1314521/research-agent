from pathlib import Path
import textwrap


ROOT = Path.home() / ".codex" / "skills"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")


def skill(name: str, description: str, body: str, files: dict[str, str]) -> None:
    base = ROOT / name
    write(
        base / "SKILL.md",
        f"""\
        ---
        name: {name}
        description: {description}
        ---

        {body}
        """,
    )
    for rel, content in files.items():
        write(base / rel, content)


skill(
    "workflow-state-manager",
    "Use when Codex needs to orchestrate long-running research workflows with checkpoints, pause/resume, human-in-the-loop decisions, artifact tracking, execution logs, task state files, or recovery after interruption. Triggers include workflow state, checkpoint, resume, pause task, continue research workflow, execution log, human intervention, and agent workflow status.",
    """\
    # Workflow State Manager

    Use this skill as the control layer for the research-agent workflow. It records state, routes to other skills, and preserves checkpoints.

    ## Standard Workflow

    1. Create or load `workflow_state.json`.
    2. Before each major step, record step name, input artifacts, expected outputs, downstream skill, and start time.
    3. After each step, record status, generated artifacts, result summary, and next step.
    4. At human checkpoints, pause and record the user's decision.
    5. On resume, read state, verify artifacts, and continue from `current_step`.

    ## Default Steps

    `academic-search-multisource -> literature-screening -> literature-matrix-extraction -> systematic-literature-review -> experiment-data-analysis -> 20-ml-paper-writing -> reference-format-gbt7714 -> docx -> final-review`

    ## Scripts

    - `scripts/init_state.py`: create a state file.
    - `scripts/update_state.py`: append events and update current step.
    - `scripts/resume_state.py`: print resume guidance.

    ## Rules

    - Never discard artifacts. Version or append instead.
    - Never silently skip failed steps.
    - Record human decisions in `human_decisions`.
    - Use `langgraph-human-in-the-loop` when checkpoint design needs workflow patterns.
    """,
    {
        "references/state_schema.md": """\
        # Workflow State Schema

        Required fields: `project_id`, `topic`, `current_step`, `status`, `completed_steps`, `pending_steps`, `artifacts`, `checkpoints`, `human_decisions`, `execution_log`.
        """,
        "scripts/init_state.py": """\
        #!/usr/bin/env python3
        import argparse, json, time, uuid
        from pathlib import Path
        DEFAULT_STEPS = ["academic-search-multisource","literature-screening","literature-matrix-extraction","systematic-literature-review","experiment-data-analysis","20-ml-paper-writing","reference-format-gbt7714","docx","final-review"]
        p = argparse.ArgumentParser()
        p.add_argument("--topic", required=True)
        p.add_argument("--out", default="workflow_state.json")
        p.add_argument("--steps", nargs="*")
        a = p.parse_args()
        steps = a.steps or DEFAULT_STEPS
        state = {"project_id": str(uuid.uuid4()), "topic": a.topic, "current_step": steps[0], "status": "initialized", "completed_steps": [], "pending_steps": steps, "artifacts": {}, "checkpoints": [], "human_decisions": [], "execution_log": [{"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "step": "init", "status": "completed", "summary": "State initialized"}]}
        Path(a.out).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        print(a.out)
        """,
        "scripts/update_state.py": """\
        #!/usr/bin/env python3
        import argparse, json, time
        from pathlib import Path
        p = argparse.ArgumentParser()
        p.add_argument("state")
        p.add_argument("--step", required=True)
        p.add_argument("--status", required=True, choices=["running","completed","needs_user","blocked"])
        p.add_argument("--summary", default="")
        p.add_argument("--artifact", action="append", default=[], help="key=path")
        p.add_argument("--decision", default="")
        a = p.parse_args()
        path = Path(a.state)
        state = json.loads(path.read_text(encoding="utf-8"))
        state["current_step"] = a.step
        state["status"] = a.status
        if a.status == "completed" and a.step not in state.get("completed_steps", []):
            state.setdefault("completed_steps", []).append(a.step)
            state["pending_steps"] = [s for s in state.get("pending_steps", []) if s != a.step]
        for item in a.artifact:
            if "=" in item:
                k, v = item.split("=", 1)
                state.setdefault("artifacts", {})[k] = v
        if a.decision:
            state.setdefault("human_decisions", []).append({"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "step": a.step, "decision": a.decision})
        state.setdefault("execution_log", []).append({"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "step": a.step, "status": a.status, "summary": a.summary})
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        print(a.state)
        """,
        "scripts/resume_state.py": """\
        #!/usr/bin/env python3
        import argparse, json
        from pathlib import Path
        p = argparse.ArgumentParser()
        p.add_argument("state")
        a = p.parse_args()
        s = json.loads(Path(a.state).read_text(encoding="utf-8"))
        print("topic:", s.get("topic"))
        print("status:", s.get("status"))
        print("current_step:", s.get("current_step"))
        print("pending_steps:", ", ".join(s.get("pending_steps", [])))
        print("artifacts:")
        for k, v in s.get("artifacts", {}).items():
            print(f"- {k}: {v}")
        """,
    },
)


skill(
    "academic-search-multisource",
    "Use when Codex needs multi-source academic literature retrieval across OpenAlex, PubMed, Semantic Scholar, and arXiv; combines search results into one normalized paper pool for downstream screening, literature matrix extraction, review writing, or citation formatting. Triggers include multi-source literature search, academic search, paper pool, OpenAlex plus PubMed, Semantic Scholar search, and recursive literature retrieval.",
    """\
    # Academic Search Multisource

    Use this skill to create a normalized paper pool. Route actual search to trusted existing search skills, then merge and normalize results.

    ## Routing

    - OpenAlex: use `literature-search-openalex`.
    - PubMed: use `pubmed-database`.
    - Semantic Scholar: use `semanticscholar-skill`.
    - arXiv: use `systematic-literature-review` for SLR-style search or `read-arxiv-paper` for single papers.

    ## Workflow

    1. Parse topic, keywords, date range, venue scope, database scope, and max results.
    2. Run selected source searches.
    3. Save raw source results separately.
    4. Normalize and merge raw results with `scripts/merge_paper_pool.py`.
    5. Output `papers.json` and pass it to `literature-screening`.

    ## Rules

    - Do not screen aggressively here.
    - Preserve raw metadata in `raw_metadata`.
    - Mark missing DOI or abstract as empty, not fabricated.
    """,
    {
        "references/paper_schema.md": """\
        # Paper Pool Schema

        Fields: `id`, `title`, `authors`, `year`, `venue`, `abstract`, `doi`, `url`, `source`, `keywords`, `raw_metadata`.
        """,
        "scripts/merge_paper_pool.py": """\
        #!/usr/bin/env python3
        import argparse, json, re
        from pathlib import Path
        def nt(t): return re.sub(r"\\W+", " ", (t or "").lower()).strip()
        def norm(p, source):
            title = p.get("title") or p.get("name") or ""
            doi = (p.get("doi") or p.get("DOI") or "").lower().replace("https://doi.org/", "")
            authors = p.get("authors") or p.get("author") or []
            if isinstance(authors, str): authors = [x.strip() for x in authors.split(",") if x.strip()]
            year = p.get("year") or p.get("publication_year") or p.get("published") or ""
            if isinstance(year, str) and len(year) >= 4 and year[:4].isdigit(): year = int(year[:4])
            return {"id": p.get("id") or doi or nt(title), "title": title, "authors": authors, "year": year, "venue": p.get("venue") or p.get("journal") or p.get("container-title") or "", "abstract": p.get("abstract") or p.get("summary") or "", "doi": doi, "url": p.get("url") or p.get("link") or "", "source": p.get("source") or source, "keywords": p.get("keywords") or [], "raw_metadata": p}
        ap = argparse.ArgumentParser()
        ap.add_argument("inputs", nargs="+")
        ap.add_argument("--out", default="papers.json")
        a = ap.parse_args()
        seen, merged = set(), []
        for inp in a.inputs:
            data = json.loads(Path(inp).read_text(encoding="utf-8"))
            if isinstance(data, dict): data = data.get("papers") or data.get("results") or [data]
            for item in data:
                p = norm(item, Path(inp).stem)
                key = p["doi"] or nt(p["title"])
                if key and key not in seen:
                    seen.add(key); merged.append(p)
        Path(a.out).write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        print(a.out)
        """,
    },
)


skill(
    "literature-screening",
    "Use when Codex needs to screen, deduplicate, rank, include, exclude, or recursively filter academic literature pools based on topic relevance, user criteria, venue scope, year range, abstracts, keywords, and inclusion/exclusion rules. Triggers include literature screening, recursive screening, relevance scoring, inclusion exclusion, paper filtering, and precise literature pool.",
    """\
    # Literature Screening

    Use this skill after `academic-search-multisource`. It turns a broad paper pool into a precise, auditable literature pool.

    ## Workflow

    1. Load `papers.json`.
    2. Deduplicate by DOI, arXiv ID, and normalized title.
    3. Score each paper from 0 to 100 using title, abstract, keywords, venue, and year.
    4. Apply inclusion and exclusion rules.
    5. Put uncertain papers in a human-review bucket.
    6. If too many papers remain, ask for a checkpoint decision or tighten keywords.
    7. Output `screened_papers.json`, `excluded_papers.json`, and `screening_log.md`.

    ## Rules

    - Every excluded paper needs a reason.
    - Prefer conservative inclusion for foundational papers.
    - Pass screened papers to `literature-matrix-extraction`.
    """,
    {
        "references/scoring_rubric.md": """\
        # Screening Scoring Rubric

        80-100 directly relevant. 60-79 likely relevant. 40-59 human review. 0-39 exclude unless foundational.
        """,
        "scripts/screen_papers.py": """\
        #!/usr/bin/env python3
        import argparse, json, re
        from pathlib import Path
        def toks(s): return set(re.findall(r"[a-zA-Z0-9_\\-]+", (s or "").lower()))
        ap = argparse.ArgumentParser()
        ap.add_argument("papers")
        ap.add_argument("--query", required=True)
        ap.add_argument("--include", default="")
        ap.add_argument("--exclude", default="")
        ap.add_argument("--threshold", type=int, default=60)
        ap.add_argument("--out", default="screened_papers.json")
        ap.add_argument("--excluded", default="excluded_papers.json")
        a = ap.parse_args()
        papers = json.loads(Path(a.papers).read_text(encoding="utf-8"))
        q, inc, exc = toks(a.query), toks(a.include), toks(a.exclude)
        kept, dropped = [], []
        for p in papers:
            text = toks((p.get("title") or "") + " " + (p.get("abstract") or ""))
            score = min(60, len(q & text) * 12) + min(25, len(inc & text) * 8) - min(60, len(exc & text) * 20)
            p["relevance_score"] = max(0, min(100, score))
            if p["relevance_score"] >= a.threshold:
                kept.append(p)
            else:
                p["exclusion_reason"] = "score_below_threshold"; dropped.append(p)
        kept.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        Path(a.out).write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
        Path(a.excluded).write_text(json.dumps(dropped, ensure_ascii=False, indent=2), encoding="utf-8")
        Path("screening_log.md").write_text(f"# Screening Log\\n\\nKept: {len(kept)}\\nExcluded: {len(dropped)}\\n", encoding="utf-8")
        print(a.out)
        """,
    },
)


skill(
    "literature-matrix-extraction",
    "Use when Codex needs to extract structured evidence from academic papers, build evidence matrices, summarize title/authors/abstract/method/innovation/findings/limitations, or prepare literature-review inputs from screened paper pools. Triggers include evidence matrix, literature matrix, paper information extraction, innovation extraction, method extraction, findings table, and review framework input.",
    """\
    # Literature Matrix Extraction

    Use this skill after `literature-screening`. It creates a structured evidence matrix for review writing and paper drafting.

    ## Workflow

    1. Load `screened_papers.json`.
    2. Extract title, authors, year, venue, abstract summary, research question, method, dataset, innovation, findings, limitations, relevance score, and citation key.
    3. For important arXiv papers, use `read-arxiv-paper`.
    4. Save `literature_matrix.csv`, `literature_matrix.md`, and `summary_notes.md`.
    5. Pass the matrix to `doc-coauthoring`, `systematic-literature-review`, or `20-ml-paper-writing`.

    ## Rules

    - Do not invent datasets, results, or limitations.
    - Use `NEEDS_READING` when metadata is insufficient.
    """,
    {
        "references/matrix_schema.md": "Columns: citation_key,title,authors,year,venue,abstract_summary,research_question,method,dataset,innovation,key_findings,limitations,relevance_score,source_url,doi.\n",
        "scripts/build_matrix.py": """\
        #!/usr/bin/env python3
        import argparse, csv, json, re
        from pathlib import Path
        def key(p):
            a = p.get("authors") or []
            first = re.sub(r"\\W+", "", str(a[0]).split()[-1].lower()) if a else "paper"
            return f"{first or 'paper'}{p.get('year') or 'nd'}"
        ap = argparse.ArgumentParser()
        ap.add_argument("papers")
        ap.add_argument("--csv", default="literature_matrix.csv")
        ap.add_argument("--md", default="literature_matrix.md")
        a = ap.parse_args()
        papers = json.loads(Path(a.papers).read_text(encoding="utf-8"))
        fields = ["citation_key","title","authors","year","venue","abstract_summary","research_question","method","dataset","innovation","key_findings","limitations","relevance_score","source_url","doi"]
        rows = []
        for p in papers:
            abstract = (p.get("abstract") or "").replace("\\n", " ")
            rows.append({"citation_key": key(p), "title": p.get("title",""), "authors": "; ".join(p.get("authors") or []), "year": p.get("year",""), "venue": p.get("venue",""), "abstract_summary": abstract[:320], "research_question": "NEEDS_READING", "method": "NEEDS_READING", "dataset": "NEEDS_READING", "innovation": "NEEDS_READING", "key_findings": "NEEDS_READING", "limitations": "NEEDS_READING", "relevance_score": p.get("relevance_score",""), "source_url": p.get("url",""), "doi": p.get("doi","")})
        with open(a.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
        lines = ["# Literature Matrix", "", "| Citation | Title | Year | Method | Innovation | Findings |", "|---|---|---:|---|---|---|"]
        for r in rows: lines.append(f"| {r['citation_key']} | {r['title']} | {r['year']} | {r['method']} | {r['innovation']} | {r['key_findings']} |")
        Path(a.md).write_text("\\n".join(lines) + "\\n", encoding="utf-8")
        print(a.csv)
        """,
    },
)


skill(
    "experiment-data-analysis",
    "Use when Codex needs to analyze uploaded experimental data files such as CSV, XLSX, TSV, or text tables; performs descriptive statistics, missing-value checks, outlier marking, trend analysis, group comparisons, and visualization recommendations before paper writing. Triggers include experiment data analysis, statistical summary, outlier detection, trend analysis, visualization suggestions, uploaded table analysis, CSV analysis, and XLSX analysis.",
    """\
    # Experiment Data Analysis

    Use this skill before paper writing. It turns raw experiment data into structured results suitable for `20-ml-paper-writing`.

    ## Workflow

    1. Identify uploaded data files: CSV, TSV, XLSX, or text tables.
    2. Run `scripts/analyze_table.py` when possible.
    3. Produce descriptive statistics, missing-value report, outlier report, trend hints, group comparison hints, and visualization recommendations.
    4. Save `analysis_summary.json` and `analysis_report.md`.
    5. Pass `analysis_summary.json` to `20-ml-paper-writing`.

    ## Rules

    - Do not write paper conclusions directly from raw data.
    - Do not run significance tests unless the experimental design supports them.
    - For XLSX, use pandas/openpyxl if available; otherwise ask user to export CSV.
    """,
    {
        "references/analysis_output_schema.md": "Fields: file,row_count,columns,numeric_summary,missing_values,visualization_recommendations,assumptions.\n",
        "scripts/analyze_table.py": """\
        #!/usr/bin/env python3
        import argparse, csv, json, math, statistics
        from pathlib import Path
        def load(path):
            suf = Path(path).suffix.lower()
            if suf in [".xlsx", ".xls"]:
                import pandas as pd
                return pd.read_excel(path).to_dict(orient="records")
            delim = "\\t" if suf == ".tsv" else ","
            with open(path, newline="", encoding="utf-8-sig") as f: return list(csv.DictReader(f, delimiter=delim))
        def num(v):
            try: return None if v is None or str(v).strip() == "" else float(v)
            except Exception: return None
        def q(vals, frac):
            vals = sorted(vals); pos = (len(vals)-1)*frac; lo = math.floor(pos); hi = math.ceil(pos)
            return vals[lo] if lo == hi else vals[lo]*(hi-pos)+vals[hi]*(pos-lo)
        ap = argparse.ArgumentParser()
        ap.add_argument("file")
        ap.add_argument("--json", default="analysis_summary.json")
        ap.add_argument("--md", default="analysis_report.md")
        a = ap.parse_args()
        rows = load(a.file); cols = list(rows[0].keys()) if rows else []
        missing = {c: 0 for c in cols}; numeric = {}
        for c in cols:
            vals = []
            for r in rows:
                v = r.get(c)
                if v is None or str(v).strip() == "": missing[c] += 1
                n = num(v)
                if n is not None: vals.append(n)
            if vals and len(vals) >= max(2, len(rows)//2):
                q1, q3 = q(vals, .25), q(vals, .75); iqr = q3-q1; low, high = q1-1.5*iqr, q3+1.5*iqr
                numeric[c] = {"count": len(vals), "mean": statistics.mean(vals), "median": statistics.median(vals), "stdev": statistics.stdev(vals) if len(vals)>1 else 0, "min": min(vals), "max": max(vals), "q1": q1, "q3": q3, "outlier_count_iqr": len([v for v in vals if v < low or v > high])}
        viz = ["Use boxplots for numeric columns with outliers.", "Use bar charts for grouped means if categorical group columns exist.", "Use line charts for numeric columns ordered by time/epoch/step columns."] if numeric else []
        summary = {"file": a.file, "row_count": len(rows), "columns": cols, "numeric_summary": numeric, "missing_values": missing, "visualization_recommendations": viz, "assumptions": ["IQR outliers are exploratory flags, not automatic exclusions."]}
        Path(a.json).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        lines = ["# Experiment Data Analysis", "", f"File: `{a.file}`", f"Rows: {len(rows)}", "", "## Numeric Summary"]
        for c, s in numeric.items(): lines.append(f"- `{c}`: mean={s['mean']:.4g}, median={s['median']:.4g}, sd={s['stdev']:.4g}, min={s['min']:.4g}, max={s['max']:.4g}, IQR outliers={s['outlier_count_iqr']}")
        lines += ["", "## Visualization Recommendations"] + [f"- {x}" for x in viz]
        Path(a.md).write_text("\\n".join(lines) + "\\n", encoding="utf-8")
        print(a.json)
        """,
    },
)


skill(
    "reference-format-gbt7714",
    "Use when Codex needs to format, convert, check, or correct academic references in GB/T 7714, APA, IEEE, BibTeX, or CSL-like styles; verifies DOI/arXiv metadata, fixes author/year/title/venue fields, and checks citation-reference consistency. Triggers include GB/T 7714, reference formatting, citation formatting, bibliography style conversion, DOI checking, BibTeX conversion, and reference audit.",
    """\
    # Reference Format GB/T 7714

    Use this skill to normalize references and format them. Detailed GB/T 7714 assets can be added later when the user provides official or journal-specific format material.

    ## Workflow

    1. Load references from DOI list, BibTeX, RIS, `papers.json`, or `literature_matrix.csv`.
    2. Normalize authors, title, year, venue, volume, issue, pages, DOI, and URL.
    3. Verify available identifiers. Never fabricate DOI or venue fields.
    4. Format GB/T 7714 draft, APA draft, IEEE draft, and BibTeX draft.
    5. Mark uncertain fields as `NEEDS_CHECK`.
    6. Pass final reference text to `docx` for Word manuscripts.

    ## Rules

    - Do not claim strict GB/T 7714 compliance until official or journal-specific material is included.
    - Preserve original metadata.
    - Produce a `citation_check_report.md` listing missing or suspicious fields.
    """,
    {
        "references/citation_input_schema.md": "Fields: type,authors,title,year,venue,volume,issue,pages,doi,url.\n",
        "scripts/format_references.py": """\
        #!/usr/bin/env python3
        import argparse, json, re
        from pathlib import Path
        def load(path):
            text = Path(path).read_text(encoding="utf-8")
            if path.lower().endswith(".json"):
                data = json.loads(text); return data.get("references") if isinstance(data, dict) and "references" in data else data
            return [{"title": x.strip(), "type": "unknown"} for x in text.splitlines() if x.strip()]
        def authors(a):
            if not a: return "NEEDS_CHECK"
            if isinstance(a, str): a = [x.strip() for x in a.split(";") if x.strip()]
            return ", ".join(a[:3]) + (", et al" if len(a) > 3 else "")
        def key(r):
            a = r.get("authors") or []; first = re.sub(r"\\W+", "", a[0].split()[-1].lower()) if isinstance(a, list) and a else "ref"
            return f"{first or 'ref'}{r.get('year') or 'nd'}"
        def gbt(r):
            mark = {"journal":"J","conference":"C","book":"M","preprint":"EB/OL","web":"EB/OL"}.get(r.get("type"), "Z")
            tail = f" DOI:{r.get('doi')}." if r.get("doi") else (f" {r.get('url')}." if r.get("url") else "")
            return f"{authors(r.get('authors'))}. {r.get('title') or 'NEEDS_CHECK'}[{mark}]. {r.get('venue') or 'NEEDS_CHECK'}, {r.get('year') or 'NEEDS_CHECK'}.{tail}"
        def bib(r):
            typ = "article" if r.get("type") == "journal" else "misc"
            auth = " and ".join(r.get("authors") or []) if isinstance(r.get("authors"), list) else (r.get("authors") or "NEEDS_CHECK")
            fields = {"title": r.get("title") or "NEEDS_CHECK", "author": auth, "year": str(r.get("year") or "NEEDS_CHECK"), "journal": r.get("venue") or "", "doi": r.get("doi") or "", "url": r.get("url") or ""}
            body = ",\\n".join([f"  {k} = {{{v}}}" for k, v in fields.items() if v])
            return f"@{typ}{{{key(r)},\\n{body}\\n}}"
        ap = argparse.ArgumentParser()
        ap.add_argument("input")
        ap.add_argument("--gbt", default="references_gbt7714.md")
        ap.add_argument("--bib", default="references.bib")
        ap.add_argument("--report", default="citation_check_report.md")
        a = ap.parse_args()
        refs = load(a.input); g, b, rep = ["# References GB/T 7714 Draft", ""], [], ["# Citation Check Report", ""]
        for i, r in enumerate(refs, 1):
            g.append(f"[{i}] {gbt(r)}"); b.append(bib(r))
            miss = [k for k in ["authors","title","year","venue"] if not r.get(k)]
            if miss: rep.append(f"- Reference {i}: missing {', '.join(miss)}")
        Path(a.gbt).write_text("\\n".join(g) + "\\n", encoding="utf-8")
        Path(a.bib).write_text("\\n\\n".join(b) + "\\n", encoding="utf-8")
        Path(a.report).write_text("\\n".join(rep) + "\\n", encoding="utf-8")
        print(a.gbt)
        """,
    },
)


print("created", ROOT)
