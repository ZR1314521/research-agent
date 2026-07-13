from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any


OPENCLI_SITES = ["brave", "duckduckgo", "google"]


def _opencli_path() -> str | None:
    path = shutil.which("opencli")
    if path:
        return path
    cand = r"C:\Users\Z18803231258\AppData\Roaming\npm\opencli.CMD"
    return cand if shutil.which(cand) else None


class WebSearchService:
    """General web search via opencli. Requires Chrome with opencli bridge extension."""

    def search(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query", "")).strip()
        if not query:
            raise ValueError("web_search requires a query")
        limit = int(arguments.get("limit") or 5)
        site = str(arguments.get("site") or "").strip().lower()

        cli = _opencli_path()
        if not cli:
            raise RuntimeError("opencli not found. Install it first: npm i -g @anthropic-ai/opencli")

        candidates = [site] if site and site in OPENCLI_SITES else OPENCLI_SITES
        errors = []
        for source in candidates:
            try:
                proc = subprocess.run(
                    [cli, source, "search", query, "-f", "json"],
                    capture_output=True, timeout=60, encoding="utf-8", errors="replace",
                )
                if proc.returncode != 0:
                    errors.append(f"{source}: {proc.stderr.strip()[:120]}")
                    continue
                data = json.loads(proc.stdout) if proc.stdout.strip() else {}
                items = self._parse(data, limit)
                if not items:
                    errors.append(f"{source}: empty results")
                    continue
                return self._result(items, source, query)
            except subprocess.TimeoutExpired:
                errors.append(f"{source}: timeout")
            except (json.JSONDecodeError, OSError) as exc:
                errors.append(f"{source}: {exc}")
        raise RuntimeError(f"All search sources failed: {'; '.join(errors)}")

    def _parse(self, data: Any, limit: int) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        candidates = data if isinstance(data, list) else data.get("results") or data.get("items") or []
        for item in candidates:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("name") or "")
            url = str(item.get("url") or item.get("link") or item.get("href") or "")
            snippet = str(item.get("snippet") or item.get("description") or item.get("summary") or "")
            if title and url:
                items.append({"title": title, "url": url, "snippet": snippet})
            if len(items) >= limit:
                break
        return items

    def _result(self, items: list[dict[str, str]], source: str, query: str) -> dict[str, Any]:
        lines = [f"web search '{query}' via {source} - {len(items)} results:"]
        for i, item in enumerate(items, 1):
            lines.append(f"\n{i}. {item['title']}\n   {item['url']}")
            if item["snippet"]:
                lines.append(f"   {item['snippet'][:200]}")
        return {
            "message": "\n".join(lines),
            "artifacts": {},
            "data": {"results": items, "source": source, "query": query},
        }
