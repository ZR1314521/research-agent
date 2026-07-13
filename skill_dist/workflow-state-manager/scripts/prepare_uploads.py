#!/usr/bin/env python3
import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path


CATEGORY_BY_EXT = {
    ".csv": ("data", "experiment-data-analysis"),
    ".tsv": ("data", "experiment-data-analysis"),
    ".xlsx": ("data", "experiment-data-analysis"),
    ".xls": ("data", "experiment-data-analysis"),
    ".bib": ("references", "reference-format-gbt7714"),
    ".ris": ("references", "reference-format-gbt7714"),
    ".enw": ("references", "reference-format-gbt7714"),
    ".nbib": ("references", "reference-format-gbt7714"),
    ".json": ("structured", "auto-detect"),
    ".pdf": ("papers", "literature-matrix-extraction"),
    ".docx": ("papers", "docx"),
    ".md": ("text", "research-rag-index"),
    ".txt": ("text", "research-rag-index"),
    ".csl": ("rules", "reference-format-gbt7714"),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def classify(path: Path) -> tuple[str, str]:
    category, skill = CATEGORY_BY_EXT.get(path.suffix.lower(), ("unknown", "manual-review"))
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            keys = set(data.keys()) if isinstance(data, dict) else set()
            if {"references", "doi", "title"} & keys:
                return "references", "reference-format-gbt7714"
            if {"papers", "abstract", "venue"} & keys:
                return "papers", "literature-screening"
        except Exception:
            pass
    return category, skill


def main() -> None:
    parser = argparse.ArgumentParser(description="Register uploaded research files and write an upload manifest.")
    parser.add_argument("files", nargs="+", help="Files to register.")
    parser.add_argument("--run-dir", default="", help="Run directory. Defaults to runs/<timestamp>.")
    parser.add_argument("--copy", action="store_true", help="Copy files into <run-dir>/uploads.")
    args = parser.parse_args()

    run_dir = Path(args.run_dir) if args.run_dir else Path("runs") / time.strftime("%Y%m%d-%H%M%S")
    upload_dir = run_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    records = []
    for raw in args.files:
        src = Path(raw).resolve()
        if not src.exists():
            records.append({"source": raw, "status": "missing"})
            continue
        category, next_skill = classify(src)
        target = upload_dir / src.name if args.copy else src
        if args.copy:
            shutil.copy2(src, target)
        records.append(
            {
                "source": str(src),
                "stored_path": str(target),
                "filename": src.name,
                "extension": src.suffix.lower(),
                "category": category,
                "next_skill": next_skill,
                "size_bytes": src.stat().st_size,
                "sha256": sha256(src),
                "status": "registered",
            }
        )

    manifest = {
        "run_dir": str(run_dir),
        "upload_dir": str(upload_dir),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "files": records,
        "routing_summary": {},
    }
    for item in records:
        key = item.get("category", "unknown")
        manifest["routing_summary"][key] = manifest["routing_summary"].get(key, 0) + 1

    out = run_dir / "upload_manifest.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
