#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path


TYPE_MARKS = {
    "journal": "J",
    "article-journal": "J",
    "conference": "C",
    "paper-conference": "C",
    "book": "M",
    "chapter": "M",
    "thesis": "D",
    "report": "R",
    "standard": "S",
    "patent": "P",
    "dataset": "DS",
    "preprint": "EB/OL",
    "web": "EB/OL",
}


def load_refs(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        if isinstance(data, dict):
            return data.get("references") or data.get("papers") or data.get("results") or [data]
        return data
    refs = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            refs.append({"type": "unknown", "title": line})
    return refs


def normalize_ref(raw: dict) -> dict:
    authors = raw.get("authors") or raw.get("author") or []
    if isinstance(authors, str):
        authors = [x.strip() for x in re.split(r";| and |,", authors) if x.strip()]
    year = raw.get("year") or raw.get("issued") or raw.get("publication_year") or ""
    if isinstance(year, dict):
        try:
            year = year["date-parts"][0][0]
        except Exception:
            year = ""
    return {
        "type": raw.get("type") or "journal",
        "authors": authors,
        "title": raw.get("title") or "",
        "year": year,
        "venue": raw.get("venue") or raw.get("journal") or raw.get("container-title") or "",
        "volume": raw.get("volume") or "",
        "issue": raw.get("issue") or "",
        "pages": raw.get("pages") or raw.get("page") or "",
        "publisher": raw.get("publisher") or "",
        "place": raw.get("place") or raw.get("publisher-place") or "",
        "doi": (raw.get("doi") or raw.get("DOI") or "").replace("https://doi.org/", ""),
        "url": raw.get("url") or raw.get("URL") or "",
        "accessed": raw.get("accessed") or "",
        "raw": raw,
    }


def last_name(name: str) -> str:
    parts = name.strip().split()
    return parts[-1] if parts else name


def initials(name: str, dots: bool = False) -> str:
    parts = name.strip().replace(",", " ").split()
    if len(parts) <= 1:
        return ""
    letters = [p[0].upper() for p in parts[:-1] if p]
    return (".".join(letters) + ".") if dots and letters else "".join(letters)


def format_authors(authors: list[str], profile: dict, style: str) -> str:
    if not authors:
        return "NEEDS_CHECK"
    source_uses_et_al = any(str(author).strip().lower().rstrip(".") == "et al" for author in authors)
    authors = [author for author in authors if str(author).strip().lower().rstrip(".") != "et al"]
    if not authors:
        return "NEEDS_CHECK"
    max_authors = int(profile.get("max_authors_before_et_al") or 6)
    et_al = profile.get("et_al") or "et al."
    shown = authors if len(authors) <= max_authors else authors[:1 if style == "nature" else max_authors]
    if style.startswith("gbt7714"):
        body = ", ".join(shown)
    elif style in {"ieee"}:
        body = ", ".join(f"{initials(a, dots=True)} {last_name(a)}".strip() for a in shown)
    elif style in {"nature", "science", "cell"}:
        body = ", ".join(f"{last_name(a)}, {initials(a, dots=True)}".strip().rstrip(",") for a in shown)
    else:
        body = ", ".join(shown)
    if source_uses_et_al or len(authors) > max_authors:
        body += f", {et_al}"
    return body


def gbt(ref: dict, profile: dict) -> str:
    mark = TYPE_MARKS.get(ref["type"], "Z")
    authors = format_authors(ref["authors"], profile, "gbt7714")
    title = ref["title"] or "NEEDS_CHECK"
    venue = ref["venue"] or ref["publisher"] or "NEEDS_CHECK"
    year = ref["year"] or "NEEDS_CHECK"
    loc = ""
    if ref["volume"]:
        loc += f", {ref['volume']}"
    if ref["issue"]:
        loc += f"({ref['issue']})"
    if ref["pages"]:
        loc += f": {ref['pages']}"
    tail = ""
    if ref["doi"]:
        tail += f" DOI:{ref['doi']}."
    elif ref["url"]:
        tail += f" {ref['url']}."
    return f"{authors}. {title}[{mark}]. {venue}, {year}{loc}.{tail}".strip()


def ieee(ref: dict, profile: dict) -> str:
    authors = format_authors(ref["authors"], profile, "ieee")
    title = ref["title"] or "NEEDS_CHECK"
    venue = ref["venue"] or "NEEDS_CHECK"
    bits = [authors + f', "{title},"', venue]
    if ref["volume"]:
        bits.append(f"vol. {ref['volume']}")
    if ref["issue"]:
        bits.append(f"no. {ref['issue']}")
    if ref["pages"]:
        bits.append(f"pp. {ref['pages']}")
    if ref["year"]:
        bits.append(str(ref["year"]))
    line = ", ".join(x for x in bits if x)
    if ref["doi"]:
        line += f", doi: {ref['doi']}"
    return line + "."


def nature_like(ref: dict, profile: dict, style: str) -> str:
    authors = format_authors(ref["authors"], profile, style).rstrip(".")
    title = ref["title"] or "NEEDS_CHECK"
    venue = ref["venue"] or "NEEDS_CHECK"
    line = f"{authors}. {title}. {venue}"
    if ref["volume"]:
        line += f" {ref['volume']}"
    if ref["pages"]:
        line += f", {ref['pages']}"
    if ref["year"]:
        line += f" ({ref['year']})"
    if ref["doi"]:
        line += f". https://doi.org/{ref['doi']}"
    return line + "."


def apa(ref: dict, profile: dict) -> str:
    authors = format_authors(ref["authors"], profile, "apa")
    year = ref["year"] or "n.d."
    title = ref["title"] or "NEEDS_CHECK"
    venue = ref["venue"] or "NEEDS_CHECK"
    line = f"{authors} ({year}). {title}. {venue}"
    if ref["volume"]:
        line += f", {ref['volume']}"
    if ref["issue"]:
        line += f"({ref['issue']})"
    if ref["pages"]:
        line += f", {ref['pages']}"
    if ref["doi"]:
        line += f". https://doi.org/{ref['doi']}"
    return line + "."


def bibtex_key(ref: dict) -> str:
    first = re.sub(r"\W+", "", last_name(ref["authors"][0]).lower()) if ref["authors"] else "ref"
    return f"{first}{ref['year'] or 'nd'}"


def bibtex(ref: dict) -> str:
    typ = "article" if TYPE_MARKS.get(ref["type"], "J") == "J" else "misc"
    fields = {
        "author": " and ".join(ref["authors"]) or "NEEDS_CHECK",
        "title": ref["title"] or "NEEDS_CHECK",
        "journal": ref["venue"],
        "year": str(ref["year"] or "NEEDS_CHECK"),
        "volume": ref["volume"],
        "number": ref["issue"],
        "pages": ref["pages"],
        "doi": ref["doi"],
        "url": ref["url"],
    }
    body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields.items() if v)
    return f"@{typ}{{{bibtex_key(ref)},\n{body}\n}}"


def format_one(ref: dict, profile: dict) -> str:
    key = profile["key"]
    if key.startswith("gbt7714"):
        return gbt(ref, profile)
    if key == "ieee":
        return ieee(ref, profile)
    if key == "apa":
        return apa(ref, profile)
    if key in {"nature", "science", "cell"}:
        return nature_like(ref, profile, key)
    if profile.get("citation_mode", "").startswith("numeric"):
        return ieee(ref, profile)
    return apa(ref, profile)


def audit(ref: dict, index: int) -> list[str]:
    required = ["authors", "title", "year", "venue"]
    recommended = ["doi", "volume", "issue", "pages"]
    missing = [field for field in required if not ref.get(field)]
    issues = []
    if missing:
        issues.append(f"Reference {index}: missing {', '.join(missing)}")
    missing_recommended = [field for field in recommended if not ref.get(field)]
    if missing_recommended:
        issues.append(f"Reference {index}: missing recommended metadata {', '.join(missing_recommended)}")
    if not ref.get("type"):
        issues.append(f"Reference {index}: missing type")
    if ref.get("doi") and not re.match(r"^10\.\S+/.+", ref["doi"]):
        issues.append(f"Reference {index}: suspicious DOI `{ref['doi']}`")
    if ref.get("url") and not re.match(r"https?://", ref["url"]):
        issues.append(f"Reference {index}: suspicious URL `{ref['url']}`")
    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description="Format references with local strict profiles and produce an audit report.")
    parser.add_argument("input")
    parser.add_argument("--profiles", default="rules/style_profiles.json")
    parser.add_argument("--style", action="append", help="Style key. Repeat or omit for core styles.")
    parser.add_argument("--out-dir", default=".")
    args = parser.parse_args()

    profile_path = Path(args.profiles)
    if not profile_path.exists():
        skill_profile_path = Path(__file__).resolve().parents[1] / "references" / "style_profiles.json"
        if skill_profile_path.exists():
            profile_path = skill_profile_path
    profiles = json.loads(profile_path.read_text(encoding="utf-8"))
    selected = set(args.style or ["gbt7714-numeric", "ieee", "nature", "apa"])
    refs = [normalize_ref(r) for r in load_refs(Path(args.input))]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    report = ["# Citation Check Report", ""]
    for i, ref in enumerate(refs, 1):
        report.extend(f"- {issue}" for issue in audit(ref, i))
    if len(report) == 2:
        report.append("- No blocking metadata issues found.")

    for profile in profiles:
        if profile["key"] not in selected:
            continue
        lines = [f"# References - {profile['display_name']}", ""]
        for i, ref in enumerate(refs, 1):
            prefix = f"[{i}] " if profile.get("citation_mode", "").startswith("numeric") else ""
            lines.append(prefix + format_one(ref, profile))
        safe = profile["key"].replace("-", "_")
        (out_dir / f"references_{safe}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    (out_dir / "references.bib").write_text("\n\n".join(bibtex(r) for r in refs) + "\n", encoding="utf-8")
    (out_dir / "citation_check_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(out_dir / "citation_check_report.md")


if __name__ == "__main__":
    main()

