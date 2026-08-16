#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from datetime import date, datetime
import hashlib
import json
import shutil
import subprocess
import sys
import unicodedata
import zipfile
from pathlib import Path
import re


THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from common_validation import (  # type: ignore  # noqa: E402
    body_word_count,
    check_inline_screening_numbers,
    check_prohibited_in_body,
    extract_section,
    load_text,
)
from validate_review_semantics import validate_semantics  # noqa: E402


REQUIRED_FILES = [
    "search_log.csv",
    "candidate_records_raw.csv",
    "candidate_records_dedup.csv",
    "screening_decisions.csv",
    "study_registry.csv",
    "measurement_registry.csv",
    "confounder_registry.csv",
    "citation_registry.json",
    "evidence_to_decision_table.csv",
    "evidence_sufficiency_report.json",
    "review_contract.json",
    "protocol_inputs.json",
    "proposal_bridge.md",
]

FULL_PACKAGE_FILES = [
    "publication_manifest.json",
    "references.bib",
    "citation_verification_report.csv",
    "citation_verification_summary.md",
    "literature_review.docx",
    "literature_review.pdf",
    "literature_review.tex",
]

CORE_SOURCES = [
    "OpenAlex",
    "PubMed/MEDLINE",
    "Semantic Scholar",
    "Europe PMC",
    "medRxiv",
    "bioRxiv",
    "Embase",
    "Web of Science",
]

# Free-access sources that must appear (or be logged as unavailable) in every completed review
REQUIRED_FREE_SOURCES = {
    "OpenAlex",
    "PubMed/MEDLINE",
    "Semantic Scholar",
    "Europe PMC",
    "medRxiv",
    "bioRxiv",
}

ALLOWED_NARRATIVE_ROLES = {
    "anchor",
    "background",
    "methods_justification",
    "mechanism",
    "direct_evidence",
    "supporting_evidence",
    "measurement",
    "confounding",
    "gap",
    "discussion",
}
ALLOWED_REVIEW_TYPES = {"structured_narrative", "systematic_no_meta", "systematic_meta"}
COMPLETED_STATUSES = {"ready", "released", "complete", "completed"}
EXECUTED_SEARCH_STATUSES = {"retrieved", "completed", "complete", "success", "executed"}
PLACEHOLDER_PATTERNS = [
    r"\bexposure\s+and\s+outcome\b",
    r"\bstudy topic\b",
    r"\b(?:todo|tbd|fill in)\b",
    r"\{\{[^}]+\}\}",
    r"\[[^\]]*(?:insert|specify|set)[^\]]*\]",
]

# Enum constraints — shared with build_review_scaffold.py and output_schema.md
ALLOWED_STRENGTH_VALUES = {"definitive", "suggestive", "preliminary", "background_only"}
STUDY_CREDIBILITY_VALUES = {"strong", "adequate", "limited", "weak"}
EFFECT_TRUSTWORTHINESS_VALUES = {"high", "moderate", "low", "not_applicable"}
LIKELY_DIRECTNESS_VALUES = {"direct", "indirect", "background"}
DECISION_ROLE_VALUES = {"anchor", "support", "methods", "background", "exclude"}
EVIDENCE_DIRECTION_VALUES = {
    "favorable", "harmful", "null", "mixed", "heterogeneous", "insufficient", "unclear",
}
EFFECT_ROW_DIRECTION_VALUES = {"favorable", "harmful", "null", "mixed", "unclear"}
BIAS_DOMAIN_VALUES_PHARMACOEPI = {
    "confounding_by_indication", "confounding_by_prognosis", "immortal_time_bias",
    "prevalent_user_bias", "time_zero_alignment", "informative_censoring",
    "outcome_misclassification", "exposure_misclassification", "reverse_causation",
    "selection_bias", "loss_to_followup", "overadjustment",
}
BIAS_SEVERITY_VALUES = {"high", "moderate", "low", "none_detected", "unclear"}
BIAS_DIRECTION_VALUES = {"towards_null", "away_from_null", "uncertain", "not_applicable"}

# Methods completeness: narrative should mention these concepts in the Search and Screening section
METHODS_COMPLETENESS_PATTERNS = [
    (r"search(?:ed|ing)?\s+(?:the\s+)?(?:database|pubmed|openalex|semantic scholar|europe pmc|medline)", "database search"),
    (r"\d{4}\s*(?:to|through|–|-)\s*\d{4}", "date range"),
    (r"(?:inclus|exclus)ion\s+criteri", "inclusion/exclusion criteria"),
    (r"\d+\s+(?:study|studies|articles|records|papers)\s+(?:was\s+|were\s+)?(?:included|retained|screened)", "PRISMA-style count"),
]

REVIEW_CONTRACT_FIELDS = [
    "contract_version",
    "review_type",
    "reporting_framework",
    "synthesis_method",
    "project_mode",
    "question_type",
    "review_goal",
    "design_type",
    "generated_at",
    "status",
    "downgrade_state",
    "topic",
    "primary_estimand",
    "evidence_sufficiency",
    "decision_ids",
    "citation_ids",
]
CANONICAL_PROJECT_MODES = {"research", "applied_methods", "workflow_methods"}

TREATMENT_STRATEGY_REVIEW_CONTRACT_FIELDS = [
    "deliverable_style",
    "narrative_readiness",
    "anchor_density_by_outcome",
]

SUFFICIENCY_FIELDS = [
    "evidence_density",
    "design_fit",
    "causal_temporality_risk",
    "estimand_feasibility",
    "interpretation_risk",
    "mode_recommendation",
]

PROHIBITED_BODY_PHRASES = [
    "skill-chain",
    "Codex",
    "workflow validation",
    "this review supports",
    "to support protocol development",
    "this review was designed to support",
    "Example 1",
    "applied-methods validation",
    "review_briefing.md",
    "study_registry.csv",
    "claim_registry.csv",
    "effect_registry.csv",
    "anchor_eligible",
    "narrative_readiness",
    "core_direct_strict",
    "core_direct_broad",
    "appendix_only",
    "background_policy",
    "screening architecture",
    "package logic",
    "candidate pool",
]

# Overclaim phrases: these trigger warnings, not hard failures.
# Each phrase suggests language stronger than "suggestive" and requires
# a corresponding claim_registry.csv entry with allowed_strength = definitive.
OVERCLAIM_WARNING_PHRASES = [
    "demonstrates",
    "proves",
    "establishes that",
    "confirms that",
    "clearly shows",
    "definitively",
    "causally linked",
    " causes ",
    "leads to",
]

META_LANGUAGE_PATTERNS = [
    r"\bthis workflow\b",
    r"\bthe workflow\b",
    r"\bthis pipeline\b",
    r"\bthe pipeline\b",
    r"\bthis upgrade\b",
    r"\bv2\.1\b",
    r"\bthe system is\b",
    r"\bthis system\b",
]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def read_csv_rows_if_exists(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    return read_csv_rows(path)


def require_columns(rows: list[dict[str, str]], required: list[str], label: str, *, allow_empty: bool = False) -> list[str]:
    if not rows:
        return [] if allow_empty else [f"{label} is empty"]
    present = set(rows[0].keys())
    missing = [column for column in required if column not in present]
    return [f"{label} missing columns: {', '.join(missing)}"] if missing else []


def check_overclaim_phrases(text: str, phrases: list[str]) -> list[str]:
    """Return phrases found in the text body (case-insensitive).

    These are reported as warnings rather than hard failures because:
    - they may appear inside direct quotations of cited papers
    - they may appear in the background section where causal language
      is contextually appropriate
    - regex matching cannot distinguish those cases from true overclaims

    The human reviewer should check each flagged phrase and either adjust
    the prose or confirm that the corresponding claim_registry.csv entry
    has allowed_strength = definitive.
    """
    found: list[str] = []
    for phrase in phrases:
        pattern = re.compile(rf"(?<![A-Za-z]){re.escape(phrase.lower())}(?![A-Za-z])")
        if pattern.search(text.lower()):
            found.append(phrase)
    return found


def check_meta_language(text: str, patterns: list[str]) -> list[str]:
    lowered = text.lower()
    found: list[str] = []
    for pattern in patterns:
        if re.search(pattern, lowered):
            found.append(pattern)
    return found


def check_methods_completeness(text: str) -> list[str]:
    """Return method concepts that are missing from the narrative body."""
    missing = []
    for pattern, label in METHODS_COMPLETENESS_PATTERNS:
        if not re.search(pattern, text, re.IGNORECASE):
            missing.append(label)
    return missing


def is_placeholder(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return True
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in PLACEHOLDER_PATTERNS)


def truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def sparse_exception(contract: dict) -> tuple[bool, str]:
    exception = contract.get("sparse_evidence_exception")
    if not isinstance(exception, dict) or not truthy(exception.get("applies")):
        return False, ""
    required = ["rationale", "search_saturation", "scope_boundary"]
    missing = [field for field in required if is_placeholder(str(exception.get(field, "")))]
    if missing:
        return False, "sparse_evidence_exception is incomplete: " + ", ".join(missing)
    return True, ""


def check_review_type_route(contract: dict) -> list[str]:
    errors: list[str] = []
    review_type = str(contract.get("review_type", "")).strip()
    frameworks_raw = contract.get("reporting_framework", [])
    if isinstance(frameworks_raw, str):
        frameworks = {part.strip().lower() for part in re.split(r"[,;|]", frameworks_raw) if part.strip()}
    else:
        frameworks = {str(part).strip().lower() for part in frameworks_raw if str(part).strip()}
    synthesis = str(contract.get("synthesis_method", "")).strip().lower()
    if review_type not in ALLOWED_REVIEW_TYPES:
        return [f"review_contract.json review_type must be one of {sorted(ALLOWED_REVIEW_TYPES)}; got {review_type!r}"]
    if is_placeholder(synthesis):
        errors.append("review_contract.json synthesis_method must be explicit and non-placeholder")
    if review_type == "structured_narrative" and not any("sanra" in item for item in frameworks):
        errors.append("structured_narrative must declare SANRA as its narrative-quality framework")
    if review_type == "systematic_no_meta":
        if not any("prisma" in item for item in frameworks):
            errors.append("systematic_no_meta must declare PRISMA/PRISMA-S")
        if not any("swim" in item for item in frameworks):
            errors.append("systematic_no_meta must declare SWiM")
        if "vote count" in synthesis and "direction" not in synthesis:
            errors.append("systematic_no_meta may not use unsafeguarded vote counting")
    if review_type == "systematic_meta":
        if not any("prisma" in item for item in frameworks):
            errors.append("systematic_meta must declare PRISMA/PRISMA-S")
        if not re.search(r"meta|random.effects|fixed.effect|quantitative", synthesis):
            errors.append("systematic_meta must name a quantitative/meta-analytic synthesis method")
    return errors


def check_search_execution(search_log: list[dict[str, str]], completed: bool) -> list[str]:
    if not completed:
        return []
    errors: list[str] = []
    for index, row in enumerate(search_log, start=2):
        status = (row.get("status") or "").strip().lower()
        if status not in EXECUTED_SEARCH_STATUSES:
            continue
        source_query = row.get("source_query") or row.get("query") or ""
        if is_placeholder(source_query) or len(source_query.strip()) < 12:
            errors.append(f"search_log.csv row {index} has an executed but placeholder/underspecified source_query")
        if is_placeholder(row.get("date_searched") or ""):
            errors.append(f"search_log.csv row {index} has no real date_searched")
        for field in ("n_retrieved", "n_after_dedup"):
            raw = (row.get(field) or "").strip()
            if not raw.isdigit():
                errors.append(f"search_log.csv row {index} executed search lacks integer {field}")
        if (row.get("n_retrieved") or "").isdigit() and (row.get("n_after_dedup") or "").isdigit():
            if int(row["n_after_dedup"]) > int(row["n_retrieved"]):
                errors.append(f"search_log.csv row {index} has n_after_dedup greater than n_retrieved")
    executed = [row for row in search_log if (row.get("status") or "").strip().lower() in EXECUTED_SEARCH_STATUSES]
    if not executed:
        errors.append("completed review has no executed search rows")
    return errors


def check_search_freshness(search_log: list[dict[str, str]], contract: dict, completed: bool) -> list[str]:
    if not completed:
        return []
    dates: list[date] = []
    for row in search_log:
        if (row.get("status") or "").strip().lower() not in EXECUTED_SEARCH_STATUSES:
            continue
        try:
            dates.append(datetime.strptime((row.get("date_searched") or "").strip(), "%Y-%m-%d").date())
        except ValueError:
            continue
    if not dates:
        return ["completed review has no parseable executed search date"]
    age = (date.today() - max(dates)).days
    if age > 183 and not truthy(contract.get("older_search_cutoff_disclosed")):
        return [f"latest executed search is {age} days old; refresh it or set older_search_cutoff_disclosed=true with a rationale"]
    return []


def check_search_strategy_document(text: str, completed: bool) -> list[str]:
    if not completed:
        return []
    if not text.strip():
        return ["completed review requires non-empty search_strategy.md"]
    errors: list[str] = []
    if re.search(r"\b(?:TODO|TBD|FILL IN)\b|\{\{[^}]+\}\}", text, re.IGNORECASE):
        errors.append("search_strategy.md contains unresolved placeholder text")
    if not re.search(r"\b(?:PubMed|MEDLINE|OpenAlex|Europe PMC|Embase|Web of Science)\b", text, re.IGNORECASE):
        errors.append("search_strategy.md does not name a searched bibliographic source")
    if not re.search(r"\b\d{4}-\d{2}-\d{2}\b", text):
        errors.append("search_strategy.md does not report an exact search date")
    if not re.search(r"\b(?:retrieved|yield|records?)\b.{0,40}\b\d+\b|\b\d+\b.{0,40}\b(?:retrieved|yield|records?)\b", text, re.IGNORECASE):
        errors.append("search_strategy.md does not report a numeric retrieval yield")
    return errors


def check_screening_accounting(
    screening: list[dict[str, str]],
    completed: bool,
    sparse_ok: bool,
) -> list[str]:
    if not completed:
        return []
    errors: list[str] = []
    seen_ids: set[str] = set()
    for index, row in enumerate(screening, start=2):
        paper_id = (row.get("paper_id") or "").strip()
        if not paper_id:
            errors.append(f"screening_decisions.csv row {index} lacks paper_id")
        elif paper_id in seen_ids:
            errors.append(f"screening_decisions.csv has duplicate paper_id {paper_id!r}")
        seen_ids.add(paper_id)
        decision = (row.get("decision") or "").strip().lower()
        stage = (row.get("screening_stage") or "").strip().lower()
        reason = (row.get("reason") or "").strip()
        if decision in {"exclude", "excluded"} and (is_placeholder(reason) or len(reason) < 15):
            errors.append(f"screening_decisions.csv row {index} exclusion lacks a specific reason")
        is_full_text = "full" in stage or (row.get("access_type") or "").strip().lower() == "full_text"
        if is_full_text and decision in {"exclude", "excluded"}:
            code = (row.get("exclusion_reason_code") or "").strip()
            if is_placeholder(code):
                errors.append(f"screening_decisions.csv row {index} full-text exclusion lacks exclusion_reason_code")
    fulltext_exclusions = [
        row for row in screening
        if ("full" in (row.get("screening_stage") or "").lower()
            or (row.get("access_type") or "").strip().lower() == "full_text")
        and (row.get("decision") or "").strip().lower() in {"exclude", "excluded"}
    ]
    if len(screening) >= 10 and not fulltext_exclusions and not sparse_ok:
        errors.append("mature completed review has no recorded full-text exclusions; document exclusions or justify a sparse-evidence exception")
    return errors


def check_quality_appraisal(
    appraisal: list[dict[str, str]],
    included_ids: set[str],
    completed: bool,
    design_by_paper: dict[str, str] | None = None,
) -> list[str]:
    if not completed:
        return []
    errors: list[str] = []
    if not appraisal:
        return ["completed review requires non-empty quality_appraisal_registry.csv"]
    rows_by_paper: dict[str, list[dict[str, str]]] = defaultdict(list)
    signatures: Counter[tuple[str, str, str]] = Counter()
    for index, row in enumerate(appraisal, start=2):
        paper_id = (row.get("paper_id") or "").strip()
        rows_by_paper[paper_id].append(row)
        for field in ("domain", "judgment", "raw_signal", "evidence_source"):
            if is_placeholder(row.get(field) or ""):
                errors.append(f"quality_appraisal_registry.csv row {index} has blank/template {field}")
        signatures[(row.get("judgment", ""), row.get("raw_signal", ""), row.get("note", ""))] += 1
    missing = sorted(included_ids - set(rows_by_paper))
    if missing:
        errors.append("included claim-bearing studies lack quality appraisal: " + ", ".join(missing))
    for paper_id in sorted(included_ids & set(rows_by_paper)):
        domains = {(row.get("domain") or "").strip().lower() for row in rows_by_paper[paper_id] if (row.get("domain") or "").strip()}
        if len(domains) < 4:
            errors.append(f"quality appraisal for {paper_id} covers only {len(domains)} domains; at least 4 design-appropriate domains are required")
        design = (design_by_paper or {}).get(paper_id, "").lower()
        domain_text = " ".join(domains)
        required_concepts: list[tuple[str, tuple[str, ...]]] = []
        if "cross" in design:
            required_concepts = [
                ("selection", ("selection", "sampling")),
                ("measurement", ("measurement", "misclassification", "validity")),
                ("confounding", ("confound", "adjustment", "overadjust")),
                ("reverse causation/temporality", ("reverse", "temporality")),
            ]
        elif any(token in design for token in ("cohort", "prospective", "longitudinal")):
            required_concepts = [
                ("selection/attrition", ("selection", "attrition", "loss")),
                ("measurement", ("measurement", "misclassification", "validity")),
                ("confounding", ("confound", "adjustment", "overadjust")),
                ("temporality/time zero", ("temporality", "time zero", "baseline")),
            ]
        elif any(token in design for token in ("systematic review", "meta-analysis", "umbrella")):
            required_concepts = [
                ("search/screening", ("search", "screen")),
                ("risk of bias", ("risk of bias", "appraisal")),
                ("synthesis", ("synthesis", "meta-analysis", "pooling")),
                ("heterogeneity/reporting bias", ("heterogeneity", "publication", "reporting bias")),
            ]
        missing_concepts = [
            label for label, aliases in required_concepts
            if not any(alias in domain_text for alias in aliases)
        ]
        if missing_concepts:
            errors.append(f"quality appraisal for {paper_id} ({design}) lacks design-appropriate domains: {', '.join(missing_concepts)}")
    if len(appraisal) >= 8 and signatures and signatures.most_common(1)[0][1] / len(appraisal) > 0.60:
        errors.append("quality appraisal is predominantly repeated template text rather than study-specific evidence")
    return errors


def check_depth_and_reference_floor(
    contract: dict,
    citations: list[dict],
    fulltexts: list[dict[str, str]],
    completed: bool,
) -> list[str]:
    if not completed:
        return []
    preset = str(contract.get("delivery_preset", "decision_grade"))
    if preset not in {"decision_grade", "full_package"}:
        return []
    sparse_ok, sparse_error = sparse_exception(contract)
    errors = [sparse_error] if sparse_error else []
    verified_count = sum(
        1 for entry in citations
        if truthy(entry.get("verified"))
        or str(entry.get("verification_status", "")).strip().lower() == "verified"
        or entry.get("doi") or entry.get("pmid")
    )
    deep_read_ids = {
        (row.get("paper_id") or "").strip()
        for row in fulltexts
        if (truthy(row.get("deep_read_completed"))
            or (row.get("fulltext_status") or "").strip().lower() in {"deep_read", "deep_read_completed", "full_text_reviewed", "completed"})
        and (row.get("paper_id") or "").strip()
    }
    if not sparse_ok and verified_count < 30:
        errors.append(f"{preset} mature-topic review requires at least 30 verified/identity-resolved references; found {verified_count}")
    if not sparse_ok and len(deep_read_ids) < 12:
        errors.append(f"{preset} review requires at least 12 documented deep-read studies; found {len(deep_read_ids)}")
    return errors


def check_effect_coverage(
    studies: list[dict[str, str]],
    effects: list[dict[str, str]],
    completed: bool,
) -> list[str]:
    if not completed:
        return []
    direct_ids = {
        (row.get("paper_id") or "").strip()
        for row in studies
        if (row.get("primary_role") or "").strip().lower() in {"anchor", "direct_evidence", "counterevidence"}
        and (row.get("paper_id") or "").strip()
    }
    if not direct_ids:
        return ["completed review has no direct/counterevidence studies identified in study_registry.csv"]
    complete_ids: set[str] = set()
    for row in effects:
        paper_id = (row.get("paper_id") or row.get("study_id") or "").strip()
        estimate = (row.get("point_estimate") or "").strip()
        lower = (row.get("ci_lower") or "").strip()
        upper = (row.get("ci_upper") or "").strip()
        if paper_id and estimate and ((lower and upper) or estimate.lower() in {"nr", "not reported"}):
            complete_ids.add(paper_id)
    coverage = len(direct_ids & complete_ids) / len(direct_ids)
    if coverage < 0.80:
        return [f"effect_registry.csv has complete estimate/interval or explicit NR for only {coverage:.0%} of direct/counterevidence studies; require at least 80%"]
    return []


def markdown_table_data_rows(section: str) -> int:
    rows = []
    for line in section.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        if re.fullmatch(r"\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?", stripped):
            continue
        rows.append(stripped)
    return max(0, len(rows) - 1)


def check_embedded_evidence_tables(text: str) -> list[str]:
    errors: list[str] = []
    for heading, minimum in (("Evidence Map and Study Characteristics", 3), ("Effect Evidence Matrix", 3)):
        section = extract_section(text, heading)
        if not section:
            errors.append(f"literature_review_synthesis.md lacks required main-body section: {heading}")
        elif markdown_table_data_rows(section) < minimum:
            errors.append(f"{heading} must contain at least {minimum} populated study rows in the main body")
        elif is_placeholder(section):
            errors.append(f"{heading} still contains placeholder content")
    return errors


def reconcile_screening_counts(
    text: str,
    candidate_raw: list[dict[str, str]],
    candidate_dedup: list[dict[str, str]],
    screening: list[dict[str, str]],
) -> list[str]:
    """Hard-check reader-facing screening counts against registry truth."""
    section = extract_section(text, "Search and Screening")
    patterns = {
        "retrieved": r"\b(\d+)\s+(?:records?|articles?|papers?)\s+(?:was\s+|were\s+)?retrieved\b",
        "deduplicated": r"\b(\d+)\s+(?:records?|articles?|papers?)\s+(?:remained\s+)?after\s+deduplication\b",
        "screened": r"\b(\d+)\s+(?:content\s+sources?|reports?|items?)\s+(?:was\s+|were\s+)?assessed\b",
        "included": r"\b(\d+)\s+(?:study|studies|articles?|papers?|sources?)\s+(?:was\s+|were\s+)?(?:retained(?:\s+and\s+included)?|included)\b",
    }
    reported: dict[str, int] = {}
    errors: list[str] = []
    for label, pattern in patterns.items():
        match = re.search(pattern, section, re.IGNORECASE)
        if not match:
            errors.append(f"Search and Screening section is missing a parseable {label} count")
        else:
            reported[label] = int(match.group(1))
    if errors:
        return errors
    content_rows = [
        row for row in screening
        if truthy(row.get("content_assessed"))
    ]
    expected = {
        "retrieved": len(candidate_raw),
        "deduplicated": len(candidate_dedup),
        "screened": len(content_rows),
        "included": sum(
            1
            for row in screening
            if (row.get("include_in_synthesis") or "").strip().lower() in {"yes", "true", "1"}
            or (row.get("decision") or "").strip().lower() == "include"
        ),
    }
    for label, value in expected.items():
        if reported[label] != value:
            errors.append(
                f"Search and Screening {label} count {reported[label]} does not match registry count {value}"
            )
    return errors


def check_enum_values(
    rows: list[dict[str, str]],
    column: str,
    allowed: set[str],
    label: str,
    *,
    allow_empty: bool = True,
) -> list[str]:
    """Return errors for any row where `column` contains an unrecognised value."""
    errors = []
    for i, row in enumerate(rows, start=2):  # row 1 is header
        val = (row.get(column) or "").strip()
        if not val:
            continue  # blank is acceptable during active filling
        if val not in allowed:
            errors.append(
                f"{label} row {i}: invalid {column}={val!r}; allowed: {sorted(allowed)}"
            )
    return errors


def check_claim_evidence_binding(
    claim_registry: list[dict[str, str]],
    effect_registry: list[dict[str, str]],
    label: str,
) -> list[str]:
    """Warn when a primary claim has no supporting_evidence_row_ids bound to effect_registry."""
    if not claim_registry or not effect_registry:
        return []
    effect_ids = {
        (row.get("effect_id") or row.get("paper_id") or "").strip()
        for row in effect_registry
        if (row.get("effect_id") or row.get("paper_id") or "").strip()
    }
    errors = []
    for row in claim_registry:
        if (row.get("supports_primary_direction_claim") or "").strip().lower() != "yes":
            continue
        row_ids = [
            r.strip()
            for r in (row.get("supporting_evidence_row_ids") or "").split(",")
            if r.strip()
        ]
        if not row_ids:
            errors.append(
                f"{label} claim {row.get('claim_id', '?')}: primary claim has no supporting_evidence_row_ids; "
                "bind at least one effect_registry row"
            )
        else:
            missing_ids = [r for r in row_ids if r not in effect_ids]
            if missing_ids:
                errors.append(
                    f"{label} claim {row.get('claim_id', '?')}: supporting_evidence_row_ids "
                    f"{missing_ids} not found in effect_registry (effect_id column)"
                )
    return errors


def check_direction_consistency(
    claim_registry: list[dict[str, str]],
    effect_registry: list[dict[str, str]],
) -> list[str]:
    """Warn when a primary claim's evidence_direction contradicts directions in effect_registry.

    Uses the optional `direction` column added to effect_registry.csv.
    Only checks primary claims (supports_primary_direction_claim=yes) with
    evidence_direction explicitly set to harmful or favorable.
    """
    if not claim_registry or not effect_registry:
        return []

    CONTRADICTIONS = {
        "harmful": "favorable",
        "favorable": "harmful",
    }

    # Build paper_id → set of effect directions from effect_registry
    effect_directions_by_paper: dict[str, set[str]] = {}
    for row in effect_registry:
        pid = (row.get("paper_id") or "").strip()
        direction = (row.get("direction") or "").strip().lower()
        if pid and direction in EFFECT_ROW_DIRECTION_VALUES:
            effect_directions_by_paper.setdefault(pid, set()).add(direction)

    warnings: list[str] = []
    for claim in claim_registry:
        if (claim.get("supports_primary_direction_claim") or "").lower() != "yes":
            continue
        claim_dir = (claim.get("evidence_direction") or "").strip().lower()
        if claim_dir not in CONTRADICTIONS:
            continue
        opposite = CONTRADICTIONS[claim_dir]
        claim_id = claim.get("claim_id") or "?"
        anchor_ids = [
            a.strip()
            for a in (claim.get("eligible_anchor_paper_ids") or "").split(",")
            if a.strip()
        ]
        for aid in anchor_ids:
            directions = effect_directions_by_paper.get(aid, set())
            if opposite in directions:
                warnings.append(
                    f"claim {claim_id}: evidence_direction={claim_dir!r} but anchor paper {aid} "
                    f"has effect direction={opposite!r} in effect_registry — review before finalising"
                )
    return warnings


def split_ids(value: str) -> set[str]:
    return {
        item.strip()
        for item in re.split(r"[,;|]", value or "")
        if item.strip()
    }


def split_json_ids(value) -> set[str]:
    if isinstance(value, list):
        return {str(item).strip() for item in value if str(item).strip()}
    return split_ids(str(value or ""))


def duplicate_values(rows: list[dict], field: str) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for row in rows:
        value = str(row.get(field, "")).strip()
        if not value:
            continue
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def check_referential_integrity(
    review_contract: dict,
    citation_registry: dict,
    study_registry: list[dict[str, str]],
    claim_registry: list[dict[str, str]],
    effect_registry: list[dict[str, str]],
    evidence_table: list[dict[str, str]],
    narrative_text: str,
) -> list[str]:
    errors: list[str] = []
    study_ids = {row.get("paper_id", "").strip() for row in study_registry if row.get("paper_id", "").strip()}
    decision_ids = {row.get("decision_id", "").strip() for row in evidence_table if row.get("decision_id", "").strip()}
    entries = citation_registry.get("entries", [])
    citation_ids = {row.get("citation_id", "").strip() for row in entries if row.get("citation_id", "").strip()}
    effect_ids = {row.get("effect_id", "").strip() for row in effect_registry if row.get("effect_id", "").strip()}
    citation_numbers: dict[str, int] = {}
    number_owners: dict[int, list[str]] = {}
    for entry in entries:
        citation_id = str(entry.get("citation_id", "")).strip()
        try:
            number = int(entry.get("reference_number"))
            if number < 1:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"citation {citation_id or 'UNKNOWN'} lacks a positive integer reference_number")
            continue
        citation_numbers[citation_id] = number
        number_owners.setdefault(number, []).append(citation_id)
    duplicate_reference_numbers = {number: ids for number, ids in number_owners.items() if len(ids) > 1}
    if duplicate_reference_numbers:
        errors.append(f"citation registry contains duplicate reference_number values: {duplicate_reference_numbers}")
    for label, rows, field in (
        ("citation_registry", entries, "citation_id"),
        ("study_registry", study_registry, "paper_id"),
        ("evidence_to_decision_table", evidence_table, "decision_id"),
        ("claim_registry", claim_registry, "claim_id"),
        ("effect_registry", effect_registry, "effect_id"),
    ):
        duplicates = duplicate_values(rows, field)
        if duplicates:
            errors.append(f"{label} contains duplicate {field} values: {sorted(duplicates)}")
    for entry in entries:
        citation_id = entry.get("citation_id", "UNKNOWN")
        paper_id = str(entry.get("paper_id", "")).strip()
        if not paper_id or paper_id not in study_ids:
            errors.append(f"citation {citation_id} references unknown paper_id {paper_id!r}")
        unknown_decisions = split_json_ids(entry.get("supporting_decision_ids")) - decision_ids
        if unknown_decisions:
            errors.append(f"citation {citation_id} references unknown decision IDs: {sorted(unknown_decisions)}")
        unknown_effects = split_json_ids(entry.get("supporting_evidence_row_ids")) - effect_ids
        if unknown_effects:
            errors.append(f"citation {citation_id} references unknown effect IDs: {sorted(unknown_effects)}")
    unknown_contract_citations = set(review_contract.get("citation_ids", [])) - citation_ids
    if unknown_contract_citations:
        errors.append(f"review_contract citation_ids are unresolved: {sorted(unknown_contract_citations)}")
    unknown_contract_decisions = set(review_contract.get("decision_ids", [])) - decision_ids
    if unknown_contract_decisions:
        errors.append(f"review_contract decision_ids are unresolved: {sorted(unknown_contract_decisions)}")
    for row in evidence_table:
        unknown = split_ids(row.get("supporting_paper_ids", "")) - study_ids
        if unknown:
            errors.append(f"decision {row.get('decision_id', 'UNKNOWN')} references unknown papers: {sorted(unknown)}")
    for row in claim_registry:
        referenced = set()
        for field in ("eligible_anchor_paper_ids", "supporting_paper_ids", "counter_study_ids"):
            referenced.update(split_ids(row.get(field, "")))
        unknown = referenced - study_ids
        if unknown:
            errors.append(f"claim {row.get('claim_id', 'UNKNOWN')} references unknown papers: {sorted(unknown)}")
    inline_ids = set(re.findall(r"\[((?:CIT|P)[A-Za-z0-9_.-]+)\]", narrative_text))
    if inline_ids:
        errors.append(f"narrative exposes internal citation IDs instead of publication markers: {sorted(inline_ids)}")
    numeric_markers = {
        int(number)
        for marker in re.findall(r"\[(\d+(?:,\d+)*)\]", narrative_text)
        for number in marker.split(",")
    }
    unresolved_numbers = numeric_markers - set(citation_numbers.values())
    if unresolved_numbers:
        errors.append(f"narrative contains unresolved numeric citation markers: {sorted(unresolved_numbers)}")
    if citation_ids and not numeric_markers:
        errors.append("completed narrative has citation registry entries but no numeric inline citation markers")
    references_match = re.search(r"^#{1,3}\s+References\s*$([\s\S]*)", narrative_text, re.M | re.I)
    references_text = references_match.group(1) if references_match else ""
    for entry in entries:
        citation_id = str(entry.get("citation_id", "")).strip()
        number = citation_numbers.get(citation_id)
        if number is None:
            continue
        reference_match = re.search(rf"^\s*{number}\.\s+(.+)$", references_text, re.M)
        if not reference_match:
            errors.append(f"References section lacks numbered entry {number} for citation {citation_id}")
            continue
        title = str(entry.get("title", "")).strip()
        normalized_title = re.sub(
            r"[^a-z0-9]+",
            " ",
            unicodedata.normalize("NFKD", title.lower())
            .encode("ascii", "ignore")
            .decode("ascii"),
        ).strip()
        normalized_reference = re.sub(
            r"[^a-z0-9]+",
            " ",
            unicodedata.normalize("NFKD", reference_match.group(1).lower())
            .encode("ascii", "ignore")
            .decode("ascii"),
        ).strip()
        if not normalized_title or normalized_title not in normalized_reference:
            errors.append(f"reference {number} does not match the registered title for citation {citation_id}")
        authors = str(entry.get("authors", "")).strip()
        if authors:
            first_author = authors.split(";")[0].strip()
            surname = (first_author.split(",")[0] if "," in first_author else first_author.split()[0]).lower()
            normalized_surname = re.sub(
                r"[^a-z0-9]+",
                " ",
                unicodedata.normalize("NFKD", surname).encode("ascii", "ignore").decode("ascii"),
            ).strip()
            if normalized_surname and normalized_surname not in normalized_reference:
                errors.append(f"reference {number} does not match the registered first author for citation {citation_id}")
        year = str(entry.get("year", "")).strip()
        if year and not re.search(rf"\b{re.escape(year)}\b", reference_match.group(1)):
            errors.append(f"reference {number} does not match the registered year for citation {citation_id}")
        doi = str(entry.get("doi", "")).strip().lower().removeprefix("https://doi.org/").removeprefix("doi:")
        if doi and doi not in reference_match.group(1).lower():
            errors.append(f"reference {number} does not match the registered DOI for citation {citation_id}")
    for row in claim_registry:
        claim_text = str(row.get("claim_text", "")).strip()
        supporting_ids = split_ids(row.get("supporting_paper_ids", "")) | split_ids(
            row.get("eligible_anchor_paper_ids", "")
        )
        if not claim_text or not supporting_ids:
            continue
        matching_paragraphs = [part for part in narrative_text.split("\n\n") if claim_text in part]
        if not matching_paragraphs:
            errors.append(f"claim {row.get('claim_id', 'UNKNOWN')} is absent from the completed narrative")
            continue
        if narrative_text.count(claim_text) != 1:
            errors.append(f"claim {row.get('claim_id', 'UNKNOWN')} must occur exactly once in the completed narrative")
            continue
        citation_ids_for_papers = {
            entry.get("citation_id")
            for entry in entries
            if entry.get("paper_id") in supporting_ids
        }
        allowed_claim_numbers = {
            citation_numbers[citation_id]
            for citation_id in citation_ids_for_papers
            if citation_id in citation_numbers
        }
        paragraph_numbers = {
            int(number)
            for marker in re.findall(r"\[(\d+(?:,\d+)*)\]", matching_paragraphs[0])
            for number in marker.split(",")
        }
        if not paragraph_numbers.intersection(allowed_claim_numbers):
            errors.append(
                f"claim {row.get('claim_id', 'UNKNOWN')} lacks a supporting inline citation marker in the same paragraph"
            )
            continue
        exact_sentence = False
        for sentence in re.findall(r"[^.!?\n]+[.!?]?", matching_paragraphs[0]):
            sentence_numbers = {
                int(number)
                for marker in re.findall(r"\[(\d+(?:,\d+)*)\]", sentence)
                for number in marker.split(",")
            }
            if not sentence_numbers.intersection(allowed_claim_numbers):
                continue
            prose = re.sub(r"\[\d+(?:,\d+)*\]", "", sentence).strip().rstrip(".!?").strip()
            expected = claim_text.strip().rstrip(".!?").strip()
            if prose == expected:
                exact_sentence = True
                break
        if not exact_sentence:
            errors.append(
                f"claim {row.get('claim_id', 'UNKNOWN')} is not exactly bound to its citation marker at sentence level"
            )
    return errors


def check_section_composition(text: str) -> list[str]:
    """Detect common section composition problems:
    - Outcome sections that only state evidence gaps without any finding
    - Direct evidence section that appears very short relative to indirect
    - Consecutive paragraphs with identical first-word openers
    """
    warnings: list[str] = []

    # Pattern: sections that are only "evidence is limited/gap/absent" — no actual finding
    gap_only_sections = re.findall(
        r"#{1,3}[^\n]+\n+(?:(?:currently lacks|no direct|evidence gap|remains thin|"
        r"limited evidence|evidence is limited|insufficient evidence)[^\n]*\n+){2,}",
        text,
        re.IGNORECASE,
    )
    if gap_only_sections:
        warnings.append(
            f"literature_review_synthesis.md has {len(gap_only_sections)} outcome section(s) "
            "that contain only gap statements without any actual finding — condense or remove"
        )

    # Pattern: paragraph opening with "This study" or "This research" many times
    this_study_count = len(re.findall(r"\bThis (?:study|research|paper|article)\b", text, re.IGNORECASE))
    if this_study_count >= 5:
        warnings.append(
            f"literature_review_synthesis.md contains {this_study_count} 'This study/paper' openers — "
            "prefer naming author and year, or restructure as thematic synthesis"
        )

    return warnings


def check_repeated_sentence_patterns(text: str) -> list[str]:
    """Detect near-identical sentence openers that suggest template-driven prose."""
    warnings: list[str] = []
    body = re.split(r"^##\s+References\s*$", text, maxsplit=1, flags=re.M | re.I)[0]
    body = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("|"))
    sentences = re.split(r"(?<=[.!?])\s+", body)
    opener_counts: dict[str, int] = {}
    for sent in sentences:
        words = sent.strip().split()
        if len(words) >= 5:
            opener = re.sub(r"\d+", "#", " ".join(words[:5]).lower())
            opener_counts[opener] = opener_counts.get(opener, 0) + 1
    repeated = [(opener, count) for opener, count in opener_counts.items() if count >= 3]
    if repeated:
        examples = "; ".join(f'"{o}" ×{c}' for o, c in repeated[:3])
        warnings.append(
            f"literature_review_synthesis.md contains repeated sentence openers (template signal): {examples}"
        )
    return warnings


def fivegram_uniqueness(text: str) -> float:
    body = re.split(r"^##\s+References\s*$", text, maxsplit=1, flags=re.M | re.I)[0]
    tokens = re.findall(r"[a-z]{3,}", re.sub(r"\d+", "#", body.lower()))
    grams = [tuple(tokens[index:index + 5]) for index in range(max(0, len(tokens) - 4))]
    return len(set(grams)) / len(grams) if grams else 1.0


def high_similarity_paragraph_pairs(text: str, threshold: float = 0.82) -> list[tuple[int, int, float]]:
    body = re.split(r"^##\s+References\s*$", text, maxsplit=1, flags=re.M | re.I)[0]
    stopwords = {
        "about", "after", "also", "among", "because", "before", "between", "could", "from", "have",
        "into", "more", "most", "only", "other", "should", "such", "than", "that", "their", "there",
        "these", "this", "through", "using", "were", "which", "while", "with", "within", "would",
    }
    paragraphs = []
    for part in re.split(r"\n\s*\n", body):
        if part.lstrip().startswith("#") or len(part.split()) < 45:
            continue
        words = set(re.findall(r"[a-z]{4,}", re.sub(r"\d+", "#", part.lower()))) - stopwords
        if words:
            paragraphs.append(words)
    pairs: list[tuple[int, int, float]] = []
    for left in range(len(paragraphs)):
        for right in range(left + 1, len(paragraphs)):
            union = paragraphs[left] | paragraphs[right]
            score = len(paragraphs[left] & paragraphs[right]) / len(union) if union else 0.0
            if score >= threshold:
                pairs.append((left + 1, right + 1, round(score, 3)))
    return pairs


def validate_publication_bundle(root: Path, warnings: list[str], errors: list[str]) -> None:
    manifest_path = root / "publication_manifest.json"
    if not manifest_path.exists():
        return
    manifest = load_json(manifest_path)
    # The scaffold reserves this filename with an empty object. Publication
    # checks become binding only after the packaging step populates the manifest.
    if not manifest:
        return
    for field in ["manifest_version", "venue_profile", "citation_style", "languages", "source_files", "artifacts"]:
        if field not in manifest:
            errors.append(f"publication_manifest.json missing field: {field}")
    source_files = manifest.get("source_files", [])
    if not isinstance(source_files, list) or not source_files:
        errors.append("publication_manifest.json must list at least one source file")
        source_files = []
    source_names: list[str] = []
    for item in source_files:
        if not isinstance(item, dict):
            errors.append("publication_manifest.json source_files entries must be hash-bound objects")
            continue
        name = str(item.get("file", ""))
        source_names.append(name)
        path = root / name
        if not name or Path(name).name != name or not path.exists() or path.stat().st_size == 0:
            errors.append(f"publication_manifest.json references missing/empty source file: {name!r}")
            continue
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if item.get("sha256") != actual_hash or item.get("size_bytes") != path.stat().st_size:
            errors.append(f"publication source hash/size mismatch: {name}")
    if source_names and "literature_review_synthesis.md" not in source_names:
        errors.append("publication_manifest.json source_files must include literature_review_synthesis.md")
    artifact_rows = manifest.get("artifacts", [])
    if not isinstance(artifact_rows, list) or not artifact_rows:
        errors.append("publication_manifest.json must contain a non-empty artifacts list")
    else:
        artifact_names = [str(item.get("file", "")) for item in artifact_rows]
        duplicate_artifacts = {name for name in artifact_names if name and artifact_names.count(name) > 1}
        if duplicate_artifacts:
            errors.append(f"publication_manifest.json contains duplicate artifact entries: {sorted(duplicate_artifacts)}")
        for item in artifact_rows:
            name = str(item.get("file", ""))
            path = root / name
            if not name or Path(name).name != name or not path.exists() or path.stat().st_size == 0:
                errors.append(f"publication_manifest.json references missing/empty artifact: {name!r}")
                continue
            actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            if item.get("sha256") != actual_hash or item.get("size_bytes") != path.stat().st_size:
                errors.append(f"publication artifact hash/size mismatch: {name}")
        manifest_bound_files = [name for name in FULL_PACKAGE_FILES if name != "publication_manifest.json"]
        missing_manifest_entries = set(manifest_bound_files + ["literature_review_synthesis.md", "delivery_quality_report.json"]) - set(artifact_names)
        if missing_manifest_entries:
            errors.append(f"publication manifest does not enumerate required artifacts: {sorted(missing_manifest_entries)}")
        missing_source_artifacts = set(source_names) - set(artifact_names)
        if missing_source_artifacts:
            errors.append(f"publication source_files are not enumerated as artifacts: {sorted(missing_source_artifacts)}")
        source_path = root / "literature_review_synthesis.md"
        if source_path.exists():
            current_source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
            for name in ("literature_review.docx", "literature_review.pdf", "literature_review.tex"):
                row = next((item for item in artifact_rows if item.get("file") == name), None)
                if row and row.get("source_sha256") != current_source_hash:
                    errors.append(f"publication export is stale relative to source: {name}")
                if row and not str(row.get("generator", "")).strip():
                    errors.append(f"publication export lacks generator provenance: {name}")
    if not (root / "references.bib").exists():
        errors.append("references.bib is missing despite publication_manifest.json being present")
    if not (root / "delivery_quality_report.json").exists():
        errors.append("delivery_quality_report.json is missing despite publication_manifest.json being present")
    else:
        report = load_json(root / "delivery_quality_report.json")
        if not report.get("files"):
            errors.append("delivery_quality_report.json must contain a non-empty files list")
        for item in report.get("files", []):
            if not item.get("sections"):
                warnings.append(
                    f"delivery_quality_report.json file entry has no section metrics: {item.get('file', 'unknown')}"
                )


def inspect_pdf(path: Path) -> tuple[bool, str]:
    """Return whether a real PDF parser can read at least one page, plus metadata text."""
    pdfinfo = shutil.which("pdfinfo")
    if pdfinfo:
        try:
            result = subprocess.run(
                [pdfinfo, str(path)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False, ""
        if result.returncode != 0:
            return False, result.stdout + result.stderr
        match = re.search(r"^Pages:\s+(\d+)\s*$", result.stdout, re.MULTILINE)
        return bool(match and int(match.group(1)) > 0), result.stdout
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        metadata = "\n".join(f"{key}: {value}" for key, value in (reader.metadata or {}).items())
        return len(reader.pages) > 0, metadata
    except Exception:
        return False, ""


def detect_listy_profile_lines(text: str) -> int:
    return sum(
        1
        for line in text.splitlines()
        if line.strip().startswith("- **")
        and "contributes to the mapped evidence" in line.lower()
    )


def rough_body_word_count(text: str) -> int:
    tokens = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text)
    return len(tokens)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a structured literature-review package.")
    parser.add_argument("review_dir")
    parser.add_argument(
        "--min-body-words",
        type=int,
        default=0,
        help="Optional stricter floor. Mature decision-grade/full-package reviews always enforce at least 4500 body words.",
    )
    parser.add_argument(
        "--allow-structure-only",
        action="store_true",
        help="Allow validation to pass without literature_review_synthesis.md.",
    )
    args = parser.parse_args()

    root = Path(args.review_dir)
    errors: list[str] = []
    warnings: list[str] = []

    missing = [name for name in REQUIRED_FILES if not (root / name).exists()]
    if missing:
        errors.append(f"missing required files: {', '.join(missing)}")

    if errors:
        raise SystemExit("\n".join(errors))

    search_log = read_csv_rows(root / "search_log.csv")
    candidate_records_raw = read_csv_rows(root / "candidate_records_raw.csv")
    candidate_records_dedup = read_csv_rows(root / "candidate_records_dedup.csv")
    screening_decisions = read_csv_rows(root / "screening_decisions.csv")
    study_registry = read_csv_rows(root / "study_registry.csv")
    measurement_registry = read_csv_rows(root / "measurement_registry.csv")
    confounder_registry = read_csv_rows(root / "confounder_registry.csv")
    evidence_table = read_csv_rows(root / "evidence_to_decision_table.csv")
    effect_registry = read_csv_rows_if_exists(root / "effect_registry.csv")
    claim_registry = read_csv_rows_if_exists(root / "claim_registry.csv")
    bias_registry = read_csv_rows_if_exists(root / "bias_registry.csv")
    quality_appraisal = read_csv_rows_if_exists(root / "quality_appraisal_registry.csv")
    fulltext_inventory = read_csv_rows_if_exists(root / "fulltext_inventory.csv")
    protocol_inputs = load_json(root / "protocol_inputs.json")

    allow_empty = args.allow_structure_only

    errors.extend(require_columns(search_log, ["query", "source", "status"], "search_log.csv", allow_empty=allow_empty))
    errors.extend(
        require_columns(
            search_log,
            [
                "search_round",
                "query_family",
                "query",
                "source",
                "source_query",
                "date_searched",
                "status",
            ],
            "search_log.csv",
            allow_empty=allow_empty,
        )
    )
    errors.extend(
        require_columns(
            candidate_records_raw,
            ["search_id", "source", "title", "url", "publication_status"],
            "candidate_records_raw.csv",
            allow_empty=allow_empty,
        )
    )
    errors.extend(
        require_columns(
            candidate_records_dedup,
            ["search_id", "source", "title", "url", "publication_status"],
            "candidate_records_dedup.csv",
            allow_empty=allow_empty,
        )
    )
    errors.extend(
        require_columns(
            screening_decisions,
            ["paper_id", "decision", "screening_stage", "reason", "include_in_synthesis"],
            "screening_decisions.csv",
            allow_empty=allow_empty,
        )
    )
    errors.extend(
        require_columns(
            study_registry,
            ["paper_id", "primary_role", "design", "population", "core_findings"],
            "study_registry.csv",
            allow_empty=allow_empty,
        )
    )
    eligibility_cols = [
        "direct_question_match",
        "design_integrity_ok",
        "comparator_integrity_ok",
        "time_zero_clear",
        "prior_user_design",
    ]
    strategy_fields = [
        "synthesis_tier",
        "anchor_eligible",
        *eligibility_cols,
    ]
    strategy_screening_fields = [
        *eligibility_cols,
        "directness_tier",
        "exclusion_reason_code",
        "question_match_summary",
    ]
    if study_registry and not all(col in study_registry[0] for col in eligibility_cols):
        missing_elig = [c for c in eligibility_cols if c not in study_registry[0]]
        warnings.append(
            f"study_registry.csv is missing eligibility columns: {', '.join(missing_elig)}. "
            "Add these for treatment_strategy_comparison or decision_support reviews."
        )
    errors.extend(
        require_columns(
            measurement_registry,
            ["construct", "preferred_tool", "protocol_use"],
            "measurement_registry.csv",
            allow_empty=allow_empty,
        )
    )
    errors.extend(
        require_columns(
            confounder_registry,
            ["variable", "classification", "recommended_main_model_role"],
            "confounder_registry.csv",
            allow_empty=allow_empty,
        )
    )
    errors.extend(
        require_columns(
            evidence_table,
            ["decision_id", "decision", "supporting_paper_ids"],
            "evidence_to_decision_table.csv",
            allow_empty=allow_empty,
        )
    )

    review_contract = load_json(root / "review_contract.json")
    sufficiency = load_json(root / "evidence_sufficiency_report.json")
    citation_registry = load_json(root / "citation_registry.json")
    question_type = (
        review_contract.get("question_type")
        or protocol_inputs.get("question_type")
        or ""
    )
    status = str(review_contract.get("status", "")).strip().lower()
    completed = status in COMPLETED_STATUSES and not args.allow_structure_only
    sparse_ok, sparse_error = sparse_exception(review_contract)

    if not args.allow_structure_only:
        errors.extend(check_review_type_route(review_contract))
        errors.extend(check_search_execution(search_log, completed))
        errors.extend(check_search_freshness(search_log, review_contract, completed))
        search_strategy_text = (root / "search_strategy.md").read_text(encoding="utf-8") if (root / "search_strategy.md").exists() else ""
        errors.extend(check_search_strategy_document(search_strategy_text, completed))
        errors.extend(check_screening_accounting(screening_decisions, completed, sparse_ok))
        if sparse_error:
            errors.append(sparse_error)

    if review_contract.get("delivery_preset") == "full_package" and not args.allow_structure_only:
        missing_full_package = [name for name in FULL_PACKAGE_FILES if not (root / name).exists() or (root / name).stat().st_size == 0]
        if missing_full_package:
            errors.append("full_package is missing required publication artifacts: " + ", ".join(missing_full_package))
        verification_rows = read_csv_rows_if_exists(root / "citation_verification_report.csv")
        if not verification_rows:
            errors.append("full_package requires a non-empty citation_verification_report.csv")
        else:
            unresolved_verification = [
                row.get("doi") or row.get("local_title") or "UNKNOWN"
                for row in verification_rows
                if row.get("verification_status") != "verified"
            ]
            if unresolved_verification:
                errors.append(
                    "full_package contains citations that are not verified: "
                    + ", ".join(unresolved_verification)
                )
            entries = citation_registry.get("entries", [])
            verification_by_id = {row.get("citation_id", ""): row for row in verification_rows if row.get("citation_id")}
            if len(verification_by_id) != len(verification_rows):
                errors.append("citation verification rows must have unique, non-empty citation_id values")
            registered_ids = {str(entry.get("citation_id", "")) for entry in entries if entry.get("citation_id")}
            reported_ids = set(verification_by_id)
            if reported_ids != registered_ids:
                errors.append(
                    "citation verification citation_id set must exactly match citation_registry.json; "
                    f"missing={sorted(registered_ids - reported_ids)}, extra={sorted(reported_ids - registered_ids)}"
                )
            for entry in entries:
                citation_id = str(entry.get("citation_id", ""))
                row = verification_by_id.get(citation_id)
                if not row:
                    errors.append(f"citation verification report does not cover {citation_id}")
                    continue
                expected = {
                    "reference_number": str(entry.get("reference_number", "")),
                    "local_title": str(entry.get("title", "")).strip(),
                    "local_year": str(entry.get("year", "")).strip(),
                }
                for field, expected_value in expected.items():
                    if str(row.get(field, "")).strip() != expected_value:
                        errors.append(f"citation verification identity mismatch for {citation_id}: {field}")
                registered_authors = str(entry.get("authors", "")).strip()
                expected_author = ((registered_authors.split(";")[0].split(",")[0]) if "," in registered_authors.split(";")[0] else registered_authors.split(";")[0].split()[0] if registered_authors else "").strip()
                if str(row.get("local_first_author", "")).strip().lower() != expected_author.lower():
                    errors.append(f"citation verification identity mismatch for {citation_id}: local_first_author")
                registered_doi = str(entry.get("doi", "")).strip().lower().removeprefix("https://doi.org/").removeprefix("doi:")
                reported_doi = str(row.get("doi", "")).strip().lower().removeprefix("https://doi.org/").removeprefix("doi:")
                if reported_doi != registered_doi:
                    errors.append(f"citation verification identity mismatch for {citation_id}: doi")

        pdf_path = root / "literature_review.pdf"
        current_source_hash = hashlib.sha256((root / "literature_review_synthesis.md").read_bytes()).hexdigest()
        if pdf_path.exists():
            pdf_ok, pdf_metadata = inspect_pdf(pdf_path)
            if not pdf_ok:
                errors.append("literature_review.pdf is not readable as a non-empty PDF document")
            elif f"source_sha256_{current_source_hash}" not in pdf_metadata:
                errors.append("literature_review.pdf does not contain the current source SHA-256 provenance marker")
        docx_path = root / "literature_review.docx"
        if docx_path.exists():
            if not zipfile.is_zipfile(docx_path):
                errors.append("literature_review.docx is not a valid DOCX ZIP package")
            else:
                with zipfile.ZipFile(docx_path) as archive:
                    if "word/document.xml" not in archive.namelist():
                        errors.append("literature_review.docx lacks word/document.xml")
                    core_xml = archive.read("docProps/core.xml").decode("utf-8", errors="replace") if "docProps/core.xml" in archive.namelist() else ""
                    if f"source_sha256:{current_source_hash}" not in core_xml:
                        errors.append("literature_review.docx does not contain the current source SHA-256 provenance marker")
        tex_path = root / "literature_review.tex"
        if tex_path.exists():
            tex_text = tex_path.read_text(encoding="utf-8", errors="replace")
            if "\\documentclass" not in tex_text or "\\begin{document}" not in tex_text:
                errors.append("literature_review.tex is not a complete LaTeX document")
            if f"% source_sha256:{current_source_hash}" not in tex_text:
                errors.append("literature_review.tex does not contain the current source SHA-256 provenance marker")

    if not args.allow_structure_only:
        for field in REVIEW_CONTRACT_FIELDS:
            if field not in review_contract:
                errors.append(f"review_contract.json missing field: {field}")

        if question_type == "treatment_strategy_comparison":
            for field in TREATMENT_STRATEGY_REVIEW_CONTRACT_FIELDS:
                if field not in review_contract:
                    errors.append(f"review_contract.json missing treatment-strategy field: {field}")

        for field in SUFFICIENCY_FIELDS:
            if field not in sufficiency:
                errors.append(f"evidence_sufficiency_report.json missing field: {field}")

        entries = citation_registry.get("entries")
        if not isinstance(entries, list) or not entries:
            errors.append("citation_registry.json must contain a non-empty entries list")
        else:
            required_entry_fields = {
                "citation_id",
                "paper_id",
                "title",
                "narrative_role",
                "claim_supported",
                "supporting_decision_ids",
                "supporting_evidence_row_ids",
                "reference_number",
            }
            for index, entry in enumerate(entries, start=1):
                if not required_entry_fields.issubset(entry):
                    missing_entry_fields = sorted(required_entry_fields - set(entry))
                    errors.append(
                        f"citation_registry.json entry {index} missing fields: "
                        + ", ".join(missing_entry_fields)
                    )
                nonempty_entry_fields = required_entry_fields - {
                    "supporting_decision_ids",
                    "supporting_evidence_row_ids",
                }
                empty_entry_fields = sorted(field for field in nonempty_entry_fields if not entry.get(field))
                if empty_entry_fields:
                    errors.append(
                        f"citation_registry.json entry {index} has empty fields: "
                        + ", ".join(empty_entry_fields)
                    )
                role = str(entry.get("narrative_role", "")).strip()
                if role and role not in ALLOWED_NARRATIVE_ROLES:
                    errors.append(
                        f"citation_registry.json entry {index} has unsupported narrative_role: {role!r}"
                    )

        included_ids = {
            (row.get("paper_id") or "").strip()
            for row in screening_decisions
            if ((row.get("include_in_synthesis") or "").strip().lower() in {"yes", "true", "1"}
                or (row.get("decision") or "").strip().lower() == "include")
            and (row.get("paper_id") or "").strip()
        }
        claim_bearing_ids = {
            (row.get("paper_id") or "").strip()
            for row in fulltext_inventory
            if truthy(row.get("claim_bearing")) and (row.get("paper_id") or "").strip()
        } or included_ids
        design_by_paper = {
            (row.get("paper_id") or "").strip(): (row.get("design") or "").strip()
            for row in study_registry
            if (row.get("paper_id") or "").strip()
        }
        errors.extend(check_quality_appraisal(quality_appraisal, claim_bearing_ids, completed, design_by_paper))
        errors.extend(
            check_depth_and_reference_floor(
                review_contract,
                entries if isinstance(entries, list) else [],
                fulltext_inventory,
                completed,
            )
        )
        errors.extend(check_effect_coverage(study_registry, effect_registry, completed))

        mode = review_contract.get("project_mode")
        if mode not in CANONICAL_PROJECT_MODES:
            errors.append(
                f"review_contract.json project_mode must be canonical; got {mode!r}"
            )
        recommended_mode = sufficiency.get("mode_recommendation")
        if mode == "research" and recommended_mode != "research":
            errors.append(
                "review_contract.json claims research mode but evidence_sufficiency_report.json "
                "does not recommend research"
            )

        if question_type == "treatment_strategy_comparison":
            errors.extend(
                require_columns(
                    screening_decisions,
                    strategy_screening_fields,
                    "screening_decisions.csv",
                    allow_empty=allow_empty,
                )
            )
            errors.extend(
                require_columns(
                    study_registry,
                    strategy_fields,
                    "study_registry.csv",
                    allow_empty=allow_empty,
                )
            )
            if review_contract.get("deliverable_style") == "narrative_review":
                if not claim_registry:
                    errors.append(
                        "claim_registry.csv is required when deliverable_style=narrative_review"
                    )
                if not effect_registry:
                    errors.append(
                        "effect_registry.csv is required when deliverable_style=narrative_review"
                    )
                strict_anchor_rows = [
                    row for row in study_registry
                    if (row.get("synthesis_tier") or "").strip() == "core_direct_strict"
                    and (row.get("anchor_eligible") or "").strip().lower() == "yes"
                ]
                if not strict_anchor_rows:
                    readiness = (review_contract.get("narrative_readiness") or "").strip()
                    if readiness != "suggestive_narrative_broad_support":
                        errors.append(
                            "deliverable_style=narrative_review requires at least one "
                            "core_direct_strict anchor study, or "
                            "narrative_readiness=suggestive_narrative_broad_support"
                        )

                appendix_ids = {
                    row.get("paper_id", "")
                    for row in study_registry
                    if (row.get("synthesis_tier") or "").strip() == "appendix_only"
                }
                primary_claim_rows = [
                    row for row in claim_registry
                    if (row.get("supports_primary_direction_claim") or "").strip().lower() == "yes"
                ]
                if not primary_claim_rows:
                    errors.append(
                        "claim_registry.csv must contain at least one row with "
                        "supports_primary_direction_claim=yes for a narrative review"
                    )
                for row in primary_claim_rows:
                    anchors = {
                        item.strip()
                        for item in (row.get("eligible_anchor_paper_ids") or "").split(",")
                        if item.strip()
                    }
                    if not anchors:
                        errors.append(
                            f"claim_registry.csv claim {row.get('claim_id', 'unknown')} "
                            "has no eligible_anchor_paper_ids"
                        )
                    if anchors & appendix_ids:
                        errors.append(
                            f"claim_registry.csv claim {row.get('claim_id', 'unknown')} "
                            "uses appendix_only studies as eligible anchors"
                        )
                    if not row.get("outcome_family", "").strip():
                        errors.append(
                            f"claim_registry.csv claim {row.get('claim_id', 'unknown')} "
                            "is missing outcome_family"
                        )
                for row in effect_registry:
                    if not row.get("outcome_family", "").strip():
                        errors.append(
                            "effect_registry.csv is missing outcome_family values for one or more rows"
                        )
                    if (
                        row.get("supports_primary_direction_claim", "").strip().lower() == "yes"
                        and not row.get("effect_directness", "").strip()
                    ):
                        errors.append(
                            "effect_registry.csv primary-claim rows must specify effect_directness"
                        )

        if question_type in {"treatment_strategy_comparison", "exposure_outcome_association", "prognosis"}:
            if not effect_registry:
                errors.append(f"effect_registry.csv is required for completed {question_type} reviews")
        if not claim_registry:
            errors.append("claim_registry.csv is required for every completed review")
        if question_type in {"treatment_strategy_comparison", "exposure_outcome_association"} and not bias_registry:
            errors.append(f"bias_registry.csv is required for completed {question_type} reviews")

    # ---- Enum consistency checks ----
    if bias_registry:
        errors.extend(
            require_columns(
                bias_registry,
                ["paper_id", "bias_domain", "severity", "bias_direction", "evidence_of_bias"],
                "bias_registry.csv",
                allow_empty=allow_empty,
            )
        )
        errors.extend(
            check_enum_values(bias_registry, "severity", BIAS_SEVERITY_VALUES, "bias_registry.csv")
        )
        errors.extend(
            check_enum_values(
                bias_registry, "bias_direction", BIAS_DIRECTION_VALUES, "bias_registry.csv"
            )
        )
    if claim_registry:
        errors.extend(
            check_enum_values(claim_registry, "allowed_strength", ALLOWED_STRENGTH_VALUES, "claim_registry.csv")
        )
        errors.extend(
            check_enum_values(claim_registry, "evidence_direction", EVIDENCE_DIRECTION_VALUES, "claim_registry.csv")
        )

    # Scored candidates (optional file)
    scored_path = root / "scored_candidates.csv"
    if scored_path.exists():
        scored = read_csv_rows(scored_path)
        if scored:
            errors.extend(check_enum_values(scored, "study_credibility", STUDY_CREDIBILITY_VALUES, "scored_candidates.csv"))
            errors.extend(check_enum_values(scored, "effect_trustworthiness", EFFECT_TRUSTWORTHINESS_VALUES, "scored_candidates.csv"))
            errors.extend(check_enum_values(scored, "likely_directness", LIKELY_DIRECTNESS_VALUES, "scored_candidates.csv"))
            errors.extend(check_enum_values(scored, "decision_role", DECISION_ROLE_VALUES, "scored_candidates.csv"))
            errors.extend(check_enum_values(scored, "claim_strength_ceiling", ALLOWED_STRENGTH_VALUES, "scored_candidates.csv"))

    # Claim–evidence binding check
    if claim_registry and effect_registry:
        errors.extend(
            check_claim_evidence_binding(claim_registry, effect_registry, "claim_registry.csv")
        )
        # Claim direction consistency: claim.evidence_direction vs effect_registry.direction
        errors.extend(check_direction_consistency(claim_registry, effect_registry))

    rounds_present = {row.get("search_round", "").strip() for row in search_log if row.get("search_round", "").strip()}
    review_md_exists = (root / "literature_review_synthesis.md").exists()
    validate_publication_bundle(root, warnings, errors)
    if review_md_exists and not args.allow_structure_only:
        if len(rounds_present) < 2:
            errors.append(
                "search_log.csv should document at least two search rounds for a completed review "
                "(initial mapping plus reading-driven expansion)"
            )

        search_sources = {row.get("source", "").strip() for row in search_log if row.get("source", "").strip()}
        # Only require free-access sources; subscription sources are expected to be absent when blocked
        missing_free_sources = [s for s in REQUIRED_FREE_SOURCES if s not in search_sources]
        if missing_free_sources:
            errors.append(
                "search_log.csv is missing free-access core sources for a completed review: "
                + ", ".join(missing_free_sources)
                + ". Add entries with status=blocked_auth_required if access is unavailable."
            )

    review_md = root / "literature_review_synthesis.md"
    if review_md_exists and not args.allow_structure_only:
        text = load_text(review_md)
        wc = max(body_word_count(text), rough_body_word_count(text))
        delivery_preset = str(review_contract.get("delivery_preset", "decision_grade"))
        mature_floor = 4500 if completed and delivery_preset in {"decision_grade", "full_package"} and not sparse_ok else 1500
        required_words = max(args.min_body_words, mature_floor)
        if wc < required_words:
            errors.append(
                f"literature_review_synthesis.md body too short: {wc} words "
                f"(minimum {required_words} for this release profile)"
            )
        citation_entries = citation_registry.get("entries", [])
        if delivery_preset in {"decision_grade", "full_package"} and len(citation_entries) < 3:
            errors.append(
                f"{delivery_preset} requires at least 3 independently registered sources; "
                f"found {len(citation_entries)}. Downgrade the deliverable or retrieve a broader evidence base."
            )
        ngram_score = fivegram_uniqueness(text)
        if ngram_score < 0.55:
            errors.append(
                f"literature_review_synthesis.md has low five-word sequence diversity ({ngram_score:.3f}); "
                "length appears to come from templated repetition rather than new evidence or interpretation"
            )
        similar_pairs = high_similarity_paragraph_pairs(text)
        if len(similar_pairs) >= 3:
            errors.append(
                "literature_review_synthesis.md contains too many highly similar substantive paragraphs: "
                + ", ".join(f"{left}-{right} ({score:.2f})" for left, right, score in similar_pairs[:6])
            )
        if not check_inline_screening_numbers(text):
            errors.append(
                "literature_review_synthesis.md must contain explicit inline screening numbers "
                "in the Search and Screening section"
            )
        errors.extend(
            reconcile_screening_counts(
                text,
                candidate_records_raw,
                candidate_records_dedup,
                screening_decisions,
            )
        )
        if completed and delivery_preset in {"decision_grade", "full_package"}:
            errors.extend(check_embedded_evidence_tables(text))
        if completed and re.search(r"\b(?:TODO|TBD|FILL IN)\b|\{\{[^}]+\}\}", text, re.IGNORECASE):
            errors.append("literature_review_synthesis.md contains unresolved placeholder text")
        errors.extend(
            check_referential_integrity(
                review_contract,
                citation_registry,
                study_registry,
                claim_registry,
                effect_registry,
                evidence_table,
                text,
            )
        )
        prohibited = check_prohibited_in_body(text, PROHIBITED_BODY_PHRASES)
        if prohibited:
            errors.append(
                "literature_review_synthesis.md contains prohibited body phrases: "
                + ", ".join(prohibited)
            )
        meta_language = check_meta_language(text, META_LANGUAGE_PATTERNS)
        if meta_language:
            errors.append(
                "literature_review_synthesis.md contains workflow/package meta language: "
                + ", ".join(meta_language)
            )

        # Overclaim check: warning level only.
        # See OVERCLAIM_WARNING_PHRASES for rationale on why these are warnings, not failures.
        overclaims = check_overclaim_phrases(text, OVERCLAIM_WARNING_PHRASES)
        if overclaims:
            warnings.append(
                "literature_review_synthesis.md contains potential overclaim phrases "
                "(verify each against claim_registry.csv allowed_strength): "
                + ", ".join(f'"{p.strip()}"' for p in overclaims)
            )
        listy_lines = detect_listy_profile_lines(text)
        if listy_lines >= 6:
            warnings.append(
                "literature_review_synthesis.md still contains many one-paper-one-sentence "
                f"evidence-profile lines ({listy_lines} detected); prefer thematic synthesis."
            )

        # Methods completeness check
        missing_methods = check_methods_completeness(text)
        if missing_methods:
            warnings.append(
                "literature_review_synthesis.md Search and Screening section may be missing: "
                + ", ".join(missing_methods)
            )

        # Repeated sentence opener check (template-prose signal)
        repeated_openers = check_repeated_sentence_patterns(text)
        if repeated_openers:
            errors.extend(repeated_openers)

        # Section composition check
        warnings.extend(check_section_composition(text))

    elif not args.allow_structure_only:
        errors.append(
            "literature_review_synthesis.md is missing; rerun with --allow-structure-only "
            "only if you are validating an unfinished scaffold"
        )

    if warnings:
        print("WARNINGS (not failures — review before finalising):")
        for w in warnings:
            print(f"  ⚠  {w}")

    if completed and not args.allow_structure_only:
        errors.extend(validate_semantics(root))

    if errors:
        raise SystemExit("\n".join(errors))

    print("Review package validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
