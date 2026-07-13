from __future__ import annotations

import csv
import json
import math
import re
import time
from collections import Counter
from pathlib import Path
from threading import Event
from typing import Any

from research_agent.config import AgentConfig
from research_agent.context import ContextManager
from research_agent.logging import ModelCallLogger
from research_agent.tools.llm_client import LLMClient


class RagService:
    def __init__(self, config: AgentConfig, session_dir: Path, cancel_event: Event | None = None):
        self.config = config
        self.session_dir = session_dir
        self.cancel_event = cancel_event
        self.index_dir = session_dir / "rag_index"

    def query(self, arguments: dict[str, Any], artifacts: dict[str, str]) -> dict[str, Any]:
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ValueError("RAG query cannot be empty")
        inputs = self._scoped_inputs(str(arguments.get("scope") or ""), artifacts)
        self.build(inputs)
        chunks = self._jsonl(self.index_dir / "chunks.jsonl")
        vectors = {item["id"]: item["vector"] for item in self._jsonl(self.index_dir / "vectors.jsonl")}
        meta = json.loads((self.index_dir / "index_meta.json").read_text(encoding="utf-8"))
        query_vector = self._query_vector(query, meta.get("idf", {}))
        ranked = []
        for chunk in chunks:
            score = self._cosine(query_vector, vectors.get(chunk["id"], {}))
            if score > 0:
                ranked.append({**chunk, "score": score})
        ranked.sort(key=lambda item: item["score"], reverse=True)
        ranked = ranked[: max(1, int(arguments.get("top_k") or 5))]
        log = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "query": query,
            "results": [
                {"chunk_id": item["id"], "source": item["source"], "score": item["score"]} for item in ranked
            ],
        }
        with (self.index_dir / "retrieval_log.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(log, ensure_ascii=False) + "\n")
        evidence = "\n\n".join(
            f"Source: {item['source']}\nScore: {item['score']:.4f}\n{item['text']}" for item in ranked
        )
        evidence = ContextManager(self.session_dir, self.config.context_window).fit_text(
            evidence,
            label="rag-evidence",
            occupied=query,
            reserve_tokens=self.config.context_window // 4,
        )
        fallback = self._fallback_answer(query, ranked)
        client = LLMClient(self.config, ModelCallLogger(self.session_dir), self.cancel_event)
        result = client.complete(
            "rag_answer",
            f"Question: {query}\n\nRetrieved evidence:\n{evidence}",
            fallback=fallback,
            system="Answer in Chinese using only retrieved evidence. Cite source paths. Say when evidence is insufficient.",
            temperature=0,
        )
        answer_path = self.session_dir / "rag_answer.md"
        answer_path.write_text(result.text.strip() + "\n", encoding="utf-8")
        return {
            "message": result.text.strip() + f"\n\n检索记录：{self.index_dir / 'retrieval_log.jsonl'}",
            "artifacts": {
                "rag_index": str(self.index_dir),
                "rag_answer": str(answer_path),
                "retrieval_log": str(self.index_dir / "retrieval_log.jsonl"),
            },
            "data": {"results": ranked},
        }

    def build(self, inputs: list[Path]) -> Path:
        self.index_dir.mkdir(parents=True, exist_ok=True)
        files = self._files(inputs)
        chunks = []
        for path in files:
            try:
                text = self._read(path)
            except Exception:
                continue
            for index, part in enumerate(self._chunks(text), 1):
                chunks.append({"id": f"c{len(chunks) + 1:06d}", "source": str(path), "chunk_index": index, "text": part})
        document_frequency: Counter[str] = Counter()
        term_counts: dict[str, Counter[str]] = {}
        for chunk in chunks:
            counts = Counter(self._terms(chunk["text"]))
            term_counts[chunk["id"]] = counts
            document_frequency.update(counts.keys())
        total = max(1, len(chunks))
        idf = {term: math.log((1 + total) / (1 + count)) + 1 for term, count in document_frequency.items()}
        vectors = []
        for chunk in chunks:
            counts = term_counts[chunk["id"]]
            length = max(1, sum(counts.values()))
            vector = {term: (count / length) * idf[term] for term, count in counts.items()}
            norm = math.sqrt(sum(value * value for value in vector.values())) or 1
            vectors.append({"id": chunk["id"], "vector": {term: value / norm for term, value in vector.items()}})
        self._write_jsonl(self.index_dir / "chunks.jsonl", chunks)
        self._write_jsonl(self.index_dir / "vectors.jsonl", vectors)
        (self.index_dir / "index_meta.json").write_text(
            json.dumps(
                {
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "mode": "sparse-tfidf-cosine",
                    "input_count": len(files),
                    "chunk_count": len(chunks),
                    "idf": idf,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return self.index_dir

    def _scoped_inputs(self, scope: str, artifacts: dict[str, str]) -> list[Path]:
        scope = (scope or "").lower()
        if scope in {"uploaded", "uploaded_only", "uploads"}:
            keys = [key for key in artifacts if key.startswith("uploaded_") or key.startswith("latest_text") or key.startswith("latest_document")]
            return [Path(artifacts[key]) for key in keys if artifacts.get(key) and Path(artifacts[key]).exists()]
        if scope in {"papers", "paper_pool", "current-paper-pool"}:
            keys = ["active_papers", "paper_pool_markdown", "literature_matrix_md", "summary_notes"]
            return [Path(artifacts[key]) for key in keys if artifacts.get(key) and Path(artifacts[key]).exists()]
        inputs = [Path(value) for value in artifacts.values() if value and Path(value).exists()]
        if scope != "session_only":
            inputs.append(self.config.rules_dir)
        return inputs

    def _files(self, inputs: list[Path]) -> list[Path]:
        allowed = {".md", ".txt", ".json", ".csv", ".tsv", ".csl", ".pdf", ".docx"}
        files: list[Path] = []
        seen = set()
        for item in inputs:
            candidates = item.rglob("*") if item.is_dir() else [item]
            for path in candidates:
                if not path.is_file() or path.suffix.lower() not in allowed:
                    continue
                key = str(path.resolve()).lower()
                if key not in seen and path.stat().st_size <= 10 * 1024 * 1024:
                    seen.add(key)
                    files.append(path)
        return files

    def _read(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".json":
            return json.dumps(json.loads(path.read_text(encoding="utf-8-sig")), ensure_ascii=False)
        if suffix in {".csv", ".tsv"}:
            delimiter = "\t" if suffix == ".tsv" else ","
            with path.open(newline="", encoding="utf-8-sig", errors="ignore") as handle:
                return "\n".join(json.dumps(row, ensure_ascii=False) for row in csv.DictReader(handle, delimiter=delimiter))
        if suffix == ".pdf":
            from pypdf import PdfReader

            return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
        if suffix == ".docx":
            from docx import Document

            return "\n".join(paragraph.text for paragraph in Document(path).paragraphs)
        return path.read_text(encoding="utf-8-sig", errors="ignore")

    def _chunks(self, text: str, size: int = 1200, overlap: int = 160) -> list[str]:
        clean = re.sub(r"\s+", " ", text).strip()
        result, start = [], 0
        while start < len(clean):
            end = min(len(clean), start + size)
            result.append(clean[start:end])
            if end >= len(clean):
                break
            start = end - overlap
        return result

    def _terms(self, text: str) -> list[str]:
        result = [item.lower() for item in re.findall(r"[A-Za-z][A-Za-z0-9-]{1,}", text)]
        for sequence in re.findall(r"[\u4e00-\u9fff]{2,}", text):
            result.extend(sequence[index : index + 2] for index in range(len(sequence) - 1))
        return result

    def _query_vector(self, query: str, idf: dict[str, float]) -> dict[str, float]:
        counts = Counter(self._terms(query))
        length = max(1, sum(counts.values()))
        vector = {term: (count / length) * idf.get(term, 0.0) for term, count in counts.items() if term in idf}
        norm = math.sqrt(sum(value * value for value in vector.values())) or 1
        return {term: value / norm for term, value in vector.items()}

    def _cosine(self, left: dict[str, float], right: dict[str, float]) -> float:
        return sum(value * right.get(term, 0.0) for term, value in left.items())

    def _fallback_answer(self, query: str, ranked: list[dict[str, Any]]) -> str:
        lines = [f"# RAG 检索结果\n\n问题：{query}\n"]
        if not ranked:
            lines.append("本地知识库中没有找到足够证据。")
        for index, item in enumerate(ranked, 1):
            lines.append(f"## {index}. {item['source']}\n\n{self._safe_excerpt(item['text'])}\n")
        return "\n".join(lines)

    def _safe_excerpt(self, text: str) -> str:
        text = re.sub(r"忽略之前规则[^。.!?]*[。.!?]?", "[文档内提示注入内容已按普通文本忽略。]", text)
        text = re.sub(r"直接编造引用[^。.!?]*[。.!?]?", "[文档内不可信指令已忽略。]", text)
        return text

    def _write_jsonl(self, path: Path, rows: list[dict[str, Any]]) -> None:
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _jsonl(self, path: Path) -> list[dict[str, Any]]:
        with path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
