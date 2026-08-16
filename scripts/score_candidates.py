#!/usr/bin/env python3
"""Prepare a structured scoring brief and CSV template for LLM-driven multi-dimensional scoring.

This script does NOT score papers itself.  It prepares inputs so the LLM can:
  1. Read scoring_prompt.md — a structured, numbered list of papers with abstracts
  2. For each paper, fill in ALL four scoring dimensions (see rubric below)
  3. Write scored_candidates.csv

The four-dimensional schema matches scoring_rubric.md exactly:
  - record_relevance    (0–5)         — Dimension 1: screening-stage relevance
  - study_credibility   (strong / adequate / limited / weak)   — Dimension 2
  - effect_trustworthiness (high / moderate / low / not_applicable) — Dimension 3
  - claim_strength_ceiling (definitive / suggestive / preliminary / background_only) — Dimension 4

Additional judgment fields:
  - likely_directness   (direct / indirect / background)
  - decision_role       (anchor / support / methods / background / exclude)
  - include_in_review   (yes / no / maybe)
  - include_in_anchor_reading (yes / no)

Usage:
    python score_candidates.py \\
        --candidates candidate_records_dedup.csv \\
        --output-dir ./literature_review \\
        [--topic-config topic_config.json] \\
        [--min-abstract-words 10] \\
        [--max-papers 200]

Outputs (in --output-dir):
    scoring_prompt.md              — structured brief for LLM consumption
    scored_candidates_template.csv — blank template; LLM fills the scoring columns
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import textwrap
from pathlib import Path


# ---------------------------------------------------------------------------
# Column schema — must match output_schema.md and scoring_rubric.md
# ---------------------------------------------------------------------------

SCORING_COLUMNS = [
    # Provenance fields (pre-filled by this script)
    "paper_id",
    "title",
    "authors",
    "year",
    "source",
    "doi",
    "url",
    "query_family",
    "publication_status",
    "abstract_snippet",
    # ---- Scoring dimensions (LLM fills these) ----
    # Dimension 1: Record Relevance (0–5)
    "record_relevance",
    # Dimension 2: Study Credibility
    "study_credibility",
    # Dimension 3: Effect Trustworthiness
    "effect_trustworthiness",
    # Dimension 4: Claim Strength Ceiling
    "claim_strength_ceiling",
    # Additional judgment fields
    "likely_directness",
    "decision_role",
    "study_design",
    "key_finding",
    "main_limitation",
    "rationale",
    "include_in_review",
    "include_in_anchor_reading",
]

RECORD_RELEVANCE_RUBRIC = """\
| Score | Meaning |
|---|---|
| 5 | Directly answers the question — population, exposure, comparator, and outcome all match |
| 4 | Strong match on 3 of 4 elements; minor population or outcome drift |
| 3 | Answers a closely related question; useful for measurement, mechanism, or confounder logic |
| 2 | Loosely related; background context or methods signal only |
| 1 | Peripheral; retain only if it fills a specific documented gap |
| 0 | Not relevant — exclude |"""

STUDY_CREDIBILITY_RUBRIC = """\
| Label | Criteria |
|---|---|
| `strong` | Well-executed design; explicit confounder rationale; transparent sample; validated outcome ascertainment; triangulated findings |
| `adequate` | Sound design; adequate confounder handling; some limitations acknowledged; interpretations appropriate for design |
| `limited` | Notable design weakness, convenience sample, or missing confounder detail; useful for context, not for anchoring decisions |
| `weak` | Severe design flaws, unexplained adjustment, or findings that overreach the design; background only or exclude |"""

EFFECT_TRUSTWORTHINESS_RUBRIC = """\
| Label | Criteria |
|---|---|
| `high` | Primary pre-specified analysis; adequate adjustment; time zero clear; interpretable comparator; CI reported; no major bias |
| `moderate` | Informative but one concern: residual confounding, secondary analysis, or preprint status |
| `low` | Notable bias: immortal time, prevalent user bias, confounding by indication, inadequate adjustment |
| `not_applicable` | No quantitative effect estimate (methods paper, narrative review, prevalence-only study) |"""

CLAIM_STRENGTH_RUBRIC = """\
| Label | Allowed narrative language |
|---|---|
| `definitive` | "evidence demonstrates", "studies show" — requires ≥2 high-trustworthiness + strong/adequate credibility, findings triangulated |
| `suggestive` | "evidence suggests", "findings indicate" — requires ≥1 high/moderate trustworthiness; direction consistent |
| `preliminary` | "preliminary evidence suggests", "limited data indicate" — only one study, or low-trustworthiness estimates, or preprints only |
| `background_only` | "has been described", "context indicates" — background or context papers |"""

DIRECTNESS_RUBRIC = """\
| Label | Meaning |
|---|---|
| `direct` | Study directly compares the strategies/exposures of interest in the target population |
| `indirect` | Related population, adjacent exposure, or outcome proxy; supports interpretation but cannot replace direct evidence |
| `background` | Provides context or prevalence data only; not usable as effect evidence |"""

DECISION_ROLE_RUBRIC = """\
| Label | Meaning |
|---|---|
| `anchor` | Highest-quality direct evidence; should organize the primary synthesis argument |
| `support` | Corroborates or extends anchor evidence; useful in synthesis but not standalone |
| `methods` | Primarily a design, measurement, or estimand paper; informs analytic decisions |
| `background` | Provides epidemiological context, prevalence, or burden data only |
| `exclude` | Should be excluded from synthesis (irrelevant, methodologically disqualifying) |"""

THRESHOLD_NOTE = """\
Inclusion thresholds:
- `include_in_review = yes` if record_relevance ≥ 3
- `include_in_anchor_reading = yes` if record_relevance ≥ 4 AND study_credibility in (strong, adequate)
- `decision_role = anchor` only if record_relevance = 5 AND study_credibility = strong/adequate AND effect_trustworthiness = high/moderate"""


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def count_words(text: str) -> int:
    return len((text or "").split())


def truncate_abstract(abstract: str, max_words: int = 80) -> str:
    words = abstract.split()
    if len(words) <= max_words:
        return abstract
    return " ".join(words[:max_words]) + " …"


def load_topic_config(path: Path | None) -> dict:
    if path and path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def build_scoring_prompt(
    papers: list[dict[str, str]],
    cfg: dict,
    min_abstract_words: int,
) -> str:
    topic = cfg.get("topic") or cfg.get("title") or "the research question"
    population = cfg.get("population") or ""
    exposure = cfg.get("exposure") or ""
    outcome = cfg.get("outcome") or ""
    question_type = cfg.get("question_type") or ""

    lines: list[str] = []

    lines += [
        "# Semantic Scoring Brief",
        "",
        "## Your Task",
        "",
        "Read each paper and fill in ALL scoring dimensions in `scored_candidates.csv`.",
        "Do not skip any paper — assign record_relevance = 0 if clearly irrelevant.",
        "Fill every column; use `not_assessed` only for effect_trustworthiness when there is no effect estimate.",
        "",
        "## Research Question",
        "",
        f"**Topic:** {topic}",
    ]
    if population:
        lines.append(f"**Population:** {population}")
    if exposure:
        lines.append(f"**Exposure:** {exposure}")
    if outcome:
        lines.append(f"**Outcome:** {outcome}")
    if question_type:
        lines.append(f"**Question type:** {question_type}")
    lines.append("")

    lines += [
        "---",
        "",
        "## Dimension 1: Record Relevance (0–5)",
        "",
        RECORD_RELEVANCE_RUBRIC,
        "",
        "## Dimension 2: Study Credibility",
        "",
        STUDY_CREDIBILITY_RUBRIC,
        "",
        "## Dimension 3: Effect Trustworthiness",
        "",
        EFFECT_TRUSTWORTHINESS_RUBRIC,
        "",
        "## Dimension 4: Claim Strength Ceiling",
        "",
        CLAIM_STRENGTH_RUBRIC,
        "",
        "## Directness",
        "",
        DIRECTNESS_RUBRIC,
        "",
        "## Decision Role",
        "",
        DECISION_ROLE_RUBRIC,
        "",
        THRESHOLD_NOTE,
        "",
        "---",
        "",
        "## Mandatory Red Flags",
        "",
        "These cap scores regardless of other strengths:",
        "- No clear exposure or outcome definition → cap `record_relevance` at 2",
        "- Severe overclaiming beyond what design supports → cap `study_credibility` at `limited`",
        "- OR interpreted as RR/PR with common outcome (>10%) → cap `effect_trustworthiness` at `low`",
        "- Adjustment for likely mediator/collider without justification → cap `effect_trustworthiness` at `low`",
        "- Preprint: cap `effect_trustworthiness` at `moderate` maximum",
        "",
        "---",
        "",
        f"## Papers to Score (N={len(papers)})",
        "",
    ]

    sparse_abstract_count = 0
    for i, row in enumerate(papers, start=1):
        abstract = normalize_space(row.get("abstract") or "")
        if count_words(abstract) < min_abstract_words:
            sparse_abstract_count += 1

        paper_id = row.get("paper_id") or f"P{i:03d}"
        title = normalize_space(row.get("title") or "(no title)")
        year = row.get("year") or "?"
        source = row.get("source") or "?"
        doi = row.get("doi") or ""
        authors_raw = normalize_space(row.get("authors") or "")
        first_author = authors_raw.split(";")[0].strip() if authors_raw else "?"
        qfam = row.get("query_family") or ""
        pub_status = row.get("publication_status") or ""
        abstract_snippet = truncate_abstract(abstract, max_words=80)

        lines += [
            f"### {paper_id}: {title}",
            "",
            f"**Year:** {year} | **Source:** {source} | **First author:** {first_author}",
        ]
        if doi:
            lines.append(f"**DOI:** {doi}")
        if qfam:
            lines.append(f"**Query family:** `{qfam}`")
        if pub_status:
            lines.append(f"**Publication status:** {pub_status}")
        lines.append("")
        if abstract_snippet:
            lines.append(f"**Abstract:** {abstract_snippet}")
        else:
            lines.append("**Abstract:** *(not available — score from title and query family context)*")
        lines.append("")
        lines += [
            "**Fill these fields in scored_candidates.csv:**",
            "- `record_relevance` (0–5): ",
            "- `study_credibility` (strong/adequate/limited/weak): ",
            "- `effect_trustworthiness` (high/moderate/low/not_applicable): ",
            "- `claim_strength_ceiling` (definitive/suggestive/preliminary/background_only): ",
            "- `likely_directness` (direct/indirect/background): ",
            "- `decision_role` (anchor/support/methods/background/exclude): ",
            "- `study_design`: ",
            "- `key_finding`: ",
            "- `main_limitation`: ",
            "- `rationale`: ",
            "- `include_in_review` (yes/no/maybe): ",
            "- `include_in_anchor_reading` (yes/no): ",
            "",
            "---",
            "",
        ]

    if sparse_abstract_count > 0:
        lines.insert(
            next(i for i, l in enumerate(lines) if "Papers to Score" in l) + 2,
            f"\n> **Note:** {sparse_abstract_count} paper(s) have sparse abstracts (<{min_abstract_words} words). "
            "Score from title and query_family context; assign record_relevance ≤ 3 unless the title is a clear match.\n",
        )

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare LLM scoring brief and CSV template from deduplicated candidates.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            After running:
              1. Read scoring_prompt.md
              2. For each paper fill in all scoring dimensions
              3. Save as scored_candidates.csv (replacing the template)
        """),
    )
    parser.add_argument("--candidates", required=True, help="Path to candidate_records_dedup.csv")
    parser.add_argument("--output-dir", required=True, help="Directory to write scoring_prompt.md and scored_candidates_template.csv")
    parser.add_argument("--topic-config", default="", help="Optional path to topic_config.json for research question context")
    parser.add_argument("--min-abstract-words", type=int, default=10, help="Flag papers with fewer abstract words (default: 10)")
    parser.add_argument("--max-papers", type=int, default=300, help="Maximum papers to include in the scoring prompt (default: 300)")
    args = parser.parse_args()

    candidates_path = Path(args.candidates)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    topic_config_path = Path(args.topic_config) if args.topic_config else None
    cfg = load_topic_config(topic_config_path)

    rows = read_csv(candidates_path)
    if not rows:
        print(f"[score_candidates] No records found in {candidates_path}")
        return

    # Assign sequential paper IDs
    for i, row in enumerate(rows, start=1):
        row["paper_id"] = f"P{i:03d}"

    # Sort by local_relevance_score descending, cap at max-papers
    try:
        rows_sorted = sorted(rows, key=lambda r: float(r.get("local_relevance_score") or 0), reverse=True)
    except Exception:
        rows_sorted = rows
    rows_to_score = rows_sorted[: args.max_papers]

    print(f"[score_candidates] {len(rows)} candidates → scoring {len(rows_to_score)}")

    # Write scoring_prompt.md
    prompt_md = build_scoring_prompt(rows_to_score, cfg, args.min_abstract_words)
    prompt_path = output_dir / "scoring_prompt.md"
    prompt_path.write_text(prompt_md, encoding="utf-8")
    print(f"[score_candidates] Wrote {prompt_path}")

    # Write scored_candidates_template.csv (blank scoring columns)
    template_rows = []
    for row in rows_to_score:
        template_rows.append(
            {
                "paper_id": row.get("paper_id", ""),
                "title": normalize_space(row.get("title") or ""),
                "authors": normalize_space(row.get("authors") or ""),
                "year": row.get("year") or "",
                "source": row.get("source") or "",
                "doi": row.get("doi") or "",
                "url": row.get("url") or "",
                "query_family": row.get("query_family") or "",
                "publication_status": row.get("publication_status") or "",
                "abstract_snippet": truncate_abstract(normalize_space(row.get("abstract") or ""), max_words=60),
                # Blank scoring fields
                "record_relevance": "",
                "study_credibility": "",
                "effect_trustworthiness": "",
                "claim_strength_ceiling": "",
                "likely_directness": "",
                "decision_role": "",
                "study_design": "",
                "key_finding": "",
                "main_limitation": "",
                "rationale": "",
                "include_in_review": "",
                "include_in_anchor_reading": "",
            }
        )

    template_path = output_dir / "scored_candidates_template.csv"
    write_csv(template_path, template_rows, SCORING_COLUMNS)
    print(f"[score_candidates] Wrote template → {template_path}")
    print()
    print("Next: read scoring_prompt.md, fill scoring columns, save as scored_candidates.csv.")


if __name__ == "__main__":
    main()
