#!/usr/bin/env python3
"""Verify citation metadata against CrossRef for papers in scored_candidates.csv or citation_registry.json.

For each record with a DOI, this script:
  - Queries CrossRef API (https://api.crossref.org/works/{doi})
  - Compares title, first author last name, and publication year
  - Flags mismatches or missing DOIs
  - Assigns a verification_status to each record

Usage:
    python verify_citations.py \\
        --input scored_candidates.csv \\
        --output-dir ./literature_review \\
        [--mailto you@institution.edu] \\
        [--title-similarity-threshold 0.75] \\
        [--skip-no-doi]

Or verify a citation_registry.json:
    python verify_citations.py \\
        --input citation_registry.json \\
        --output-dir ./literature_review

Outputs:
    citation_verification_report.csv   — per-record verification results
    citation_verification_summary.md   — human-readable summary
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


USER_AGENT = "study-literature-review/1.0 (crossref-polite-pool)"
CROSSREF_BASE = "https://api.crossref.org/works"


def build_ssl_context(insecure_skip_verify: bool) -> ssl.SSLContext | None:
    if not insecure_skip_verify:
        return None
    return ssl._create_unverified_context()  # noqa: SLF001


def http_get_json(url: str, headers: dict[str, str] | None = None, *, insecure_skip_verify: bool = False) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30, context=build_ssl_context(insecure_skip_verify)) as resp:
        return json.loads(resp.read().decode("utf-8"))


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def normalize_doi(doi: str) -> str:
    doi = (doi or "").strip().lower()
    doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
    return doi


def first_author_surname(authors_raw: str) -> str:
    first = normalize_space(authors_raw).split(";")[0].strip()
    if not first:
        return ""
    return (first.split(",")[0] if "," in first else first.split()[0]).strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def title_similarity(a: str, b: str) -> float:
    """Simple token-overlap Jaccard similarity between two titles."""
    a_tokens = set(re.findall(r"[a-z0-9]+", a.lower()))
    b_tokens = set(re.findall(r"[a-z0-9]+", b.lower()))
    if not a_tokens or not b_tokens:
        return 0.0
    intersection = a_tokens & b_tokens
    union = a_tokens | b_tokens
    return len(intersection) / len(union)


def crossref_lookup(doi: str, mailto: str | None, *, insecure_skip_verify: bool = False) -> dict[str, Any] | None:
    encoded_doi = urllib.parse.quote(doi, safe="")
    url = f"{CROSSREF_BASE}/{encoded_doi}"
    headers = {"User-Agent": USER_AGENT}
    if mailto:
        headers["User-Agent"] = f"{USER_AGENT}; mailto:{mailto}"
    try:
        payload = http_get_json(url, headers=headers, insecure_skip_verify=insecure_skip_verify)
        return payload.get("message")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def extract_crossref_year(message: dict[str, Any]) -> str:
    for key in ("published-print", "published-online", "published", "issued"):
        date_parts = (message.get(key) or {}).get("date-parts")
        if date_parts and date_parts[0]:
            return str(date_parts[0][0])
    return ""


def extract_crossref_first_author_last(message: dict[str, Any]) -> str:
    authors = message.get("author") or []
    if authors:
        return normalize_space(authors[0].get("family") or "")
    return ""


def extract_crossref_title(message: dict[str, Any]) -> str:
    titles = message.get("title") or []
    return normalize_space(titles[0]) if titles else ""


def extract_crossref_journal(message: dict[str, Any]) -> str:
    container = message.get("container-title") or []
    return normalize_space(container[0]) if container else ""


def extract_crossref_type(message: dict[str, Any]) -> str:
    return message.get("type") or ""


def verify_record(
    doi: str,
    local_title: str,
    local_year: str,
    local_first_author: str,
    title_threshold: float,
    mailto: str | None,
    insecure_skip_verify: bool,
) -> dict[str, str]:
    """Look up a DOI on CrossRef and return a verification result dict."""
    result: dict[str, str] = {
        "doi": doi,
        "local_title": local_title,
        "local_year": local_year,
        "local_first_author": local_first_author,
        "crossref_title": "",
        "crossref_year": "",
        "crossref_first_author": "",
        "crossref_journal": "",
        "crossref_type": "",
        "title_similarity": "",
        "year_match": "",
        "author_match": "",
        "verification_status": "",
        "notes": "",
    }

    if not doi:
        result["verification_status"] = "no_doi"
        return result

    try:
        message = crossref_lookup(doi, mailto, insecure_skip_verify=insecure_skip_verify)
    except Exception as exc:
        result["verification_status"] = "error"
        result["notes"] = str(exc)[:200]
        return result

    if message is None:
        result["verification_status"] = "doi_not_found"
        result["notes"] = "DOI returned 404 on CrossRef"
        return result

    cr_title = extract_crossref_title(message)
    cr_year = extract_crossref_year(message)
    cr_author = extract_crossref_first_author_last(message)
    cr_journal = extract_crossref_journal(message)
    cr_type = extract_crossref_type(message)

    result["crossref_title"] = cr_title
    result["crossref_year"] = cr_year
    result["crossref_first_author"] = cr_author
    result["crossref_journal"] = cr_journal
    result["crossref_type"] = cr_type

    sim = title_similarity(local_title, cr_title) if local_title and cr_title else 0.0
    result["title_similarity"] = f"{sim:.3f}"

    year_ok = not local_year or not cr_year or local_year == cr_year
    result["year_match"] = "yes" if year_ok else "no"

    local_last = ""
    if local_first_author:
        parts = re.split(r"[\s,;]+", local_first_author.strip())
        local_last = parts[-1].lower() if parts else ""
    author_ok = not local_last or not cr_author or (local_last in cr_author.lower())
    result["author_match"] = "yes" if author_ok else "no"

    if sim >= title_threshold and year_ok and author_ok:
        result["verification_status"] = "verified"
    elif sim >= title_threshold:
        result["verification_status"] = "title_ok_metadata_mismatch"
        notes = []
        if not year_ok:
            notes.append(f"year: local={local_year} crossref={cr_year}")
        if not author_ok:
            notes.append(f"first_author: local={local_last!r} crossref={cr_author!r}")
        result["notes"] = "; ".join(notes)
    elif sim > 0.3:
        result["verification_status"] = "partial_match_review_needed"
        result["notes"] = f"title_similarity={sim:.3f}; may be a related but different paper"
    else:
        result["verification_status"] = "likely_mismatch"
        result["notes"] = f"title_similarity={sim:.3f}; CrossRef title: {cr_title[:80]!r}"

    return result


def load_input(path: Path) -> list[dict[str, str]]:
    """Return citation identity records from CSV or a citation registry JSON."""
    suffix = path.suffix.lower()
    records: list[dict[str, str]] = []

    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data if isinstance(data, list) else data.get("entries", data.get("citations", data.get("items", [])))
        for item in items:
            doi = normalize_doi(item.get("doi") or "")
            title = normalize_space(item.get("title") or "")
            year = str(item.get("year") or "")
            authors_raw = item.get("authors") or item.get("author") or ""
            if isinstance(authors_raw, list):
                authors_raw = "; ".join(str(a) for a in authors_raw)
            first_last = first_author_surname(str(authors_raw))
            records.append({
                "citation_id": str(item.get("citation_id") or ""),
                "reference_number": str(item.get("reference_number") or ""),
                "doi": doi,
                "title": title,
                "year": year,
                "first_author": first_last,
            })
    else:
        rows = read_csv(path)
        for row in rows:
            doi = normalize_doi(row.get("doi") or "")
            title = normalize_space(row.get("title") or "")
            year = str(row.get("year") or "")
            authors_raw = normalize_space(row.get("authors") or "")
            first_last = first_author_surname(authors_raw)
            records.append({
                "citation_id": str(row.get("citation_id") or row.get("paper_id") or ""),
                "reference_number": str(row.get("reference_number") or ""),
                "doi": doi,
                "title": title,
                "year": year,
                "first_author": first_last,
            })

    return records


def build_summary_md(results: list[dict[str, str]]) -> str:
    status_counts: dict[str, int] = {}
    for r in results:
        s = r.get("verification_status") or "unknown"
        status_counts[s] = status_counts.get(s, 0) + 1

    lines = [
        "# Citation Verification Summary",
        "",
        f"**Total records checked:** {len(results)}",
        "",
        "## Status Breakdown",
        "",
        "| Status | Count |",
        "|---|---|",
    ]
    for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| `{status}` | {count} |")

    mismatches = [r for r in results if r.get("verification_status") not in ("verified", "no_doi")]
    if mismatches:
        lines += [
            "",
            "## Records Needing Review",
            "",
            "| DOI | Status | Notes |",
            "|---|---|---|",
        ]
        for r in mismatches[:50]:
            doi = r.get("doi") or ""
            status = r.get("verification_status") or ""
            notes = (r.get("notes") or "")[:80]
            lines.append(f"| {doi} | `{status}` | {notes} |")
        if len(mismatches) > 50:
            lines.append(f"| … | … | {len(mismatches) - 50} more — see full report CSV |")

    lines += [
        "",
        "## Verification Status Key",
        "",
        "| Status | Meaning |",
        "|---|---|",
        "| `verified` | Title, year, and author all match CrossRef |",
        "| `title_ok_metadata_mismatch` | Title matches but year or author differs (usually harmless) |",
        "| `partial_match_review_needed` | Title partially matches; review manually |",
        "| `likely_mismatch` | Title similarity < 0.3; possible wrong DOI |",
        "| `doi_not_found` | DOI not in CrossRef database |",
        "| `no_doi` | No DOI available for this record |",
        "| `error` | Network or API error during lookup |",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify citation metadata against CrossRef.",
    )
    parser.add_argument("--input", required=True, help="Path to scored_candidates.csv or citation_registry.json")
    parser.add_argument("--output-dir", required=True, help="Directory to write citation_verification_report.csv")
    parser.add_argument("--mailto", default="", help="Email for CrossRef polite pool (recommended; improves rate limits)")
    parser.add_argument("--title-similarity-threshold", type=float, default=0.75, help="Jaccard title similarity threshold for verification (default: 0.75)")
    parser.add_argument("--skip-no-doi", action="store_true", help="Skip records without a DOI entirely")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds to wait between CrossRef requests (default: 0.5)")
    parser.add_argument("--insecure-skip-verify", action="store_true", help="Skip SSL certificate verification")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    records = load_input(input_path)
    print(f"[verify_citations] Loaded {len(records)} records from {input_path}")

    if args.skip_no_doi:
        records = [record for record in records if record["doi"]]
        print(f"[verify_citations] After --skip-no-doi filter: {len(records)} records")

    results: list[dict[str, str]] = []
    for i, record in enumerate(records, start=1):
        if i % 20 == 0:
            print(f"  [{i}/{len(records)}] …")
        result = verify_record(
            doi=record["doi"],
            local_title=record["title"],
            local_year=record["year"],
            local_first_author=record["first_author"],
            title_threshold=args.title_similarity_threshold,
            mailto=args.mailto or None,
            insecure_skip_verify=args.insecure_skip_verify,
        )
        result["citation_id"] = record["citation_id"]
        result["reference_number"] = record["reference_number"]
        results.append(result)
        if record["doi"]:
            time.sleep(args.delay)

    report_fieldnames = [
        "citation_id", "reference_number",
        "doi", "local_title", "local_year", "local_first_author",
        "crossref_title", "crossref_year", "crossref_first_author",
        "crossref_journal", "crossref_type",
        "title_similarity", "year_match", "author_match",
        "verification_status", "notes",
    ]
    report_path = output_dir / "citation_verification_report.csv"
    write_csv(report_path, results, report_fieldnames)
    print(f"[verify_citations] Wrote {report_path}")

    summary_md = build_summary_md(results)
    summary_path = output_dir / "citation_verification_summary.md"
    summary_path.write_text(summary_md, encoding="utf-8")
    print(f"[verify_citations] Wrote {summary_path}")

    verified = sum(1 for r in results if r.get("verification_status") == "verified")
    mismatches = sum(1 for r in results if r.get("verification_status") == "likely_mismatch")
    not_found = sum(1 for r in results if r.get("verification_status") == "doi_not_found")
    print(f"\n[verify_citations] verified={verified} | likely_mismatch={mismatches} | doi_not_found={not_found}")


if __name__ == "__main__":
    main()
