from __future__ import annotations

import json
import urllib.parse
import urllib.request

from research_agent.config import AgentConfig


class OpenAlexClient:
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
        params = {"search": query, "per-page": str(min(limit, 50))}
        filters = []
        if year_from:
            filters.append(f"from_publication_date:{year_from}-01-01")
        if year_to:
            filters.append(f"to_publication_date:{year_to}-12-31")
        if filters:
            params["filter"] = ",".join(filters)
        if self.config.openalex_mailto:
            params["mailto"] = self.config.openalex_mailto
        url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
        return [self._normalize(item) for item in data.get("results", [])]

    def _normalize(self, item: dict) -> dict:
        authors = [
            a.get("author", {}).get("display_name", "")
            for a in item.get("authorships", [])
            if a.get("author", {}).get("display_name")
        ]
        source = ((item.get("primary_location") or {}).get("source") or {})
        return {
            "title": item.get("title") or "",
            "authors": authors,
            "year": item.get("publication_year") or "",
            "venue": source.get("display_name", ""),
            "abstract": self._abstract(item.get("abstract_inverted_index") or {}),
            "doi": (item.get("doi") or "").replace("https://doi.org/", ""),
            "url": (item.get("primary_location") or {}).get("landing_page_url") or item.get("id") or "",
            "citation_count": item.get("cited_by_count") or 0,
            "open_access_url": ((item.get("open_access") or {}).get("oa_url") or ""),
            "source": "openalex",
            "raw_metadata": item,
        }

    def _abstract(self, inverted: dict) -> str:
        if not inverted:
            return ""
        positions = [(position, word) for word, indexes in inverted.items() for position in indexes]
        return " ".join(word for _, word in sorted(positions))
