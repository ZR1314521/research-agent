from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


def _opencli_path() -> str | None:
    path = shutil.which("opencli")
    if path:
        return path
    appdata = os.environ.get("APPDATA")
    candidate = Path(appdata) / "npm" / "opencli.CMD" if appdata else None
    return str(candidate) if candidate and candidate.exists() else None


class WebSearchService:
    """Search via any installed OpenCLI adapter.  The model selects the adapter
    at runtime after consulting ``opencli list`` (see the opencli-usage skill).
    """

    def search(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query", "")).strip()
        if not query:
            raise ValueError("opencli search requires a query")
        limit = int(arguments.get("limit") or 5)
        site = str(arguments.get("site") or "").strip().lower()
        if not site:
            raise ValueError("opencli search requires the model to select an adapter via site")

        cli = _opencli_path()
        if not cli:
            raise RuntimeError("opencli not found. Install it first: npm i -g @jackwener/opencli")

        try:
            proc = subprocess.run(
                [cli, site, "search", query, "-f", "json"],
                capture_output=True, timeout=60, encoding="utf-8", errors="replace",
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"OpenCLI adapter {site} timed out") from exc
        if proc.returncode != 0:
            raise RuntimeError(f"OpenCLI adapter {site} failed: {proc.stderr.strip()[:240]}")
        try:
            data = json.loads(proc.stdout) if proc.stdout.strip() else {}
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"OpenCLI adapter {site} returned invalid JSON") from exc
        items = self._parse(data, limit)
        if not items:
            return self._result([], site, query, outcome="empty")
        return self._result(items, site, query)

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

    def _result(self, items: list[dict[str, str]], source: str, query: str, *, outcome: str = "success") -> dict[str, Any]:
        lines = [f"web search '{query}' via {source} - {len(items)} results:"]
        for i, item in enumerate(items, 1):
            lines.append(f"\n{i}. {item['title']}\n   {item['url']}")
            if item["snippet"]:
                lines.append(f"   {item['snippet'][:200]}")
        return {
            "message": "\n".join(lines),
            "artifacts": {},
            "data": {"results": items, "source": source, "query": query},
            "outcome": outcome,
            "progress": {
                "summary": f"{source} 返回 {len(items)} 条网页结果" if items else f"{source} 未返回网页结果",
                "metrics": {"results": len(items)},
            },
        }


class _DuckDuckGoParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._anchor: dict[str, str] | None = None
        self._snippet = False
        self._snippet_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = set(str(values.get("class") or "").split())
        if tag == "a" and "result__a" in classes:
            self._anchor = {"title": "", "url": str(values.get("href") or ""), "snippet": ""}
        elif "result__snippet" in classes:
            self._snippet = True
            self._snippet_parts = []

    def handle_data(self, data: str) -> None:
        if self._anchor is not None:
            self._anchor["title"] += data
        if self._snippet:
            self._snippet_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._anchor is not None:
            self._anchor["title"] = " ".join(self._anchor["title"].split())
            if self._anchor["title"] and self._anchor["url"]:
                self.results.append(self._anchor)
            self._anchor = None
        if self._snippet and tag in {"a", "div", "span"}:
            snippet = " ".join("".join(self._snippet_parts).split())
            if snippet and self.results:
                self.results[-1]["snippet"] = snippet
            self._snippet = False


class HttpWebSearchService:
    """Direct HTTP search route. The caller selects the provider explicitly."""

    PROVIDERS = {"duckduckgo"}

    def search(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ValueError("web-search-http requires a query")
        provider = str(arguments.get("provider") or "").strip().lower()
        if not provider:
            raise ValueError("web-search-http requires the model to select a provider")
        if provider not in self.PROVIDERS:
            raise ValueError(f"Unsupported HTTP search provider: {provider}")
        limit = max(1, min(20, int(arguments.get("limit") or 5)))
        return self._duckduckgo(query, limit)

    def _duckduckgo(self, query: str, limit: int) -> dict[str, Any]:
        url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
        request = urllib.request.Request(url, headers={"User-Agent": "ResearchAgent/1.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            page = response.read().decode("utf-8", errors="replace")
        parser = _DuckDuckGoParser()
        parser.feed(page)
        items = []
        for item in parser.results[:limit]:
            link = item["url"]
            parsed = urllib.parse.urlparse(link)
            if "duckduckgo.com" in parsed.netloc:
                target = urllib.parse.parse_qs(parsed.query).get("uddg", [])
                if target:
                    link = target[0]
            items.append({**item, "url": link})
        return WebSearchService()._result(
            items,
            "duckduckgo-http",
            query,
            outcome="success" if items else "empty",
        )
