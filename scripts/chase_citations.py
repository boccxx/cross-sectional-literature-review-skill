#!/usr/bin/env python3
"""Expand the candidate pool via citation graph traversal using the OpenAlex API.

Given anchor papers (high-scoring candidates or manually designated DOIs), this script:

  1. Looks up each anchor on OpenAlex by DOI
  2. Retrieves papers that CITE each anchor (forward chasing — who cites this paper)
  3. Retrieves papers that the anchor CITES (backward chasing — what this paper cites)
  4. Deduplicates against the existing candidate_records_dedup.csv
  5. Writes citation_expansion_candidates.csv with newly discovered records

Usage:
    python chase_citations.py \\
        --existing-candidates candidate_records_dedup.csv \\
        --output-dir ./literature_review \\
        [--anchor-dois 10.xxxx/yyy,10.xxxx/zzz] \\
        [--anchor-csv scored_candidates.csv --min-score 7] \\
        [--max-per-anchor 30] \\
        [--forward] [--backward] \\
        [--mailto you@institution.edu]

If neither --anchor-dois nor --anchor-csv is given, the script reads
existing_candidates and uses those with local_relevance_score > 0 sorted
descending, capped at --max-anchors.

Outputs:
    citation_expansion_candidates.csv   — new records not in existing_candidates
    citation_expansion_summary.md       — human-readable summary of the expansion run
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
from dataclasses import dataclass
from pathlib import Path
from typing import Any


USER_AGENT = "study-literature-review/1.0"
OPENALEX_WORKS_BASE = "https://api.openalex.org/works"


def build_ssl_context(insecure_skip_verify: bool) -> ssl.SSLContext | None:
    if not insecure_skip_verify:
        return None
    return ssl._create_unverified_context()  # noqa: SLF001


def http_get_json(url: str, headers: dict[str, str] | None = None, *, insecure_skip_verify: bool = False) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=60, context=build_ssl_context(insecure_skip_verify)) as resp:
        return json.loads(resp.read().decode("utf-8"))


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def normalize_doi(doi: str) -> str:
    doi = (doi or "").strip().lower()
    doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
    return doi


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str:
    if not inverted_index:
        return ""
    words_by_pos: dict[int, str] = {}
    for word, positions in inverted_index.items():
        for pos in positions:
            words_by_pos[pos] = word
    return " ".join(words_by_pos[p] for p in sorted(words_by_pos))


def existing_dois_and_titles(rows: list[dict[str, str]]) -> tuple[set[str], set[str]]:
    dois: set[str] = set()
    titles: set[str] = set()
    for row in rows:
        doi = normalize_doi(row.get("doi") or "")
        if doi:
            dois.add(doi)
        title = normalize_space(row.get("title") or "").lower()
        if title:
            titles.add(title)
    return dois, titles


def fetch_openalex_work_by_doi(doi: str, mailto: str | None, *, insecure_skip_verify: bool = False) -> dict[str, Any] | None:
    params = {"filter": f"doi:{doi}"}
    if mailto:
        params["mailto"] = mailto
    url = OPENALEX_WORKS_BASE + "?" + urllib.parse.urlencode(params)
    try:
        payload = http_get_json(url, headers={"User-Agent": USER_AGENT}, insecure_skip_verify=insecure_skip_verify)
        results = payload.get("results", [])
        return results[0] if results else None
    except Exception as exc:
        print(f"  [chase] Could not fetch OpenAlex work for doi:{doi}: {exc}")
        return None


def fetch_openalex_works_batch(openalex_ids: list[str], mailto: str | None, *, insecure_skip_verify: bool = False) -> list[dict[str, Any]]:
    """Fetch up to 50 OpenAlex works by their IDs in one request."""
    if not openalex_ids:
        return []
    ids_filter = "|".join(openalex_ids[:50])
    params = {"filter": f"openalex_id:{ids_filter}", "per-page": "50"}
    if mailto:
        params["mailto"] = mailto
    url = OPENALEX_WORKS_BASE + "?" + urllib.parse.urlencode(params)
    try:
        payload = http_get_json(url, headers={"User-Agent": USER_AGENT}, insecure_skip_verify=insecure_skip_verify)
        return payload.get("results", [])
    except Exception as exc:
        print(f"  [chase] Batch fetch failed: {exc}")
        return []


def fetch_citing_works(openalex_work_id: str, max_results: int, mailto: str | None, *, insecure_skip_verify: bool = False) -> list[dict[str, Any]]:
    """Return works that cite the given OpenAlex work ID (forward chasing)."""
    params = {
        "filter": f"cites:{openalex_work_id}",
        "per-page": str(min(max_results, 200)),
        "sort": "cited_by_count:desc",
    }
    if mailto:
        params["mailto"] = mailto
    url = OPENALEX_WORKS_BASE + "?" + urllib.parse.urlencode(params)
    try:
        payload = http_get_json(url, headers={"User-Agent": USER_AGENT}, insecure_skip_verify=insecure_skip_verify)
        return payload.get("results", [])
    except Exception as exc:
        print(f"  [chase] Forward chase failed for {openalex_work_id}: {exc}")
        return []


def openalex_work_to_row(work: dict[str, Any], chase_type: str, anchor_doi: str) -> dict[str, str]:
    title = normalize_space(work.get("display_name") or "")
    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    doi = normalize_doi(work.get("doi") or "")
    primary_loc = work.get("primary_location") or {}
    url_value = primary_loc.get("landing_page_url") or primary_loc.get("pdf_url") or (f"https://doi.org/{doi}" if doi else work.get("id", ""))
    year = str(work.get("publication_year") or "")
    pub_date = work.get("publication_date") or ""
    authors = "; ".join(
        a.get("author", {}).get("display_name", "")
        for a in work.get("authorships", [])
        if a.get("author", {}).get("display_name")
    )
    pub_status = "preprint" if work.get("type") == "posted-content" else "peer_reviewed_or_unknown"
    return {
        "search_id": f"CHASE_{chase_type.upper()}",
        "search_round": "chase",
        "query_family": f"citation_chase_{chase_type}",
        "source": "OpenAlex",
        "source_rank": "",
        "title": title,
        "authors": authors,
        "year": year,
        "published_date": pub_date,
        "doi": doi,
        "url": url_value,
        "abstract": abstract,
        "publication_status": pub_status,
        "source_record_id": work.get("id", ""),
        "matched_query": f"citation_chase from anchor doi:{anchor_doi}",
        "local_relevance_score": "0.00",
        "strategy_match_score": "0",
    }


def is_duplicate(row: dict[str, str], existing_dois: set[str], existing_titles: set[str]) -> bool:
    doi = normalize_doi(row.get("doi") or "")
    if doi and doi in existing_dois:
        return True
    title = normalize_space(row.get("title") or "").lower()
    return bool(title and title in existing_titles)


def chase_anchor(
    doi: str,
    existing_dois: set[str],
    existing_titles: set[str],
    max_per_anchor: int,
    do_forward: bool,
    do_backward: bool,
    mailto: str | None,
    insecure_skip_verify: bool,
) -> list[dict[str, str]]:
    print(f"  [chase] Anchor: doi:{doi}")
    work = fetch_openalex_work_by_doi(doi, mailto, insecure_skip_verify=insecure_skip_verify)
    if not work:
        print(f"  [chase] Not found on OpenAlex: doi:{doi}")
        return []

    openalex_id = work.get("id") or ""
    new_rows: list[dict[str, str]] = []
    time.sleep(0.1)

    if do_forward and openalex_id:
        citing = fetch_citing_works(openalex_id, max_per_anchor, mailto, insecure_skip_verify=insecure_skip_verify)
        print(f"    forward: {len(citing)} citing works retrieved")
        for cw in citing:
            row = openalex_work_to_row(cw, "forward", doi)
            if not is_duplicate(row, existing_dois, existing_titles):
                new_rows.append(row)
                existing_dois.add(normalize_doi(row["doi"]))
                existing_titles.add(normalize_space(row["title"]).lower())
        time.sleep(0.2)

    if do_backward:
        ref_ids = work.get("referenced_works") or []
        print(f"    backward: {len(ref_ids)} referenced works in record")
        for batch_start in range(0, min(len(ref_ids), max_per_anchor * 2), 50):
            batch = ref_ids[batch_start: batch_start + 50]
            ref_works = fetch_openalex_works_batch(batch, mailto, insecure_skip_verify=insecure_skip_verify)
            for rw in ref_works:
                row = openalex_work_to_row(rw, "backward", doi)
                if not is_duplicate(row, existing_dois, existing_titles):
                    new_rows.append(row)
                    existing_dois.add(normalize_doi(row["doi"]))
                    existing_titles.add(normalize_space(row["title"]).lower())
            time.sleep(0.15)
            if len(new_rows) >= max_per_anchor:
                break

    print(f"    → {len(new_rows)} new unique records from this anchor")
    return new_rows


def build_summary_md(
    anchor_dois: list[str],
    total_new: int,
    do_forward: bool,
    do_backward: bool,
    output_path: Path,
) -> str:
    direction = []
    if do_forward:
        direction.append("forward (citing)")
    if do_backward:
        direction.append("backward (references)")
    lines = [
        "# Citation Expansion Summary",
        "",
        f"**Anchors processed:** {len(anchor_dois)}",
        f"**Chase direction(s):** {', '.join(direction) or 'none'}",
        f"**New unique records added:** {total_new}",
        f"**Output:** {output_path}",
        "",
        "## Anchor DOIs",
        "",
    ]
    for doi in anchor_dois:
        lines.append(f"- {doi}")
    lines += [
        "",
        "## Next Step",
        "",
        "Run `score_candidates.py` on `citation_expansion_candidates.csv` (or merge it",
        "into `candidate_records_dedup.csv` first) to score the newly discovered papers.",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Expand candidate pool via OpenAlex citation graph traversal.",
    )
    parser.add_argument("--existing-candidates", required=True, help="Path to candidate_records_dedup.csv")
    parser.add_argument("--output-dir", required=True, help="Directory to write citation_expansion_candidates.csv")
    parser.add_argument("--anchor-dois", default="", help="Comma-separated list of anchor DOIs (e.g. 10.1234/abc,10.5678/def)")
    parser.add_argument("--anchor-csv", default="", help="Path to scored_candidates.csv; use papers with score >= --min-score as anchors")
    parser.add_argument("--min-score", type=int, default=7, help="Minimum llm_relevance_score for anchor selection from --anchor-csv (default: 7)")
    parser.add_argument("--max-anchors", type=int, default=20, help="Maximum number of anchor papers to chase (default: 20)")
    parser.add_argument("--max-per-anchor", type=int, default=30, help="Maximum new records to collect per anchor paper (default: 30)")
    parser.add_argument("--forward", action="store_true", default=True, help="Chase forward (papers that cite the anchor)")
    parser.add_argument("--backward", action="store_true", default=True, help="Chase backward (papers the anchor cites)")
    parser.add_argument("--no-forward", dest="forward", action="store_false", help="Disable forward citation chasing")
    parser.add_argument("--no-backward", dest="backward", action="store_false", help="Disable backward citation chasing")
    parser.add_argument("--mailto", default="", help="Email for OpenAlex polite pool (recommended)")
    parser.add_argument("--insecure-skip-verify", action="store_true", help="Skip SSL certificate verification")
    args = parser.parse_args()

    existing_path = Path(args.existing_candidates)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    existing_rows = read_csv(existing_path) if existing_path.exists() else []
    existing_dois, existing_titles = existing_dois_and_titles(existing_rows)
    print(f"[chase_citations] Existing pool: {len(existing_rows)} records, {len(existing_dois)} unique DOIs")

    # Collect anchor DOIs
    anchor_dois: list[str] = []

    if args.anchor_dois:
        for doi in args.anchor_dois.split(","):
            doi = normalize_doi(doi.strip())
            if doi:
                anchor_dois.append(doi)

    if args.anchor_csv and Path(args.anchor_csv).exists():
        scored = read_csv(Path(args.anchor_csv))
        for row in scored:
            try:
                score = float(row.get("llm_relevance_score") or 0)
            except ValueError:
                score = 0.0
            if score >= args.min_score:
                doi = normalize_doi(row.get("doi") or "")
                if doi and doi not in anchor_dois:
                    anchor_dois.append(doi)

    if not anchor_dois:
        # Fall back to top records by local_relevance_score
        try:
            sorted_rows = sorted(existing_rows, key=lambda r: float(r.get("local_relevance_score") or 0), reverse=True)
        except Exception:
            sorted_rows = existing_rows
        for row in sorted_rows:
            doi = normalize_doi(row.get("doi") or "")
            if doi and doi not in anchor_dois:
                anchor_dois.append(doi)
            if len(anchor_dois) >= args.max_anchors:
                break

    anchor_dois = anchor_dois[: args.max_anchors]
    print(f"[chase_citations] Chasing {len(anchor_dois)} anchor(s) | forward={args.forward} | backward={args.backward}")

    all_new: list[dict[str, str]] = []
    for doi in anchor_dois:
        new = chase_anchor(
            doi=doi,
            existing_dois=existing_dois,
            existing_titles=existing_titles,
            max_per_anchor=args.max_per_anchor,
            do_forward=args.forward,
            do_backward=args.backward,
            mailto=args.mailto or None,
            insecure_skip_verify=args.insecure_skip_verify,
        )
        all_new.extend(new)
        time.sleep(0.3)

    print(f"\n[chase_citations] Total new records: {len(all_new)}")

    raw_fieldnames = [
        "search_id", "search_round", "query_family", "source", "source_rank",
        "title", "authors", "year", "published_date", "doi", "url", "abstract",
        "publication_status", "source_record_id", "matched_query",
        "local_relevance_score", "strategy_match_score",
    ]
    out_path = output_dir / "citation_expansion_candidates.csv"
    write_csv(out_path, all_new, raw_fieldnames)
    print(f"[chase_citations] Wrote {out_path}")

    summary_md = build_summary_md(anchor_dois, len(all_new), args.forward, args.backward, out_path)
    summary_path = output_dir / "citation_expansion_summary.md"
    summary_path.write_text(summary_md, encoding="utf-8")
    print(f"[chase_citations] Wrote {summary_path}")


if __name__ == "__main__":
    main()
