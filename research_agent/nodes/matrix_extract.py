from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from research_agent.nodes.base import BaseNode, NodeError
from research_agent.state import RunState


def _citation_key(paper: dict) -> str:
    authors = paper.get("authors") or []
    first = "paper"
    if authors:
        first = re.sub(r"\W+", "", str(authors[0]).split()[-1].lower()) or "paper"
    return f"{first}{paper.get('year') or 'nd'}"


class MatrixExtractNode(BaseNode):
    name = "matrix_extract"

    def run(self, state: RunState) -> RunState:
        state.mark_running(self.name)
        screened = state.artifacts.get("screened_papers")
        if not screened:
            raise NodeError("No screened_papers artifact available")
        papers = json.loads(Path(screened).read_text(encoding="utf-8"))
        fields = [
            "citation_key",
            "title",
            "authors",
            "year",
            "venue",
            "abstract_summary",
            "innovation",
            "conclusion",
            "limitations",
            "relevance_score",
            "source_url",
            "doi",
        ]
        rows = []
        notes = ["# Literature Summary Notes", ""]
        for paper in papers:
            abstract = (paper.get("abstract") or "").replace("\n", " ")
            row = {
                "citation_key": _citation_key(paper),
                "title": paper.get("title", ""),
                "authors": "; ".join(paper.get("authors") or []),
                "year": paper.get("year", ""),
                "venue": paper.get("venue", ""),
                "abstract_summary": abstract,
                "innovation": "NEEDS_LLM_OR_FULLTEXT",
                "conclusion": "NEEDS_LLM_OR_FULLTEXT",
                "limitations": "NEEDS_LLM_OR_FULLTEXT",
                "relevance_score": paper.get("relevance_score", ""),
                "source_url": paper.get("url", ""),
                "doi": paper.get("doi", ""),
            }
            rows.append(row)
            notes.append(f"- **{row['citation_key']}** {row['title']}: {row['abstract_summary']}")
        csv_path = self.run_dir / "literature_matrix.csv"
        with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        md_path = self.run_dir / "literature_matrix.md"
        md_lines = ["# Literature Matrix", "", "| Citation | Title | Year | Innovation | Conclusion |", "|---|---|---:|---|---|"]
        for row in rows:
            md_lines.append(f"| {row['citation_key']} | {row['title']} | {row['year']} | {row['innovation']} | {row['conclusion']} |")
        md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
        notes_path = self.run_dir / "summary_notes.md"
        notes_path.write_text("\n".join(notes) + "\n", encoding="utf-8")
        state.add_artifact("literature_matrix_csv", csv_path)
        state.add_artifact("literature_matrix_md", md_path)
        state.add_artifact("summary_notes", notes_path)
        state.mark_completed(self.name, f"Extracted matrix for {len(rows)} paper(s)")
        return state
