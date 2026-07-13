#!/usr/bin/env python3
import argparse
import json
import re
import time
from collections import Counter
from pathlib import Path


def terms(text: str) -> list[str]:
    return re.findall(r"[\w\-]{2,}", text.lower())


def main() -> None:
    parser = argparse.ArgumentParser(description="Query the local lexical RAG index and write retrieval logs.")
    parser.add_argument("--index-dir", default="rag_index")
    parser.add_argument("--query", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--out", default="rag_answer.md")
    args = parser.parse_args()

    index_dir = Path(args.index_dir)
    chunks = {}
    with (index_dir / "chunks.jsonl").open(encoding="utf-8") as f:
        for line in f:
            item = json.loads(line)
            chunks[item["id"]] = item
    inverted = json.loads((index_dir / "inverted_index.json").read_text(encoding="utf-8"))

    scores = Counter()
    q_terms = terms(args.query)
    for term in q_terms:
        for chunk_id in inverted.get(term, []):
            scores[chunk_id] += 1
    ranked = [
        {
            "chunk_id": chunk_id,
            "score": score,
            "source": chunks[chunk_id]["source"],
            "text": chunks[chunk_id]["text"][:700],
        }
        for chunk_id, score in scores.most_common(args.top_k)
    ]

    log_item = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "query": args.query, "top_k": args.top_k, "results": ranked}
    with (index_dir / "retrieval_log.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(log_item, ensure_ascii=False) + "\n")

    lines = ["# RAG Retrieval Answer Draft", "", f"Query: {args.query}", "", "## Retrieved Evidence"]
    for i, item in enumerate(ranked, 1):
        lines.append(f"{i}. `{item['source']}` score={item['score']}")
        lines.append("")
        lines.append(item["text"])
        lines.append("")
    lines.append("## Draft")
    lines.append("Use the retrieved evidence above to ground the final answer. This demo script does not call a model.")
    Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(args.out)


if __name__ == "__main__":
    main()
