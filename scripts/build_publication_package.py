#!/usr/bin/env python3
"""Package completed review narratives without generating scientific prose."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


def read_json(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"Required file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def artifact_record(path: Path, *, source_sha256: str = "", generator: str = "") -> dict:
    record = {
        "file": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": path.stat().st_size,
    }
    if source_sha256:
        record["source_sha256"] = source_sha256
    if generator:
        record["generator"] = generator
    return record


def authors(entry: dict) -> str:
    value = entry.get("authors", "")
    if isinstance(value, list):
        return " and ".join(str(item) for item in value)
    return " and ".join(part.strip() for part in str(value).split(";") if part.strip())


def bibtex(entry: dict) -> str:
    key = entry.get("paper_id") or entry.get("citation_id") or "reference"
    fields = {
        "title": entry.get("title", ""),
        "author": authors(entry),
        "journal": entry.get("journal", ""),
        "year": entry.get("year", ""),
        "doi": str(entry.get("doi", "")).replace("https://doi.org/", ""),
        "url": entry.get("url", ""),
    }
    lines = [f"@article{{{key},"]
    for name, value in fields.items():
        if value:
            safe = str(value).replace("{", "\\{").replace("}", "\\}")
            lines.append(f"  {name} = {{{safe}}},")
    lines.append("}")
    return "\n".join(lines)


def section_metrics(text: str) -> list[dict]:
    sections = []
    current = "Opening"
    buffer: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^#{1,3}\s+(.+)$", line)
        if match:
            if buffer:
                body = "\n".join(buffer)
                sections.append({"section": current, "words": len(body.split()), "citation_ids": len(re.findall(r"\[P[^\]]+\]", body))})
            current = match.group(1).strip()
            buffer = []
        else:
            buffer.append(line)
    body = "\n".join(buffer)
    sections.append({"section": current, "words": len(body.split()), "citation_ids": len(re.findall(r"\[P[^\]]+\]", body))})
    return sections


def main() -> int:
    parser = argparse.ArgumentParser(description="Package already completed literature-review narratives.")
    parser.add_argument("project_root")
    parser.add_argument("--review-dir", default="")
    parser.add_argument("--input", action="append", default=[])
    parser.add_argument("--citation-style", choices=["vancouver", "apa"], default="vancouver")
    parser.add_argument("--export", action="store_true")
    args = parser.parse_args()

    root = Path(args.project_root)
    review_dir = Path(args.review_dir) if args.review_dir else root / "literature_review"
    inputs = [Path(value) for value in args.input] or [review_dir / "literature_review_synthesis.md"]
    missing = [str(path) for path in inputs if not path.exists()]
    if missing:
        raise SystemExit("Completed narrative file(s) missing: " + ", ".join(missing))
    if args.export and len(inputs) != 1:
        raise SystemExit("Publication export requires exactly one completed narrative source")
    outside_review_dir = [str(path) for path in inputs if path.resolve().parent != review_dir.resolve()]
    if outside_review_dir:
        raise SystemExit("Publication narrative source(s) must be stored directly in the review directory: " + ", ".join(outside_review_dir))
    citation_registry = read_json(review_dir / "citation_registry.json")
    entries = citation_registry.get("entries", [])
    if not entries:
        raise SystemExit("citation_registry.json has no entries")

    write_text(review_dir / "references.bib", "\n\n".join(bibtex(entry) for entry in entries))
    reports = []
    for path in inputs:
        text = path.read_text(encoding="utf-8")
        if re.search(r"\b(?:TODO|TBD)\b|\*\*\*\*", text, re.I):
            raise SystemExit(f"Narrative contains unresolved placeholders: {path}")
        reports.append({"file": path.name, "sections": section_metrics(text)})
        if args.export:
            subprocess.run(
                [sys.executable, str(Path(__file__).with_name("export_review.py")), "--input", str(path), "--output-dir", str(review_dir)],
                check=True,
            )
    write_json(review_dir / "delivery_quality_report.json", {"files": reports})
    publication_names = ["references.bib", "delivery_quality_report.json"]
    if args.export:
        publication_names.extend(["literature_review.docx", "literature_review.pdf", "literature_review.tex"])
    verification_names = ["citation_verification_report.csv", "citation_verification_summary.md"]
    artifact_paths = inputs + [review_dir / name for name in publication_names + verification_names]
    missing_artifacts = [str(path) for path in artifact_paths if not path.exists() or path.stat().st_size == 0]
    if missing_artifacts:
        raise SystemExit("Publication manifest cannot bind missing/empty artifacts: " + ", ".join(missing_artifacts))
    source_sha256 = hashlib.sha256(inputs[0].read_bytes()).hexdigest()
    export_names = {"literature_review.docx", "literature_review.pdf", "literature_review.tex"}
    artifact_rows = []
    for path in artifact_paths:
        artifact_rows.append(
            artifact_record(
                path,
                source_sha256=source_sha256 if path.name in export_names else "",
                generator="export_review.py" if path.name in export_names else "",
            )
        )
    write_json(
        review_dir / "publication_manifest.json",
        {
            "manifest_version": "2.1",
            "venue_profile": "user_or_journal_defined",
            "citation_style": args.citation_style,
            "languages": [],
            "source_files": [artifact_record(path) for path in inputs],
            "artifacts": artifact_rows,
        },
    )
    print(f"Publication package built from {len(inputs)} completed narrative(s) in {review_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
