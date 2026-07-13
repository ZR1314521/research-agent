#!/usr/bin/env python3
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "demo_runs" / "demo"


def run(args: list[str], cwd: Path = ROOT) -> None:
    print("+", " ".join(args))
    subprocess.run(args, cwd=cwd, check=True)


def main() -> None:
    if RUN.exists():
        shutil.rmtree(RUN)
    RUN.mkdir(parents=True)
    py = sys.executable
    run([py, "scripts/prepare_uploads.py", "demo_data/data.csv", "demo_data/refs.json", "demo_data/papers.json", "--run-dir", str(RUN), "--copy"])
    run([py, "scripts/recursive_search.py", "demo_data/papers.json", "--topic", "AI research agent literature review automation", "--keywords", "agent workflow RAG screening", "--venues", "IEEE,Nature", "--year-from", "2022", "--rounds", "3", "--out-dir", str(RUN)])
    run([py, "scripts/build_rag_index.py", "rules", str(RUN / "screened_papers.json"), "--out-dir", str(RUN / "rag_index")])
    run([py, "scripts/query_rag.py", "--index-dir", str(RUN / "rag_index"), "--query", "Nature IEEE GB/T 7714 reference rules for research agent demo", "--out", str(RUN / "rag_answer.md")])
    run([py, "scripts/format_references_strict.py", "demo_data/refs.json", "--profiles", "rules/style_profiles.json", "--style", "gbt7714-numeric", "--style", "ieee", "--style", "nature", "--style", "science", "--style", "cell", "--style", "elsevier-vancouver", "--style", "apa", "--out-dir", str(RUN)])
    print(RUN)


if __name__ == "__main__":
    main()
