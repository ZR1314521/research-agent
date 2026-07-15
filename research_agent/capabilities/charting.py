from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any


SUPPORTED_CHART_TYPES = {"line", "scatter", "bar", "histogram", "box", "heatmap"}
SUPPORTED_OUTPUT_FORMATS = {"png", "svg"}


class ChartService:
    """Render an explicit chart specification without interpreting user intent."""

    def __init__(self, session_dir: Path):
        self.session_dir = Path(session_dir)

    def render(self, arguments: dict[str, Any]) -> dict[str, Any]:
        source = self._source(arguments)
        chart_type = str(arguments.get("chart_type") or "").strip().lower()
        if chart_type not in SUPPORTED_CHART_TYPES:
            raise ValueError(
                f"Unsupported chart type: {chart_type or '(empty)'}. "
                f"Supported types: {', '.join(sorted(SUPPORTED_CHART_TYPES))}"
            )
        output_format = str(arguments.get("output_format") or "png").strip().lower()
        if output_format not in SUPPORTED_OUTPUT_FORMATS:
            raise ValueError(f"Unsupported chart output format: {output_format}")

        frame = self._load(source)
        x = str(arguments.get("x") or "").strip()
        y = [str(item).strip() for item in arguments.get("y") or [] if str(item).strip()]
        group = str(arguments.get("group") or "").strip()
        requested = list(dict.fromkeys([item for item in [x, *y, group] if item]))
        missing = [item for item in requested if item not in frame.columns]
        if missing:
            raise ValueError(f"Requested columns are missing: {', '.join(missing)}")
        if not y:
            raise ValueError("At least one y column is required")

        numeric = self._numeric(frame, y)
        if numeric.empty or all(numeric[column].dropna().empty for column in y):
            raise ValueError("Requested y columns contain no usable numeric values")

        pyplot = self._pyplot()
        figure, axis = pyplot.subplots(figsize=(9.6, 5.8), constrained_layout=True)
        warnings: list[str] = []
        self._draw(axis, frame, numeric, chart_type, x, y, group, warnings)
        axis.set_title(str(arguments.get("title") or ""))
        if arguments.get("x_label"):
            axis.set_xlabel(str(arguments["x_label"]))
        if arguments.get("y_label"):
            axis.set_ylabel(str(arguments["y_label"]))
        axis.grid(chart_type in {"line", "scatter", "bar"}, alpha=0.2)

        output_dir = self.session_dir / "artifacts" / "charts"
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / f"chart_{uuid.uuid4().hex[:12]}.{output_format}"
        figure.savefig(output, dpi=180 if output_format == "png" else None, format=output_format)
        pyplot.close(figure)
        if not output.exists() or output.stat().st_size == 0:
            raise RuntimeError("Chart renderer did not create a usable output file")

        artifact_key = f"chart_{output.stem.removeprefix('chart_')}"
        selected_columns = list(dict.fromkeys([item for item in [x, *y, group] if item]))
        data = {
            "path": str(output),
            "source": str(source),
            "chart_type": chart_type,
            "output_format": output_format,
            "columns": selected_columns,
            "warnings": warnings,
        }
        message = f"已生成 {chart_type} 图：{output}"
        if warnings:
            message += "\n注意：" + "；".join(warnings)
        return {"message": message, "artifacts": {artifact_key: str(output)}, "data": data}

    def _source(self, arguments: dict[str, Any]) -> Path:
        raw = str(arguments.get("path") or "").strip()
        if not raw:
            raise ValueError("Chart source path is required")
        source = Path(raw).expanduser().resolve()
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(f"Chart source file not found: {source}")
        return source

    def _load(self, source: Path):
        import pandas as pd

        suffix = source.suffix.lower()
        if suffix in {".xlsx", ".xlsm"}:
            frame = pd.read_excel(source)
        elif suffix in {".csv", ".tsv", ".txt"}:
            separator = "\t" if suffix == ".tsv" else None
            frame = pd.read_csv(source, sep=separator, engine="python" if separator is None else "c")
        else:
            raise ValueError(f"Unsupported chart data format: {suffix}")
        if frame.empty:
            raise ValueError("Chart source contains no data rows")
        frame.columns = [str(item) for item in frame.columns]
        return frame

    def _numeric(self, frame, columns: list[str]):
        import pandas as pd

        return frame[columns].apply(pd.to_numeric, errors="coerce")

    def _pyplot(self):
        import matplotlib

        matplotlib.use("Agg")
        from matplotlib import pyplot

        pyplot.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
        pyplot.rcParams["axes.unicode_minus"] = False
        return pyplot

    def _draw(
        self,
        axis: Any,
        frame: Any,
        numeric: Any,
        chart_type: str,
        x: str,
        y: list[str],
        group: str,
        warnings: list[str],
    ) -> None:
        x_values = frame[x] if x else frame.index
        dropped = sum(int(numeric[column].isna().sum()) for column in y)
        if dropped:
            warnings.append(f"{dropped} 个无法转换为数值的单元格未参与绘图")

        if chart_type == "heatmap":
            correlations = numeric.corr()
            image = axis.imshow(correlations, cmap="coolwarm", vmin=-1, vmax=1)
            axis.set_xticks(range(len(y)), labels=y, rotation=35, ha="right")
            axis.set_yticks(range(len(y)), labels=y)
            axis.figure.colorbar(image, ax=axis, label="Correlation")
            return
        if chart_type == "box":
            axis.boxplot([numeric[column].dropna() for column in y], tick_labels=y)
            return
        if chart_type == "histogram":
            for column in y:
                axis.hist(numeric[column].dropna(), bins="auto", alpha=0.55, label=column)
            if len(y) > 1:
                axis.legend()
            return
        if group:
            for group_value, indexes in frame.groupby(group, dropna=False).groups.items():
                for column in y:
                    values = numeric.loc[indexes, column]
                    xs = frame.loc[indexes, x] if x else indexes
                    self._draw_series(axis, chart_type, xs, values, f"{group_value} · {column}")
            axis.legend()
            return
        for column in y:
            self._draw_series(axis, chart_type, x_values, numeric[column], column)
        if len(y) > 1 or chart_type in {"line", "scatter"}:
            axis.legend()

    def _draw_series(self, axis: Any, chart_type: str, x_values: Any, y_values: Any, label: str) -> None:
        if chart_type == "line":
            axis.plot(x_values, y_values, marker="o", linewidth=1.8, label=label)
        elif chart_type == "scatter":
            axis.scatter(x_values, y_values, alpha=0.75, label=label)
        elif chart_type == "bar":
            axis.bar([str(item) for item in x_values], y_values, alpha=0.8, label=label)
        else:
            raise ValueError(f"Chart type {chart_type} cannot render series data")
