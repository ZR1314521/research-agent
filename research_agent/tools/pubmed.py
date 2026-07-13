from __future__ import annotations

import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from research_agent.config import AgentConfig


class PubMedClient:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"

    def search(
        self,
        query: str,
        *,
        year_from: int | None = None,
        year_to: int | None = None,
        limit: int = 20,
    ) -> list[dict]:
        term = query
        if year_from or year_to:
            term += f" AND {year_from or 1800}:{year_to or 3000}[pdat]"
        params = self._identity(
            {"db": "pubmed", "term": term, "retmode": "json", "retmax": str(min(limit, 50))}
        )
        url = self.base + "esearch.fcgi?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=30) as response:
            ids = json.loads(response.read().decode("utf-8")).get("esearchresult", {}).get("idlist", [])
        return self._fetch(ids) if ids else []

    def _fetch(self, ids: list[str]) -> list[dict]:
        params = self._identity({"db": "pubmed", "id": ",".join(ids), "retmode": "xml"})
        url = self.base + "efetch.fcgi?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=30) as response:
            root = ET.fromstring(response.read())
        return [self._normalize(article) for article in root.findall(".//PubmedArticle")]

    def _identity(self, params: dict[str, str]) -> dict[str, str]:
        if self.config.pubmed_email:
            params["email"] = self.config.pubmed_email
        if self.config.pubmed_api_key:
            params["api_key"] = self.config.pubmed_api_key
        return params

    def _normalize(self, article: ET.Element) -> dict:
        citation = article.find(".//MedlineCitation")
        article_node = citation.find("Article") if citation is not None else None
        pmid = self._text(citation.find("PMID")) if citation is not None else ""
        title = self._text(article_node.find("ArticleTitle")) if article_node is not None else ""
        abstract = " ".join(
            self._text(node) for node in article.findall(".//Abstract/AbstractText") if self._text(node)
        )
        authors = []
        for author in article.findall(".//AuthorList/Author"):
            collective = self._text(author.find("CollectiveName"))
            name = " ".join(
                part for part in (self._text(author.find("ForeName")), self._text(author.find("LastName"))) if part
            )
            if collective or name:
                authors.append(collective or name)
        journal = self._text(article.find(".//Journal/Title"))
        year = self._year(article)
        doi = ""
        for item in article.findall(".//ArticleId"):
            if item.attrib.get("IdType") == "doi":
                doi = self._text(item)
                break
        return {
            "title": title,
            "authors": authors,
            "year": year,
            "venue": journal,
            "abstract": abstract,
            "doi": doi,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
            "citation_count": 0,
            "open_access_url": "",
            "source": "pubmed",
            "raw_metadata": {"pmid": pmid},
        }

    def _year(self, article: ET.Element) -> int | str:
        for path in (".//JournalIssue/PubDate/Year", ".//ArticleDate/Year", ".//DateCompleted/Year"):
            value = self._text(article.find(path))
            if value.isdigit():
                return int(value)
        medline = self._text(article.find(".//JournalIssue/PubDate/MedlineDate"))
        return int(medline[:4]) if len(medline) >= 4 and medline[:4].isdigit() else ""

    def _text(self, node: ET.Element | None) -> str:
        return "" if node is None else "".join(node.itertext()).strip()
