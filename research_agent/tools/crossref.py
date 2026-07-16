from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Any

from research_agent.config import AgentConfig
from research_agent.version import RUNTIME_VERSION


class CrossrefClient:
    """Search and resolve metadata through Crossref's public works endpoint."""

    def __init__(self, config: AgentConfig):
        self.config = config

    def search(
        self,
        query: str,
        *,
        year_from: int | None = None,
        year_to: int | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {
            "query.bibliographic": query,
            "rows": str(min(max(1, limit), 100)),
            "select": "DOI,title,author,issued,container-title,URL,abstract,is-referenced-by-count,publisher,volume,issue,page",
        }
        filters = []
        if year_from:
            filters.append(f"from-pub-date:{year_from}-01-01")
        if year_to:
            filters.append(f"until-pub-date:{year_to}-12-31")
        if filters:
            params["filter"] = ",".join(filters)
        if self.config.openalex_mailto:
            params["mailto"] = self.config.openalex_mailto
        url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers=self._headers())
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        message = payload.get("message") if isinstance(payload, dict) else {}
        items = message.get("items") if isinstance(message, dict) else []
        return [self._normalize(item) for item in items or [] if isinstance(item, dict)]

    def resolve(self, reference: dict[str, Any]) -> dict[str, Any] | None:
        doi = str(reference.get("doi") or "").strip()
        if not doi:
            return None
        encoded = urllib.parse.quote(doi, safe="")
        url = f"https://api.crossref.org/works/{encoded}"
        if self.config.openalex_mailto:
            url += "?" + urllib.parse.urlencode({"mailto": self.config.openalex_mailto})
        request = urllib.request.Request(url, headers=self._headers())
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        message = payload.get("message") if isinstance(payload, dict) else None
        if not isinstance(message, dict):
            return None
        normalized = self._normalize(message)
        normalized["doi"] = normalized.get("doi") or doi
        normalized.update({
            "metadata_source": "crossref",
            "metadata_url": f"https://api.crossref.org/works/{encoded}",
            "match_basis": "exact_doi",
        })
        return normalized

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": "ResearchAgent/%s (mailto:%s)" % (
            RUNTIME_VERSION,
            self.config.openalex_mailto or "not-configured",
        )}

    def _normalize(self, message: dict[str, Any]) -> dict[str, Any]:
        issued = (message.get("issued") or {}).get("date-parts") or []
        year = str(issued[0][0]) if issued and issued[0] else ""
        authors = []
        for author in message.get("author") or []:
            if not isinstance(author, dict):
                continue
            name = " ".join(str(author.get(key) or "").strip() for key in ("given", "family")).strip()
            if name:
                authors.append(name)
        titles = message.get("title") or []
        containers = message.get("container-title") or []
        abstract = re.sub(r"<[^>]+>", " ", str(message.get("abstract") or ""))
        abstract = re.sub(r"\s+", " ", abstract).strip()
        return {
            "title": str(titles[0]) if titles else "",
            "authors": authors,
            "year": year,
            "venue": str(containers[0]) if containers else "",
            "volume": str(message.get("volume") or ""),
            "issue": str(message.get("issue") or ""),
            "pages": str(message.get("page") or ""),
            "publisher": str(message.get("publisher") or ""),
            "doi": str(message.get("DOI") or ""),
            "url": str(message.get("URL") or ""),
            "abstract": abstract,
            "citation_count": int(message.get("is-referenced-by-count") or 0),
            "open_access_url": "",
            "source": "crossref",
            "raw_metadata": message,
        }
