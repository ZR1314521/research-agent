from __future__ import annotations

import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


class ArxivClient:
    def search(
        self,
        query: str,
        *,
        year_from: int | None = None,
        year_to: int | None = None,
        limit: int = 20,
    ) -> list[dict]:
        params = {
            "search_query": "all:" + query,
            "start": "0",
            "max_results": str(min(limit, 50)),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=30) as response:
            root = ET.fromstring(response.read())
        ns = {"a": "http://www.w3.org/2005/Atom"}
        papers = []
        for entry in root.findall("a:entry", ns):
            published = entry.findtext("a:published", default="", namespaces=ns)
            year = int(published[:4]) if re.match(r"\d{4}", published) else ""
            if year_from and year and year < year_from:
                continue
            if year_to and year and year > year_to:
                continue
            papers.append(
                {
                    "title": (entry.findtext("a:title", default="", namespaces=ns) or "").strip(),
                    "authors": [
                        (author.findtext("a:name", default="", namespaces=ns) or "").strip()
                        for author in entry.findall("a:author", ns)
                    ],
                    "year": year,
                    "venue": "arXiv",
                    "abstract": (entry.findtext("a:summary", default="", namespaces=ns) or "").strip(),
                    "doi": "",
                    "url": entry.findtext("a:id", default="", namespaces=ns),
                    "citation_count": 0,
                    "open_access_url": next(
                        (
                            link.attrib.get("href", "")
                            for link in entry.findall("a:link", ns)
                            if link.attrib.get("title") == "pdf"
                        ),
                        "",
                    ),
                    "source": "arxiv",
                    "raw_metadata": {"published": published},
                }
            )
        return papers
