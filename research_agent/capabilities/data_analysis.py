from __future__ import annotations

import csv
import json
import math
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


class ExperimentAnalysisService:
    def __init__(self, session_dir: Path):
        self.session_dir = session_dir

    def analyze(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raw_path = str(arguments.get("path") or "").strip()
        if not raw_path:
            raise ValueError('请提供数据文件路径，例如：分析数据 "D:\\data\\experiment.xlsx"')
        path = Path(raw_path).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Data file not found: {path}")
        rows = self._load(path)
        if not rows:
            raise ValueError("Data file contains no rows")
        columns = list(rows[0])
        id_like = [column for column in columns if self._id_like(column)]
        missing = {column: sum(self._blank(row.get(column)) for row in rows) for column in columns}
        numeric = self._numeric_columns(rows, columns)
        summaries, outliers = self._summaries(numeric)
        trends = self._trends(numeric)
        groups = self._groups(rows, columns, numeric)
        charts = self._charts(summaries, trends, groups)
        payload = {
            "file": str(path),
            "row_count": len(rows),
            "columns": columns,
            "id_like_columns": id_like,
            "missing_values": missing,
            "numeric_summary": summaries,
            "outliers": outliers,
            "trends": trends,
            "group_comparisons": groups,
            "visualization_recommendations": charts,
            "assumptions": [
                "IQR outliers are exploratory flags and are not removed automatically.",
                "ID-like columns are treated as identifiers, not continuous variables.",
            ],
        }
        summary_path = self.session_dir / "analysis_summary.json"
        report_path = self.session_dir / "analysis_report.md"
        outlier_path = self.session_dir / "outlier_flags.csv"
        summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        report_path.write_text(self._report(payload), encoding="utf-8")
        with outlier_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=["row", "column", "value", "lower_bound", "upper_bound"])
            writer.writeheader()
            writer.writerows(outliers)
        message = [f"已分析 {path.name}：{len(rows)} 行，{len(columns)} 列，{len(summaries)} 个数值列。"]
        message.append(f"缺失值共 {sum(missing.values())} 个，IQR 异常标记 {len(outliers)} 个。")
        for column, trend in list(trends.items())[:4]:
            message.append(f"- {column}: {trend['direction']}，斜率 {trend['slope']:.4g}")
        message.append(f"报告：{report_path}")
        return {
            "message": "\n".join(message),
            "artifacts": {
                "analysis_summary": str(summary_path),
                "analysis_report": str(report_path),
                "outlier_flags": str(outlier_path),
            },
            "data": payload,
        }

    def _load(self, path: Path) -> list[dict[str, Any]]:
        suffix = path.suffix.lower()
        if suffix in {".xlsx", ".xlsm"}:
            try:
                from openpyxl import load_workbook
            except ImportError as exc:
                raise RuntimeError("XLSX support requires openpyxl") from exc
            book = load_workbook(path, read_only=True, data_only=True)
            sheet = book.active
            values = list(sheet.iter_rows(values_only=True))
            if not values:
                return []
            headers = [str(value or f"column_{index + 1}") for index, value in enumerate(values[0])]
            return [dict(zip(headers, row)) for row in values[1:] if any(value is not None for value in row)]
        if suffix not in {".csv", ".tsv", ".txt"}:
            raise ValueError(f"Unsupported data format: {suffix}")
        sample = path.read_text(encoding="utf-8-sig", errors="ignore")[:4096]
        delimiter = "\t" if suffix == ".tsv" else ","
        if suffix == ".txt":
            try:
                delimiter = csv.Sniffer().sniff(sample, delimiters=",\t;|").delimiter
            except csv.Error:
                delimiter = "\t" if "\t" in sample else ","
        with path.open(newline="", encoding="utf-8-sig", errors="ignore") as handle:
            return list(csv.DictReader(handle, delimiter=delimiter))

    def _numeric_columns(self, rows: list[dict[str, Any]], columns: list[str]) -> dict[str, list[tuple[int, float]]]:
        numeric: dict[str, list[tuple[int, float]]] = {}
        for column in columns:
            if self._id_like(column):
                continue
            values = []
            for index, row in enumerate(rows, 1):
                value = self._number(row.get(column))
                if value is not None:
                    values.append((index, value))
            nonblank = len(rows) - sum(self._blank(row.get(column)) for row in rows)
            if len(values) >= 2 and len(values) >= max(2, math.ceil(nonblank * 0.7)):
                numeric[column] = values
        return numeric

    def _summaries(self, numeric: dict[str, list[tuple[int, float]]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        summaries: dict[str, Any] = {}
        flags: list[dict[str, Any]] = []
        for column, indexed in numeric.items():
            values = [value for _, value in indexed]
            q1, q3 = self._quantile(values, 0.25), self._quantile(values, 0.75)
            iqr = q3 - q1
            lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            for row, value in indexed:
                if value < lower or value > upper:
                    flags.append({"row": row, "column": column, "value": value, "lower_bound": lower, "upper_bound": upper})
            summaries[column] = {
                "count": len(values),
                "mean": statistics.mean(values),
                "median": statistics.median(values),
                "stdev": statistics.stdev(values) if len(values) > 1 else 0,
                "min": min(values),
                "q1": q1,
                "q3": q3,
                "max": max(values),
                "outlier_count_iqr": sum(1 for value in values if value < lower or value > upper),
            }
        return summaries, flags

    def _trends(self, numeric: dict[str, list[tuple[int, float]]]) -> dict[str, Any]:
        trends = {}
        for column, indexed in numeric.items():
            if len(indexed) < 3:
                continue
            x = [float(row) for row, _ in indexed]
            y = [value for _, value in indexed]
            x_mean, y_mean = statistics.mean(x), statistics.mean(y)
            denominator = sum((value - x_mean) ** 2 for value in x)
            slope = 0.0 if denominator == 0 else sum((a - x_mean) * (b - y_mean) for a, b in zip(x, y)) / denominator
            scale = max(y) - min(y)
            normalized = 0.0 if scale == 0 else slope * max(1, len(y) - 1) / scale
            direction = "increasing" if normalized > 0.1 else "decreasing" if normalized < -0.1 else "stable"
            trends[column] = {"slope": slope, "normalized_change": normalized, "direction": direction}
        return trends

    def _groups(
        self,
        rows: list[dict[str, Any]],
        columns: list[str],
        numeric: dict[str, list[tuple[int, float]]],
    ) -> dict[str, Any]:
        categorical = None
        for column in columns:
            if column in numeric:
                continue
            values = {str(row.get(column)).strip() for row in rows if not self._blank(row.get(column))}
            if 1 < len(values) <= min(20, max(2, len(rows) // 2)):
                categorical = column
                break
        if not categorical:
            return {}
        result: dict[str, Any] = {"group_column": categorical, "means": {}}
        for numeric_column in list(numeric)[:8]:
            grouped: dict[str, list[float]] = defaultdict(list)
            for row in rows:
                group = str(row.get(categorical) or "").strip()
                value = self._number(row.get(numeric_column))
                if group and value is not None:
                    grouped[group].append(value)
            result["means"][numeric_column] = {
                group: {"count": len(values), "mean": statistics.mean(values)} for group, values in grouped.items()
            }
        return result

    def _charts(self, summaries: dict[str, Any], trends: dict[str, Any], groups: dict[str, Any]) -> list[str]:
        charts = []
        if summaries:
            charts.append("Use box plots for numeric distributions and IQR outlier review.")
        if trends:
            charts.append("Use line charts for ordered measurements, epochs, steps, or time points.")
        if groups:
            charts.append(f"Use grouped bars or point-range plots by `{groups['group_column']}`.")
        if len(summaries) >= 2:
            charts.append("Use a scatter plot or correlation heatmap for relationships between numeric variables.")
        return charts

    def _report(self, payload: dict[str, Any]) -> str:
        lines = [
            "# Experiment Data Analysis",
            "",
            f"File: `{payload['file']}`",
            f"Rows: {payload['row_count']}",
            "",
        ]
        if payload.get("id_like_columns"):
            lines.extend(["## Identifier-like Columns", ""])
            lines.extend(f"- `{column}`" for column in payload["id_like_columns"])
            lines.extend([""])
        lines.extend(["## Numeric Summary", ""])
        for column, item in payload["numeric_summary"].items():
            lines.append(
                f"- `{column}`: mean={item['mean']:.6g}, median={item['median']:.6g}, "
                f"sd={item['stdev']:.6g}, range=[{item['min']:.6g}, {item['max']:.6g}], "
                f"IQR outliers={item['outlier_count_iqr']}"
            )
        lines.extend(["", "## Missing Values", ""])
        lines.extend(f"- `{column}`: {count}" for column, count in payload["missing_values"].items())
        lines.extend(["", "## Trends", ""])
        lines.extend(
            f"- `{column}`: {item['direction']} (slope={item['slope']:.6g})" for column, item in payload["trends"].items()
        )
        lines.extend(["", "## Visualization Recommendations", ""])
        lines.extend(f"- {item}" for item in payload["visualization_recommendations"])
        return "\n".join(lines) + "\n"

    def _quantile(self, values: list[float], fraction: float) -> float:
        ordered = sorted(values)
        position = (len(ordered) - 1) * fraction
        low, high = math.floor(position), math.ceil(position)
        if low == high:
            return ordered[low]
        return ordered[low] * (high - position) + ordered[high] * (position - low)

    def _number(self, value: Any) -> float | None:
        try:
            return None if self._blank(value) else float(value)
        except (TypeError, ValueError):
            return None

    def _blank(self, value: Any) -> bool:
        return value is None or str(value).strip() == ""

    def _id_like(self, column: str) -> bool:
        return bool(re.search(r"(^id$|subject|subj|被试|编号|trial|epoch|样本号)", column, re.IGNORECASE))
