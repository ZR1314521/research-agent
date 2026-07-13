from __future__ import annotations

import csv
import json
import math
import statistics
from pathlib import Path

from research_agent.nodes.base import BaseNode
from research_agent.state import RunState


def _num(value):
    try:
        return None if value is None or str(value).strip() == "" else float(value)
    except Exception:
        return None


class ExperimentAnalysisNode(BaseNode):
    name = "experiment_analysis"

    def run(self, state: RunState) -> RunState:
        state.mark_running(self.name)
        manifest_path = state.artifacts.get("upload_manifest")
        summaries = []
        if manifest_path:
            manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            for item in manifest.get("files", []):
                if item.get("category") == "data" and item.get("extension") in {".csv", ".tsv"}:
                    summaries.append(self._analyze_csv(Path(item["stored_path"])))
        summary = {"files": summaries}
        out_json = self.run_dir / "analysis_summary.json"
        out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        out_md = self.run_dir / "analysis_report.md"
        lines = ["# Experiment Data Analysis", ""]
        if not summaries:
            lines.append("No CSV/TSV experiment data uploaded.")
        for item in summaries:
            lines.append(f"## {item['file']}")
            lines.append(f"- Rows: {item['row_count']}")
            for col, stats in item["numeric_summary"].items():
                lines.append(f"- `{col}`: mean={stats['mean']:.4g}, median={stats['median']:.4g}, outliers={stats['outlier_count_iqr']}")
        out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
        state.add_artifact("analysis_summary", out_json)
        state.add_artifact("analysis_report", out_md)
        state.mark_completed(self.name, f"Analyzed {len(summaries)} experiment data file(s)")
        return state

    def _analyze_csv(self, path: Path) -> dict:
        delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
        with path.open(newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f, delimiter=delimiter))
        cols = list(rows[0].keys()) if rows else []
        numeric = {}
        for col in cols:
            vals = [_num(row.get(col)) for row in rows]
            vals = [v for v in vals if v is not None]
            if len(vals) >= max(2, len(rows) // 2):
                ordered = sorted(vals)
                q1 = ordered[math.floor((len(ordered) - 1) * 0.25)]
                q3 = ordered[math.floor((len(ordered) - 1) * 0.75)]
                iqr = q3 - q1
                low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
                numeric[col] = {
                    "count": len(vals),
                    "mean": statistics.mean(vals),
                    "median": statistics.median(vals),
                    "stdev": statistics.stdev(vals) if len(vals) > 1 else 0,
                    "min": min(vals),
                    "max": max(vals),
                    "outlier_count_iqr": len([v for v in vals if v < low or v > high]),
                }
        return {"file": str(path), "row_count": len(rows), "columns": cols, "numeric_summary": numeric}
