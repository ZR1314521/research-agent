from __future__ import annotations

import json
import urllib.parse
import urllib.request

from research_agent.config import AgentConfig


class SemanticScholarClient:
    def __init__(self, config: AgentConfig):
        self.config = config

    def search(
        self,
        query: str,
        *,
        year_from: int | None = None,
        year_to: int | None = None,
        limit: int = 20,
    ) -> list[dict]:
        params = {
            "query": query,
            "limit": str(min(limit, 50)),
            "fields": "title,authors,year,venue,abstract,externalIds,url,citationCount,openAccessPdf",
        }
        if year_from or year_to:
            params["year"] = f"{year_from or ''}-{year_to or ''}"
        url = "https://api.semanticscholar.org/graph/v1/paper/search?" + urllib.parse.urlencode(params)
        headers = {}
        if self.config.semantic_scholar_api_key:
            headers["x-api-key"] = self.config.semantic_scholar_api_key
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
        return [self._normalize(item) for item in data.get("data", [])]

    def _normalize(self, item: dict) -> dict:
        external = item.get("externalIds") or {}
        return {
            "title": item.get("title") or "",
            "authors": [a.get("name", "") for a in item.get("authors", []) if a.get("name")],
            "year": item.get("year") or "",
            "venue": item.get("venue") or "",
            "abstract": item.get("abstract") or "",
            "doi": external.get("DOI") or "",
            "url": item.get("url") or "",
            "citation_count": item.get("citationCount") or 0,
            "open_access_url": (item.get("openAccessPdf") or {}).get("url") or "",
            "source": "semantic_scholar",
            "raw_metadata": item,
        }
