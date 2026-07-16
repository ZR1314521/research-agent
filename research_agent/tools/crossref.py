from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from research_agent.config import AgentConfig
from research_agent.version import RUNTIME_VERSION


class CrossrefClient:
    """Resolve exact DOI metadata through Crossref's public works endpoint."""

    def __init__(self, config: AgentConfig):
        self.config = config

    def resolve(self, reference: dict[str, Any]) -> dict[str, Any] | None:
        doi = str(reference.get("doi") or "").strip()
        if not doi:
            return None
        encoded = urllib.parse.quote(doi, safe="")
        url = f"https://api.crossref.org/works/{encoded}"
        if self.config.openalex_mailto:
            url += "?" + urllib.parse.urlencode({"mailto": self.config.openalex_mailto})
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "ResearchAgent/%s (mailto:%s)" % (
                RUNTIME_VERSION,
                self.config.openalex_mailto or "not-configured",
            )},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        message = payload.get("message") if isinstance(payload, dict) else None
        if not isinstance(message, dict):
            return None
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
        links = message.get("URL") or ""
        return {
            "title": str(titles[0]) if titles else "",
            "authors": authors,
            "year": year,
            "venue": str(containers[0]) if containers else "",
            "volume": str(message.get("volume") or ""),
            "issue": str(message.get("issue") or ""),
            "pages": str(message.get("page") or ""),
            "publisher": str(message.get("publisher") or ""),
            "doi": str(message.get("DOI") or doi),
            "url": str(links),
            "metadata_source": "crossref",
            "metadata_url": f"https://api.crossref.org/works/{encoded}",
            "match_basis": "exact_doi",
        }
