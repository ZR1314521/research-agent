#!/usr/bin/env python3
import argparse
import csv
import json
import re
import time
from collections import defaultdict
from pathlib import Path


def read_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return json.dumps(data, ensure_ascii=False, indent=2)
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        return "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    return path.read_text(encoding="utf-8-sig", errors="ignore")


def chunk_text(text: str, max_chars: int = 1200, overlap: int = 160) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = max(0, end - overlap)
    return chunks


def terms(text: str) -> set[str]:
    return set(re.findall(r"[\w\-]{2,}", text.lower()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a local lexical RAG index from public rules, papers, and extracted artifacts.")
    parser.add_argument("inputs", nargs="+", help="Files or directories to index.")
    parser.add_argument("--out-dir", default="rag_index")
    parser.add_argument("--max-chars", type=int, default=1200)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    for raw in args.inputs:
        p = Path(raw)
        if p.is_dir():
            files.extend(x for x in p.rglob("*") if x.is_file() and x.suffix.lower() in {".md", ".txt", ".json", ".csv", ".csl"})
        elif p.is_file():
            files.append(p)

    chunks = []
    inverted: dict[str, list[str]] = defaultdict(list)
    for file_path in files:
        try:
            text = read_text(file_path)
        except Exception as exc:
            chunks.append({"id": f"error-{len(chunks)+1}", "source": str(file_path), "text": "", "error": str(exc)})
            continue
        for idx, chunk in enumerate(chunk_text(text, args.max_chars), 1):
            chunk_id = f"c{len(chunks)+1:05d}"
            record = {"id": chunk_id, "source": str(file_path), "chunk_index": idx, "text": chunk}
            chunks.append(record)
            for term in terms(chunk):
                inverted[term].append(chunk_id)

    with (out_dir / "chunks.jsonl").open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    (out_dir / "inverted_index.json").write_text(json.dumps(inverted, ensure_ascii=False), encoding="utf-8")
    meta = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "input_count": len(files),
        "chunk_count": len(chunks),
        "mode": "lexical-demo-index",
        "note": "Replace with embeddings/Chroma/FAISS for production RAG.",
    }
    (out_dir / "index_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out_dir / "chunks.jsonl")


if __name__ == "__main__":
    main()
