from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from research_agent.platform_store import PlatformStore


def _number(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


class UsageService:
    def __init__(self, runs_dir: Path, store: PlatformStore):
        self.runs_dir = Path(runs_dir)
        self.store = store

    def _paths(self) -> list[Path]:
        root = self.runs_dir / "sessions"
        return list(root.glob("*/provider_calls.jsonl")) if root.exists() else []

    def records(self) -> tuple[list[dict[str, Any]], int]:
        records: list[dict[str, Any]] = []
        damaged = 0
        prices = dict(self.store.get_setting("model_prices", {}) or {})
        for path in self._paths():
            run_id = path.parent.name
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    damaged += 1
                    continue
                usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
                input_tokens = _number(usage.get("prompt_tokens", usage.get("input_tokens")))
                output_tokens = _number(usage.get("completion_tokens", usage.get("output_tokens")))
                total_tokens = _number(usage.get("total_tokens")) or input_tokens + output_tokens
                details = usage.get("prompt_tokens_details") if isinstance(usage.get("prompt_tokens_details"), dict) else {}
                cached_tokens = _number(usage.get("prompt_cache_hit_tokens")) or _number(details.get("cached_tokens"))
                started = float(raw.get("started_at") or 0)
                moment = datetime.fromtimestamp(started).astimezone() if started > 0 else None
                model = str(raw.get("model") or "unknown")
                price = prices.get(model) if isinstance(prices.get(model), dict) else {}
                cost = None
                if price and "input_per_million" in price and "output_per_million" in price:
                    cost = round(
                        input_tokens / 1_000_000 * float(price["input_per_million"])
                        + output_tokens / 1_000_000 * float(price["output_per_million"]),
                        8,
                    )
                records.append({
                    "call_id": str(raw.get("call_id") or ""),
                    "run_id": run_id,
                    "turn_id": str(raw.get("turn_id") or ""),
                    "time": moment.isoformat(timespec="seconds") if moment else "",
                    "provider": str(raw.get("provider") or "unknown"),
                    "model": model,
                    "operation": str(raw.get("operation") or ""),
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "cached_tokens": cached_tokens,
                    "duration_ms": _number(raw.get("duration_ms")),
                    "status": str(raw.get("status") or "unknown"),
                    "cost": cost,
                    "priced": cost is not None,
                    "source": "provider_calls",
                })
        records.sort(key=lambda item: item["time"], reverse=True)
        return records, damaged

    @staticmethod
    def _filter(
        records: list[dict[str, Any]],
        provider: str = "",
        model: str = "",
        status: str = "",
        date_from: str = "",
        date_to: str = "",
    ) -> list[dict[str, Any]]:
        result = records
        if provider:
            result = [item for item in result if item["provider"] == provider]
        if model:
            result = [item for item in result if item["model"] == model]
        if status:
            result = [item for item in result if item["status"] == status]
        if date_from:
            result = [item for item in result if item["time"] and item["time"][:10] >= date_from]
        if date_to:
            result = [item for item in result if item["time"] and item["time"][:10] <= date_to]
        return result

    def report(
        self,
        *,
        provider: str = "",
        model: str = "",
        status: str = "",
        date_from: str = "",
        date_to: str = "",
        limit: int = 200,
    ) -> dict[str, Any]:
        all_records, damaged = self.records()
        records = self._filter(all_records, provider, model, status, date_from, date_to)
        total_input = sum(item["input_tokens"] for item in records)
        total_output = sum(item["output_tokens"] for item in records)
        total_tokens = sum(item["total_tokens"] for item in records)
        total_cached = sum(item["cached_tokens"] for item in records)
        completed = sum(item["status"] == "completed" for item in records)
        priced_costs = [item["cost"] for item in records if item["priced"]]
        providers: dict[str, dict[str, Any]] = defaultdict(lambda: {"requests": 0, "tokens": 0, "duration_ms": 0})
        models: dict[str, dict[str, Any]] = defaultdict(lambda: {"requests": 0, "tokens": 0, "duration_ms": 0})
        trend: dict[str, dict[str, Any]] = defaultdict(lambda: {"input": 0, "output": 0, "cached": 0, "requests": 0, "cost": 0.0})
        for item in records:
            for target, key in ((providers, item["provider"]), (models, item["model"])):
                target[key]["requests"] += 1
                target[key]["tokens"] += item["total_tokens"]
                target[key]["duration_ms"] += item["duration_ms"]
            bucket = item["time"][:13] + ":00" if item["time"] else "未知"
            trend[bucket]["input"] += item["input_tokens"]
            trend[bucket]["output"] += item["output_tokens"]
            trend[bucket]["cached"] += item["cached_tokens"]
            trend[bucket]["requests"] += 1
            trend[bucket]["cost"] += item["cost"] or 0
        return {
            "summary": {
                "requests": len(records),
                "input_tokens": total_input,
                "output_tokens": total_output,
                "total_tokens": total_tokens,
                "cached_tokens": total_cached,
                "cache_hit_rate": round(total_cached / total_input * 100, 1) if total_input else 0,
                "duration_ms": sum(item["duration_ms"] for item in records),
                "success_rate": round(completed / len(records) * 100, 1) if records else 0,
                "cost": round(sum(priced_costs), 8) if priced_costs and len(priced_costs) == len(records) else None,
                "priced_requests": len(priced_costs),
                "damaged_records": damaged,
            },
            "trend": [{"time": key, **trend[key]} for key in sorted(trend)],
            "providers": [{"name": key, **value} for key, value in sorted(providers.items())],
            "models": [{"name": key, **value} for key, value in sorted(models.items())],
            "records": records[:max(1, min(500, int(limit)))],
            "filters": {
                "providers": sorted({item["provider"] for item in all_records}),
                "models": sorted({item["model"] for item in all_records}),
                "statuses": sorted({item["status"] for item in all_records}),
            },
        }

    def clear(self) -> int:
        cleared = 0
        for path in self._paths():
            path.write_text("", encoding="utf-8")
            cleared += 1
        return cleared

    def prune(self, days: int) -> int:
        cutoff = datetime.now().astimezone() - timedelta(days=max(1, int(days)))
        removed = 0
        for path in self._paths():
            kept: list[str] = []
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                try:
                    item = json.loads(line)
                    started = datetime.fromtimestamp(float(item.get("started_at") or 0)).astimezone()
                    if started >= cutoff:
                        kept.append(line)
                    else:
                        removed += 1
                except Exception:
                    kept.append(line)
            path.write_text(("\n".join(kept) + "\n") if kept else "", encoding="utf-8")
        return removed
