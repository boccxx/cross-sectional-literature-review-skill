#!/usr/bin/env python3
"""Execute a live multi-source literature search from search_log.csv.

This script is intentionally pragmatic:

- OpenAlex and PubMed are queried directly via official APIs.
- Semantic Scholar is queried via the Semantic Scholar Graph API; an optional
  API key raises rate limits from 100 req/5min to 1 req/sec.
- Europe PMC is queried via the EBI REST API (free, no auth required).
- medRxiv and bioRxiv are queried via the official bioRxiv API using
  date-window retrieval plus local keyword scoring because the official
  API exposes interval endpoints rather than free-text search.
- Embase and Web of Science are marked as access-controlled sources. The
  search log is updated honestly when credentials or export workflows are
  still missing.

The output is designed to be auditable rather than pretty:

- updated `search_log.csv`
- `candidate_records_raw.csv`
- `candidate_records_dedup.csv`
- source-specific JSON payloads under `raw_results/`
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import socket
import ssl
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


USER_AGENT = "study-literature-review/1.0"
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "between", "by", "for", "from",
    "in", "into", "is", "it", "of", "on", "or", "the", "to", "using", "with",
}
GENERIC_QUERY_TOKENS = {
    "adult",
    "adults",
    "associated",
    "association",
    "clinical",
    "comparing",
    "comparison",
    "disease",
    "event",
    "events",
    "major",
    "multiple",
    "outcome",
    "outcomes",
    "patient",
    "patients",
    "population",
    "populations",
    "research",
    "risk",
    "risks",
    "study",
    "treated",
    "treatment",
    "versus",
}
CONTINUE_TERMS = ("continue", "continuing", "continued", "persistence", "persistent", "maintained")
STOP_TERMS = ("stop", "stopping", "discontinu", "cessation", "cease", "withdraw", "deprescrib", "termination")
DESIGN_STRATEGY_TERMS = (
    "target trial", "grace period", "active comparator",
    "prior user", "new user design", "incident user",
)
STRATEGY_QUERY_FAMILIES = {
    "direct_association",
    "design_estimand",
    "strategy_comparison",
    "clinical_trigger_strategy",
    "outcome_specific_strategy",
}


@dataclass
class SearchResult:
    title: str
    authors: str
    year: str
    published_date: str
    abstract: str
    doi: str
    url: str
    source_record_id: str
    publication_status: str
    raw: dict[str, Any]
    local_relevance_score: float


def infer_publication_status(*parts: str) -> str:
    blob = " ".join(part or "" for part in parts).lower()
    if any(token in blob for token in ["medrxiv", "biorxiv", "arxiv", "preprint", "preprints202", "ssrn"]):
        return "preprint"
    return "peer_reviewed_or_unknown"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_ssl_context(insecure_skip_verify: bool) -> ssl.SSLContext | None:
    if not insecure_skip_verify:
        return None
    return ssl._create_unverified_context()  # noqa: SLF001


def http_get_json(url: str, headers: dict[str, str] | None = None, *, insecure_skip_verify: bool = False) -> dict[str, Any]:
    last_error: Exception | None = None
    request_headers = {**(headers or {}), "Connection": "close"}
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers=request_headers)
            with urllib.request.urlopen(req, timeout=60, context=build_ssl_context(insecure_skip_verify)) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # transient truncation/reset is common behind proxies
            last_error = exc
            if attempt < 3:
                time.sleep(0.4 * (attempt + 1))
    assert last_error is not None
    raise last_error


def http_get_text(url: str, headers: dict[str, str] | None = None, *, insecure_skip_verify: bool = False) -> str:
    last_error: Exception | None = None
    request_headers = {**(headers or {}), "Connection": "close"}
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers=request_headers)
            with urllib.request.urlopen(req, timeout=60, context=build_ssl_context(insecure_skip_verify)) as resp:
                return resp.read().decode("utf-8")
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(0.4 * (attempt + 1))
    assert last_error is not None
    raise last_error


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def classify_exception(exc: Exception) -> dict[str, str]:
    """Turn operational failures into actionable diagnostics."""
    message = normalize_space(str(exc))
    lowered = message.lower()

    if isinstance(exc, urllib.error.HTTPError):
        code = getattr(exc, "code", None)
        if code == 429:
            return {
                "class": "http_rate_limited",
                "message": message,
                "hint": "Retry later or add provider API keys such as --ncbi-api-key or --ss-api-key.",
            }
        if code in {401, 403}:
            return {
                "class": "http_auth_or_access_denied",
                "message": message,
                "hint": "Check whether the source requires credentials, institutional access, or a provider key.",
            }
        if code and code >= 500:
            return {
                "class": "http_upstream_server_error",
                "message": message,
                "hint": "The provider appears unavailable; retry later or switch sources for the current round.",
            }

    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        reason_text = normalize_space(str(reason or message)).lower()
        if isinstance(reason, socket.gaierror) or any(
            token in reason_text
            for token in [
                "nodename nor servname provided",
                "name or service not known",
                "temporary failure in name resolution",
                "no address associated with hostname",
            ]
        ):
            return {
                "class": "network_dns_resolution_failed",
                "message": message,
                "hint": "The runtime cannot resolve provider hostnames. Check DNS/network access first; if connectivity is unavailable, seed a manually verified corpus and document the downgrade.",
            }
        if "certificate" in reason_text or "ssl" in reason_text:
            return {
                "class": "network_ssl_error",
                "message": message,
                "hint": "Check local root certificates. If the network is trusted but the certificate store is incomplete, retry with --insecure-skip-verify.",
            }
        if "timed out" in reason_text or isinstance(reason, TimeoutError):
            return {
                "class": "network_timeout",
                "message": message,
                "hint": "The source did not respond in time. Retry later, lower concurrency externally, or narrow the current query family.",
            }
        if any(token in reason_text for token in ["refused", "unreachable", "reset by peer"]):
            return {
                "class": "network_connection_failed",
                "message": message,
                "hint": "The connection failed before a response was returned. Check firewall, proxy, or network policy.",
            }

    return {
        "class": "unexpected_runtime_error",
        "message": message,
        "hint": "Inspect the failing row and raw query, then rerun after narrowing the scope or fixing the local environment.",
    }


def slug(text: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", (text or "").strip().lower()).strip("_")
    return value or "item"


def query_tokens(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-\+\.%/]*", (text or "").lower())
    return [t for t in tokens if len(t) > 2 and t not in STOPWORDS and t not in GENERIC_QUERY_TOKENS]


def score_match(query: str, title: str, abstract: str) -> float:
    tokens = query_tokens(query)
    if not tokens:
        return 0.0
    blob = f"{title} {abstract}".lower()
    matched = sum(1 for token in tokens if token in blob)
    title_hits = sum(1 for token in tokens if token in (title or "").lower())
    return matched + 0.5 * title_hits


def rank_results(results: list[SearchResult], max_results: int) -> list[SearchResult]:
    ranked = sorted(
        results,
        key=lambda item: (
            item.local_relevance_score,
            item.published_date or item.year or "",
            item.title,
        ),
        reverse=True,
    )
    # Relevance is a prioritisation signal, not an eligibility filter. Exact-ID
    # verification queries often have zero lexical overlap with their purpose label.
    return ranked[:max_results]


def has_any_term(blob: str, terms: tuple[str, ...]) -> bool:
    lowered = (blob or "").lower()
    return any(term in lowered for term in terms)


def compute_strategy_match_score(row: dict[str, str], result: SearchResult) -> int:
    """Return 0–3 indicating how well a result matches a strategy comparison query.

    This replaces the former hard-filter approach.  No results are deleted;
    instead the score is added as a ranking bonus so that well-matched papers
    rise to the top while marginally-matched papers are preserved for human review.

    Score bands:
      0 — not a strategy query, or no strategy vocabulary in result
      1 — single-side match (continue-only OR stop-only)
      2 — both-side match (continue AND stop vocabulary present)
      3 — both-side match + design vocabulary (target trial, grace period, etc.)
    """
    query_blob = f"{row.get('query', '')} {row.get('source_query', '')}".lower()
    if row.get("query_family") not in STRATEGY_QUERY_FAMILIES:
        return 0
    if not (has_any_term(query_blob, CONTINUE_TERMS) or has_any_term(query_blob, STOP_TERMS)):
        return 0

    blob = f"{result.title} {result.abstract}".lower()
    has_continue = has_any_term(blob, CONTINUE_TERMS)
    has_stop = has_any_term(blob, STOP_TERMS)
    has_design_vocab = has_any_term(blob, DESIGN_STRATEGY_TERMS)

    if has_continue and has_stop:
        return 3 if has_design_vocab else 2
    if has_continue or has_stop:
        return 1
    return 0


def rerank_with_strategy(
    results: list[SearchResult],
    strategy_scores: list[int],
    max_results: int,
) -> tuple[list[SearchResult], list[int]]:
    """Re-rank results by (local_relevance_score + 0.5 * strategy_score), descending.

    Returns the re-ranked results and their corresponding strategy scores,
    both capped at max_results.  All results are preserved before the cap;
    none are deleted.
    """
    paired = list(zip(results, strategy_scores))
    paired.sort(key=lambda x: x[0].local_relevance_score + 0.5 * x[1], reverse=True)
    ranked = paired[:max_results]
    return [r for r, _ in ranked], [s for _, s in ranked]


def reconstruct_openalex_abstract(inverted_index: dict[str, list[int]] | None) -> str:
    if not inverted_index:
        return ""
    words_by_position: dict[int, str] = {}
    for word, positions in inverted_index.items():
        for position in positions:
            words_by_position[position] = word
    return " ".join(words_by_position[pos] for pos in sorted(words_by_position))


def parse_date_limit(limit: str) -> tuple[str, str]:
    value = (limit or "").strip()
    if not value:
        return "", ""
    if "/" in value and "-" in value:
        parts = value.split("-")
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()
    if re.fullmatch(r"\d{4}-\d{4}", value):
        start_year, end_year = value.split("-")
        end_date = f"{end_year}-12-31"
        if int(end_year) >= date.today().year:
            end_date = date.today().isoformat()
        return f"{start_year}-01-01", end_date
    if re.fullmatch(r"\d{4}", value):
        year = int(value)
        end_date = f"{year}-12-31"
        if year >= date.today().year:
            end_date = date.today().isoformat()
        return f"{year}-01-01", end_date
    return "", ""


def month_windows(start_date: str, end_date: str) -> list[tuple[str, str]]:
    if not start_date or not end_date:
        end = date.today()
        start = date(end.year - 1, end.month, 1)
    else:
        start = datetime.strptime(start_date, "%Y-%m-%d").date().replace(day=1)
        end = datetime.strptime(end_date, "%Y-%m-%d").date()

    windows: list[tuple[str, str]] = []
    cursor = date(end.year, end.month, 1)
    while cursor >= start:
        next_month = date(cursor.year + (cursor.month // 12), (cursor.month % 12) + 1, 1)
        last_day = min(end, next_month.fromordinal(next_month.toordinal() - 1))
        first_day = cursor if cursor >= start else start
        windows.append((first_day.isoformat(), last_day.isoformat()))
        if cursor.month == 1:
            cursor = date(cursor.year - 1, 12, 1)
        else:
            cursor = date(cursor.year, cursor.month - 1, 1)
    return windows


def dedupe_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    order: list[str] = []
    best: dict[str, dict[str, str]] = {}
    source_priority = {"PubMed/MEDLINE": 3, "Europe PMC": 2, "Semantic Scholar": 1, "OpenAlex": 0}
    for row in rows:
        doi = (row.get("doi") or "").strip().lower()
        title = normalize_space(row.get("title", "")).lower()
        key = doi or title
        if not key:
            continue
        if key not in best:
            order.append(key)
            best[key] = row
            continue
        current = best[key]
        candidate_score = (len(row.get("abstract", "")), source_priority.get(row.get("source", ""), -1))
        current_score = (len(current.get("abstract", "")), source_priority.get(current.get("source", ""), -1))
        if candidate_score > current_score:
            best[key] = row
    return [best[key] for key in order]


def search_openalex(row: dict[str, str], max_results: int, mailto: str | None, *, insecure_skip_verify: bool = False) -> tuple[list[SearchResult], dict[str, Any]]:
    params = {
        "search": row["query"],
        "per-page": str(min(max_results, 200)),
    }
    start_date, end_date = parse_date_limit(row.get("date_limit", ""))
    filters = []
    if start_date:
        filters.append(f"from_publication_date:{start_date}")
    if end_date:
        filters.append(f"to_publication_date:{end_date}")
    if filters:
        params["filter"] = ",".join(filters)
    if mailto:
        params["mailto"] = mailto
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    payload = http_get_json(url, headers={"User-Agent": USER_AGENT}, insecure_skip_verify=insecure_skip_verify)
    results: list[SearchResult] = []
    for work in payload.get("results", []):
        title = normalize_space(work.get("display_name", ""))
        abstract = reconstruct_openalex_abstract(work.get("abstract_inverted_index"))
        doi = (work.get("doi") or "").replace("https://doi.org/", "")
        primary_location = work.get("primary_location") or {}
        url_value = primary_location.get("landing_page_url") or primary_location.get("pdf_url") or work.get("doi") or work.get("id", "")
        year = str(work.get("publication_year") or "")
        pub_date = work.get("publication_date") or ""
        authors = "; ".join(
            author.get("author", {}).get("display_name", "")
            for author in work.get("authorships", [])
            if author.get("author", {}).get("display_name")
        )
        results.append(
            SearchResult(
                title=title,
                authors=authors,
                year=year,
                published_date=pub_date,
                abstract=abstract,
                doi=doi,
                url=url_value,
                source_record_id=work.get("id", ""),
                publication_status=(
                    "preprint"
                    if work.get("type") == "posted-content"
                    else infer_publication_status(doi, url_value, title)
                ),
                raw=work,
                local_relevance_score=score_match(row["query"], title, abstract),
            )
        )
    return rank_results(results, max_results), payload


def pubmed_esearch(row: dict[str, str], max_results: int, ncbi_api_key: str | None, *, insecure_skip_verify: bool = False) -> dict[str, Any]:
    params = {
        "db": "pubmed",
        "term": row["source_query"] or row["query"],
        "retmode": "json",
        "retmax": str(max_results),
        "sort": "relevance",
        "usehistory": "y",
    }
    start_date, end_date = parse_date_limit(row.get("date_limit", ""))
    if start_date and end_date:
        params["datetype"] = "pdat"
        params["mindate"] = start_date
        params["maxdate"] = end_date
    if ncbi_api_key:
        params["api_key"] = ncbi_api_key
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + urllib.parse.urlencode(params)
    return http_get_json(url, headers={"User-Agent": USER_AGENT}, insecure_skip_verify=insecure_skip_verify)


def pubmed_efetch(id_list: list[str], ncbi_api_key: str | None, *, insecure_skip_verify: bool = False) -> str:
    params = {
        "db": "pubmed",
        "id": ",".join(id_list),
        "retmode": "xml",
    }
    if ncbi_api_key:
        params["api_key"] = ncbi_api_key
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?" + urllib.parse.urlencode(params)
    return http_get_text(url, headers={"User-Agent": USER_AGENT}, insecure_skip_verify=insecure_skip_verify)


def parse_pubmed_articles(xml_text: str, query: str) -> list[SearchResult]:
    root = ET.fromstring(xml_text)
    results: list[SearchResult] = []
    for article in root.findall(".//PubmedArticle"):
        pmid = article.findtext(".//PMID", default="")
        title = normalize_space("".join(article.find(".//ArticleTitle").itertext())) if article.find(".//ArticleTitle") is not None else ""
        abstract = normalize_space(" ".join("".join(node.itertext()) for node in article.findall(".//Abstract/AbstractText")))
        year = (
            article.findtext(".//PubDate/Year")
            or article.findtext(".//ArticleDate/Year")
            or article.findtext(".//DateCompleted/Year")
            or ""
        )
        month = article.findtext(".//ArticleDate/Month", default="01")
        day = article.findtext(".//ArticleDate/Day", default="01")
        pub_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}" if year else ""
        authors = []
        for author in article.findall(".//Author"):
            last = author.findtext("LastName", default="")
            fore = author.findtext("ForeName", default="")
            collective = author.findtext("CollectiveName", default="")
            name = normalize_space(f"{fore} {last}") if (fore or last) else collective
            if name:
                authors.append(name)
        doi = ""
        for article_id in article.findall(".//ArticleId"):
            if article_id.attrib.get("IdType") == "doi":
                doi = normalize_space(article_id.text or "")
                break
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""
        results.append(
            SearchResult(
                title=title,
                authors="; ".join(authors),
                year=year,
                published_date=pub_date,
                abstract=abstract,
                doi=doi,
                url=url,
                source_record_id=pmid,
                publication_status=infer_publication_status(doi, url, title),
                raw={"pmid": pmid, "title": title},
                local_relevance_score=score_match(query, title, abstract),
            )
        )
    return results


def search_pubmed(row: dict[str, str], max_results: int, ncbi_api_key: str | None, *, insecure_skip_verify: bool = False) -> tuple[list[SearchResult], dict[str, Any]]:
    esearch_payload = pubmed_esearch(row, max_results, ncbi_api_key, insecure_skip_verify=insecure_skip_verify)
    id_list = esearch_payload.get("esearchresult", {}).get("idlist", [])
    if not id_list:
        return [], esearch_payload
    xml_text = pubmed_efetch(id_list, ncbi_api_key, insecure_skip_verify=insecure_skip_verify)
    articles = parse_pubmed_articles(xml_text, row["query"])
    return rank_results(articles, max_results), {
        "esearch": esearch_payload,
        "efetch_ids": id_list,
        "efetch_xml": xml_text,
    }


def fetch_preprint_interval(server: str, start_date: str, end_date: str, cursor: int, *, insecure_skip_verify: bool = False) -> dict[str, Any]:
    url = f"https://api.biorxiv.org/details/{server}/{start_date}/{end_date}/{cursor}/json"
    return http_get_json(url, headers={"User-Agent": USER_AGENT}, insecure_skip_verify=insecure_skip_verify)


def search_preprint_source(row: dict[str, str], server: str, max_results: int, scan_cap: int, *, insecure_skip_verify: bool = False) -> tuple[list[SearchResult], dict[str, Any]]:
    start_date, end_date = parse_date_limit(row.get("date_limit", ""))
    windows = month_windows(start_date, end_date)
    harvested = 0
    payload_summary: dict[str, Any] = {
        "windows": [],
        "scan_cap": scan_cap,
        "harvested_records": [],
    }
    collected: list[SearchResult] = []

    for window_start, window_end in windows:
        cursor = 0
        window_info = {"start": window_start, "end": window_end, "pages": 0}
        while harvested < scan_cap:
            payload = fetch_preprint_interval(server, window_start, window_end, cursor, insecure_skip_verify=insecure_skip_verify)
            collection = payload.get("collection", [])
            window_info["pages"] += 1
            if not collection:
                break
            for item in collection:
                harvested += 1
                # Preserve the provider-returned object before local ranking.
                # This is the retrieval truth; the candidate CSV is only a
                # normalized downstream view of these archived objects.
                payload_summary["harvested_records"].append(item)
                title = normalize_space(item.get("title", ""))
                abstract = normalize_space(item.get("abstract", ""))
                score = score_match(row["query"], title, abstract)
                if score <= 0:
                    continue
                doi = normalize_space(item.get("doi", ""))
                preprint_url = f"https://www.{server}.org/content/{doi}v{item.get('version', '1')}" if doi else ""
                collected.append(
                    SearchResult(
                        title=title,
                        authors=normalize_space(item.get("authors", "").replace(";", "; ")),
                        year=(item.get("date", "") or "")[:4],
                        published_date=item.get("date", ""),
                        abstract=abstract,
                        doi=doi,
                        url=preprint_url,
                        source_record_id=doi,
                        publication_status=infer_publication_status(doi, preprint_url, title),
                        raw=item,
                        local_relevance_score=score,
                    )
                )
                if len(collected) >= max_results * 3:
                    break
            if len(collection) < 100 or len(collected) >= max_results * 3 or harvested >= scan_cap:
                break
            cursor += 100
            time.sleep(0.1)
        payload_summary["windows"].append(window_info)
        if len(collected) >= max_results * 3 or harvested >= scan_cap:
            break

    payload_summary["harvested"] = harvested
    payload_summary["locally_matched"] = len(collected)
    return rank_results(collected, max_results), payload_summary


def search_semantic_scholar(
    row: dict[str, str],
    max_results: int,
    ss_api_key: str | None,
    *,
    insecure_skip_verify: bool = False,
) -> tuple[list[SearchResult], dict[str, Any]]:
    """Query Semantic Scholar Graph API.

    Rate limits: 100 requests/5 min without key; add --ss-api-key for higher limits.
    The API does not support date-range filtering on the search endpoint, so date
    limits from the search plan are applied post-hoc by local relevance ranking.
    """
    params = {
        "query": row["query"],
        "limit": str(min(max_results, 100)),
        "fields": "title,abstract,authors,year,publicationDate,externalIds,venue,publicationTypes,openAccessPdf",
    }
    headers = {"User-Agent": USER_AGENT}
    if ss_api_key:
        headers["x-api-key"] = ss_api_key
    url = "https://api.semanticscholar.org/graph/v1/paper/search?" + urllib.parse.urlencode(params)
    payload = http_get_json(url, headers=headers, insecure_skip_verify=insecure_skip_verify)
    results: list[SearchResult] = []
    for paper in payload.get("data", []):
        title = normalize_space(paper.get("title") or "")
        abstract = normalize_space(paper.get("abstract") or "")
        authors = "; ".join(
            a.get("name", "") for a in (paper.get("authors") or []) if a.get("name")
        )
        year = str(paper.get("year") or "")
        pub_date = paper.get("publicationDate") or ""
        ext_ids = paper.get("externalIds") or {}
        doi = normalize_space(ext_ids.get("DOI") or "")
        pmid = ext_ids.get("PubMed") or ""
        paper_id = paper.get("paperId") or ""
        oa_url = (paper.get("openAccessPdf") or {}).get("url") or ""
        url_value = oa_url or (f"https://doi.org/{doi}" if doi else f"https://www.semanticscholar.org/paper/{paper_id}")
        pub_types = paper.get("publicationTypes") or []
        pub_status = "preprint" if "Preprint" in pub_types else infer_publication_status(doi, url_value, title)
        results.append(
            SearchResult(
                title=title,
                authors=authors,
                year=year,
                published_date=pub_date,
                abstract=abstract,
                doi=doi,
                url=url_value,
                source_record_id=paper_id or pmid or doi or "",
                publication_status=pub_status,
                raw=paper,
                local_relevance_score=score_match(row["query"], title, abstract),
            )
        )
    return rank_results(results, max_results), payload


def search_europe_pmc(
    row: dict[str, str],
    max_results: int,
    *,
    insecure_skip_verify: bool = False,
) -> tuple[list[SearchResult], dict[str, Any]]:
    """Query Europe PMC REST API (free, no authentication required).

    Europe PMC covers MEDLINE, PubMed Central, preprints, and some grey literature.
    It provides structured author metadata and full abstractText for many records.
    The source_query field may use Europe PMC field syntax (TITLE: ABSTRACT:) or
    plain text; plain text is used as fallback.
    """
    start_date, end_date = parse_date_limit(row.get("date_limit", ""))
    query = (row.get("source_query") or row["query"]).strip()
    if start_date and end_date:
        query = f"({query}) AND FIRST_PDATE:[{start_date} TO {end_date}]"
    params = {
        "query": query,
        "format": "json",
        "pageSize": str(min(max_results, 100)),
        "resultType": "core",
    }
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urllib.parse.urlencode(params)
    payload = http_get_json(url, headers={"User-Agent": USER_AGENT}, insecure_skip_verify=insecure_skip_verify)
    results: list[SearchResult] = []
    for item in (payload.get("resultList") or {}).get("result", []):
        title = normalize_space(item.get("title") or "")
        abstract = normalize_space(item.get("abstractText") or "")
        doi = normalize_space(item.get("doi") or "")
        pmid = item.get("pmid") or ""
        year = str(item.get("pubYear") or "")
        pub_date = item.get("firstPublicationDate") or ""
        author_list = ((item.get("authorList") or {}).get("author")) or []
        authors = "; ".join(
            normalize_space(f"{a.get('firstName', '')} {a.get('lastName', '')}").strip()
            for a in author_list
            if a.get("lastName")
        )
        source_code = item.get("source") or "MED"
        url_value = (
            f"https://europepmc.org/article/{source_code}/{pmid}"
            if pmid
            else (f"https://doi.org/{doi}" if doi else "")
        )
        results.append(
            SearchResult(
                title=title,
                authors=authors,
                year=year,
                published_date=pub_date,
                abstract=abstract,
                doi=doi,
                url=url_value,
                source_record_id=pmid or doi or item.get("id", ""),
                publication_status=infer_publication_status(doi, url_value, title),
                raw=item,
                local_relevance_score=score_match(row["query"], title, abstract),
            )
        )
    return rank_results(results, max_results), payload


def serialize_result_rows(
    search_row: dict[str, str],
    results: list[SearchResult],
    strategy_scores: list[int] | None = None,
) -> list[dict[str, str]]:
    rows = []
    for rank, result in enumerate(results, start=1):
        s_score = strategy_scores[rank - 1] if strategy_scores else 0
        rows.append(
            {
                "search_id": search_row["search_id"],
                "search_round": search_row["search_round"],
                "query_family": search_row["query_family"],
                "source": search_row["source"],
                "source_rank": str(rank),
                "title": result.title,
                "authors": result.authors,
                "year": result.year,
                "published_date": result.published_date,
                "doi": result.doi,
                "url": result.url,
                "abstract": result.abstract,
                "publication_status": result.publication_status,
                "source_record_id": result.source_record_id,
                "matched_query": search_row["query"],
                "local_relevance_score": f"{result.local_relevance_score:.2f}",
                "strategy_match_score": str(s_score),
            }
        )
    return rows


def api_total_hits(source: str, payload: dict[str, Any], exported: int) -> int:
    """Return the provider-reported hit count without conflating it with export size."""
    try:
        if source == "OpenAlex":
            return int((payload.get("meta") or {}).get("count") or exported)
        if source == "PubMed/MEDLINE":
            return int((((payload.get("esearch") or {}).get("esearchresult") or {}).get("count")) or exported)
        if source == "Europe PMC":
            return int(payload.get("hitCount") or exported)
        if source == "Semantic Scholar":
            return int(payload.get("total") or exported)
        if source in {"medRxiv", "bioRxiv"}:
            return int(payload.get("harvested") or exported)
    except (TypeError, ValueError):
        return exported
    return exported


def raw_payload_filename(row: dict[str, str]) -> str:
    return f"{row['search_id']}_{slug(row['source'])}.json"


def write_raw_payload(
    raw_dir: Path,
    row: dict[str, str],
    payload: dict[str, Any],
    *,
    results: list[SearchResult],
) -> str:
    """Write one self-describing raw payload for one executed ledger row.

    `exported_records` is constructed from the in-memory provider results at
    execution time and retains each original provider object. It must never be
    reconstructed later from candidate_records_raw.csv.
    """
    filename = raw_payload_filename(row)
    exported_records = [
        {
            "source_record_id": result.source_record_id,
            "doi": result.doi,
            "title": result.title,
            "raw_record": result.raw,
        }
        for result in results
    ]
    wrapper = {
        "search_id": row["search_id"],
        "source": row["source"],
        "query_family": row.get("query_family", ""),
        "query": row.get("query", ""),
        "source_query": row.get("source_query", ""),
        "executed_at": datetime.now(UTC).isoformat(),
        "api_total_hits": api_total_hits(row["source"], payload, len(results)),
        "exported_count": len(results),
        "exported_records": exported_records,
        "payload": payload,
    }
    write_json(raw_dir / filename, wrapper)
    return f"raw_results/{filename}"


def update_search_row(
    row: dict[str, str],
    *,
    retrieved: int,
    status: str,
    note: str,
    exported: int | None = None,
    raw_file: str = "",
) -> dict[str, str]:
    updated = dict(row)
    updated["date_searched"] = date.today().isoformat()
    updated["n_retrieved"] = str(retrieved)
    updated["api_total_hits"] = str(retrieved)
    updated["n_exported"] = str(retrieved if exported is None else exported)
    updated["raw_file"] = raw_file
    updated["status"] = status
    existing_note = normalize_space(row.get("note", ""))
    updated["note"] = normalize_space(" ".join(part for part in [existing_note, note] if part))
    return updated


def execute_row(
    row: dict[str, str],
    output_dir: Path,
    max_override: int | None,
    mailto: str | None,
    ncbi_api_key: str | None,
    ss_api_key: str | None,
    preprint_scan_cap: int,
    insecure_skip_verify: bool,
) -> tuple[dict[str, str], list[dict[str, str]]]:
    source = row["source"]
    max_results = max_override or int(row.get("recommended_retrieval_target") or "40")
    raw_dir = output_dir / "raw_results"
    raw_dir.mkdir(parents=True, exist_ok=True)

    if source == "OpenAlex":
        results, payload = search_openalex(row, max_results, mailto, insecure_skip_verify=insecure_skip_verify)
        strategy_scores = [compute_strategy_match_score(row, r) for r in results]
        results, strategy_scores = rerank_with_strategy(results, strategy_scores, max_results)
        raw_file = write_raw_payload(raw_dir, row, payload, results=results)
        return update_search_row(row, retrieved=api_total_hits(source, payload, len(results)), exported=len(results), raw_file=raw_file, status="retrieved", note="queried OpenAlex API"), serialize_result_rows(row, results, strategy_scores)

    if source == "PubMed/MEDLINE":
        results, payload = search_pubmed(row, max_results, ncbi_api_key, insecure_skip_verify=insecure_skip_verify)
        strategy_scores = [compute_strategy_match_score(row, r) for r in results]
        results, strategy_scores = rerank_with_strategy(results, strategy_scores, max_results)
        raw_file = write_raw_payload(raw_dir, row, payload, results=results)
        return update_search_row(row, retrieved=api_total_hits(source, payload, len(results)), exported=len(results), raw_file=raw_file, status="retrieved", note="queried NCBI E-utilities; raw payload includes efetch XML"), serialize_result_rows(row, results, strategy_scores)

    if source == "medRxiv":
        results, payload = search_preprint_source(row, "medrxiv", max_results, preprint_scan_cap, insecure_skip_verify=insecure_skip_verify)
        strategy_scores = [compute_strategy_match_score(row, r) for r in results]
        results, strategy_scores = rerank_with_strategy(results, strategy_scores, max_results)
        raw_file = write_raw_payload(raw_dir, row, payload, results=results)
        note = f"queried official medRxiv interval API and locally ranked matches; scan_cap={preprint_scan_cap}"
        return update_search_row(row, retrieved=api_total_hits(source, payload, len(results)), exported=len(results), raw_file=raw_file, status="retrieved", note=note), serialize_result_rows(row, results, strategy_scores)

    if source == "bioRxiv":
        results, payload = search_preprint_source(row, "biorxiv", max_results, preprint_scan_cap, insecure_skip_verify=insecure_skip_verify)
        strategy_scores = [compute_strategy_match_score(row, r) for r in results]
        results, strategy_scores = rerank_with_strategy(results, strategy_scores, max_results)
        raw_file = write_raw_payload(raw_dir, row, payload, results=results)
        note = f"queried official bioRxiv interval API and locally ranked matches; scan_cap={preprint_scan_cap}"
        return update_search_row(row, retrieved=api_total_hits(source, payload, len(results)), exported=len(results), raw_file=raw_file, status="retrieved", note=note), serialize_result_rows(row, results, strategy_scores)

    if source == "Semantic Scholar":
        results, payload = search_semantic_scholar(row, max_results, ss_api_key, insecure_skip_verify=insecure_skip_verify)
        strategy_scores = [compute_strategy_match_score(row, r) for r in results]
        results, strategy_scores = rerank_with_strategy(results, strategy_scores, max_results)
        raw_file = write_raw_payload(raw_dir, row, payload, results=results)
        key_note = "queried Semantic Scholar Graph API (add --ss-api-key for higher rate limits)"
        return update_search_row(row, retrieved=api_total_hits(source, payload, len(results)), exported=len(results), raw_file=raw_file, status="retrieved", note=key_note), serialize_result_rows(row, results, strategy_scores)

    if source == "Europe PMC":
        results, payload = search_europe_pmc(row, max_results, insecure_skip_verify=insecure_skip_verify)
        strategy_scores = [compute_strategy_match_score(row, r) for r in results]
        results, strategy_scores = rerank_with_strategy(results, strategy_scores, max_results)
        raw_file = write_raw_payload(raw_dir, row, payload, results=results)
        return update_search_row(row, retrieved=api_total_hits(source, payload, len(results)), exported=len(results), raw_file=raw_file, status="retrieved", note="queried Europe PMC REST API"), serialize_result_rows(row, results, strategy_scores)

    if source == "Embase":
        return update_search_row(row, retrieved=0, exported=0, status="blocked_auth_required", note="Embase API access is subscription-gated; export or API key workflow still required"), []

    if source == "Web of Science":
        return update_search_row(row, retrieved=0, exported=0, status="blocked_auth_required", note="Web of Science API access is credential-gated; Starter or Expanded API workflow still required"), []

    return update_search_row(row, retrieved=0, exported=0, status="skipped_unknown_source", note="source not recognized by run_live_search.py"), []


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a live literature search from search_log.csv.")
    parser.add_argument("--search-log", required=True, help="Path to search_log.csv produced by build_search_plan.py")
    parser.add_argument("--output-dir", required=True, help="Directory for updated search_log.csv and candidate records")
    parser.add_argument("--max-per-query", type=int, default=None, help="Override recommended_retrieval_target for all rows")
    parser.add_argument("--mailto", default="", help="Optional email for polite-pool APIs such as OpenAlex")
    parser.add_argument("--ncbi-api-key", default="", help="Optional NCBI API key for PubMed E-utilities")
    parser.add_argument("--ss-api-key", default="", help="Optional Semantic Scholar API key (x-api-key header) for higher rate limits")
    parser.add_argument("--preprint-scan-cap", type=int, default=500, help="Maximum raw interval records to scan per preprint-source query (default 500; use 2000 for broader preprint sweeps)")
    parser.add_argument("--skip-preprints", action="store_true", help="Skip medRxiv and bioRxiv queries entirely (recommended for clinical/pharmacoepi questions where peer-reviewed coverage is adequate)")
    parser.add_argument("--insecure-skip-verify", action="store_true", help="Skip SSL certificate verification when the local environment lacks required root certificates")
    parser.add_argument("--clean-output", action="store_true", help="Remove prior retrieval artifacts in OUTPUT_DIR before execution so stale raw payloads cannot survive")
    parser.add_argument("--append-existing", action="store_true", help="Retain existing candidate/raw artifacts and append only newly planned rows; use with the current output search_log")
    parser.add_argument(
        "--execute-statuses",
        default="planned,refresh_requested",
        help="Comma-separated search_log statuses that should be executed",
    )
    parser.add_argument("--only-query-families", default="", help="Optional comma-separated allowlist of query_family values to execute")
    parser.add_argument("--only-sources", default="", help="Optional comma-separated allowlist of source values to execute")
    args = parser.parse_args()

    search_log_path = Path(args.search_log)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.clean_output:
        raw_dir = output_dir / "raw_results"
        if raw_dir.exists():
            shutil.rmtree(raw_dir)
        for name in ("candidate_records_raw.csv", "candidate_records_dedup.csv", "live_search_diagnostics.json"):
            path = output_dir / name
            if path.exists():
                path.unlink()
    rows = read_csv(search_log_path)

    executable_statuses = {item.strip() for item in args.execute_statuses.split(",") if item.strip()}
    only_query_families = {item.strip() for item in args.only_query_families.split(",") if item.strip()}
    only_sources = {item.strip() for item in args.only_sources.split(",") if item.strip()}
    skip_preprint_sources = {"medRxiv", "bioRxiv"} if args.skip_preprints else set()
    updated_rows: list[dict[str, str]] = []
    candidate_rows: list[dict[str, str]] = []
    if args.append_existing and (output_dir / "candidate_records_raw.csv").exists():
        candidate_rows = read_csv(output_dir / "candidate_records_raw.csv")
        executable_ids = {
            row.get("search_id", "") for row in rows
            if (row.get("status") or "").strip() in executable_statuses
            and (not only_query_families or row.get("query_family") in only_query_families)
            and (not only_sources or row.get("source") in only_sources)
        }
        candidate_rows = [row for row in candidate_rows if row.get("search_id", "") not in executable_ids]
    diagnostics: list[dict[str, str]] = []

    for row in rows:
        status = (row.get("status") or "").strip()
        if status and status not in executable_statuses:
            updated_rows.append(row)
            continue
        if only_query_families and row.get("query_family") not in only_query_families:
            updated_rows.append(row)
            continue
        if only_sources and row.get("source") not in only_sources:
            updated_rows.append(row)
            continue
        if skip_preprint_sources and row.get("source") in skip_preprint_sources:
            updated_rows.append(update_search_row(row, retrieved=0, exported=0, status="skipped_preprints_disabled",
                                                   note="--skip-preprints flag set; preprint sources bypassed"))
            continue
        try:
            updated, candidates = execute_row(
                row,
                output_dir=output_dir,
                max_override=args.max_per_query,
                mailto=args.mailto or None,
                ncbi_api_key=args.ncbi_api_key or None,
                ss_api_key=args.ss_api_key or None,
                preprint_scan_cap=args.preprint_scan_cap,
                insecure_skip_verify=args.insecure_skip_verify,
            )
            updated_rows.append(updated)
            candidate_rows.extend(candidates)
        except Exception as exc:  # pragma: no cover - operational fallback
            diag = classify_exception(exc)
            failed = update_search_row(
                row,
                retrieved=0,
                exported=0,
                status="error",
                note=f"[{diag['class']}] search failed: {diag['message']} next_step: {diag['hint']}",
            )
            updated_rows.append(failed)
            diagnostics.append(
                {
                    "search_id": row.get("search_id", ""),
                    "source": row.get("source", ""),
                    "query_family": row.get("query_family", ""),
                    "error_class": diag["class"],
                    "message": diag["message"],
                    "next_step": diag["hint"],
                }
            )

    deduped_rows = dedupe_rows(candidate_rows)
    dedup_owned_counts: dict[str, int] = defaultdict(int)
    for candidate in deduped_rows:
        dedup_owned_counts[candidate.get("search_id", "")] += 1
    for row in updated_rows:
        row["n_after_dedup"] = str(dedup_owned_counts.get(row.get("search_id", ""), 0))

    fieldnames = list(updated_rows[0].keys()) if updated_rows else []
    if fieldnames:
        write_csv(output_dir / "search_log.csv", updated_rows, fieldnames)

    raw_fieldnames = [
        "search_id",
        "search_round",
        "query_family",
        "source",
        "source_rank",
        "title",
        "authors",
        "year",
        "published_date",
        "doi",
        "url",
        "abstract",
        "publication_status",
        "source_record_id",
        "matched_query",
        "local_relevance_score",
        "strategy_match_score",
    ]
    write_csv(output_dir / "candidate_records_raw.csv", candidate_rows, raw_fieldnames)
    write_csv(output_dir / "candidate_records_dedup.csv", deduped_rows, raw_fieldnames)
    status_counts = defaultdict(int)
    for row in updated_rows:
        status_counts[row.get("status", "")] += 1
    write_json(
        output_dir / "live_search_diagnostics.json",
        {
            "generated_at": datetime.now(UTC).isoformat(),
            "search_log": str(search_log_path),
            "output_dir": str(output_dir),
            "executed_statuses": sorted(executable_statuses),
            "only_query_families": sorted(only_query_families),
            "only_sources": sorted(only_sources),
            "status_counts": dict(status_counts),
            "candidate_row_count": len(candidate_rows),
            "dedup_candidate_row_count": len(deduped_rows),
            "api_total_hits": sum(int(row.get("api_total_hits") or 0) for row in updated_rows),
            "raw_payload_count": len(list((output_dir / "raw_results").glob("*.json"))) if (output_dir / "raw_results").exists() else 0,
            "issues": diagnostics,
        },
    )


if __name__ == "__main__":
    main()
