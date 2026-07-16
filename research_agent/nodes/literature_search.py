from __future__ import annotations

import json
from pathlib import Path

from research_agent.nodes.base import BaseNode
from research_agent.state import RunState
from research_agent.tools.arxiv import ArxivClient
from research_agent.tools.openalex import OpenAlexClient
from research_agent.tools.pubmed import PubMedClient
from research_agent.tools.semantic_scholar import SemanticScholarClient


class LiteratureSearchNode(BaseNode):
    name = "literature_search"

    def __init__(self, config, run_dir: Path, sources: list[str] | None = None, limit: int = 20):
        super().__init__(config, run_dir)
        self.sources = list(dict.fromkeys(sources or []))
        self.limit = limit

    def run(self, state: RunState) -> RunState:
        state.mark_running(self.name)
        query = " ".join(x for x in [state.topic, state.keywords] if x).strip()
        clients = {
            "openalex": OpenAlexClient(self.config),
            "pubmed": PubMedClient(self.config),
            "semantic_scholar": SemanticScholarClient(self.config),
            "arxiv": ArxivClient(),
        }
        all_papers: list[dict] = []
        errors = []
        raw_dir = self.run_dir / "raw_search"
        raw_dir.mkdir(parents=True, exist_ok=True)
        for source in self.sources:
            client = clients.get(source)
            if not client:
                continue
            try:
                papers = client.search(query, year_from=state.year_from, limit=self.limit)
                (raw_dir / f"{source}.json").write_text(json.dumps(papers, ensure_ascii=False, indent=2), encoding="utf-8")
                all_papers.extend(papers)
            except Exception as exc:
                errors.append({"source": source, "error": str(exc)})
        if not all_papers:
            upload_manifest = state.artifacts.get("upload_manifest")
            if upload_manifest:
                manifest = json.loads(Path(upload_manifest).read_text(encoding="utf-8"))
                for item in manifest.get("files", []):
                    if item.get("category") in {"papers", "references", "structured"} and item.get("extension") == ".json":
                        try:
                            data = json.loads(Path(item["stored_path"]).read_text(encoding="utf-8-sig"))
                            candidates = data if isinstance(data, list) else data.get("papers", []) if isinstance(data, dict) else []
                            all_papers.extend(item for item in candidates if isinstance(item, dict))
                        except Exception as exc:
                            errors.append({"source": item.get("filename"), "error": str(exc)})
        if not self.sources and not all_papers:
            raise ValueError("旧工作流未收到明确的文献来源，也没有可用的上传文献")
        papers_path = self.run_dir / "papers_raw.json"
        papers_path.write_text(json.dumps(all_papers, ensure_ascii=False, indent=2), encoding="utf-8")
        if errors:
            (self.run_dir / "literature_search_errors.json").write_text(json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8")
            state.add_artifact("literature_search_errors", self.run_dir / "literature_search_errors.json")
        state.add_artifact("raw_papers", papers_path)
        state.mark_completed(self.name, f"Collected {len(all_papers)} paper candidate(s)")
        return state
