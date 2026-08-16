#!/usr/bin/env python3
"""Build an iterative multi-database search plan for a literature review."""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


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

# Primary sources: free-text structured APIs suited for all query families.
# Subscription sources (Embase, WoS) are included in the plan but marked
# blocked_auth_required at runtime.
PRIMARY_SOURCES = [
    "PubMed/MEDLINE",
    "OpenAlex",
    "Europe PMC",
    "Semantic Scholar",
    "Embase",
    "Web of Science",
]

# Preprint sources: interval-based scans with local keyword scoring.
# For clinical and pharmacoepidemiology question types, preprints have very low
# signal density (most published pharmacoepi evidence is peer-reviewed). They
# are therefore only generated for Round 1 direct_association queries, with a
# lower retrieval target, and skipped for all Round 2/3 query families.
PREPRINT_SOURCES = ["medRxiv", "bioRxiv"]

# Question types for which preprints are low-yield and should only be queried
# in Round 1 / direct_association family. For other types (e.g. mechanism_mediation,
# methods_estimand) preprints may be more useful and are treated as primary.
CLINICAL_QUESTION_TYPES = {
    "treatment_strategy_comparison",
    "prognosis",
    "exposure_outcome_association",
    "guideline_to_evidence",
}

# Query families where preprints are always skipped regardless of question type.
PREPRINT_SKIP_FAMILIES = {
    "population_setting",
    "measurement_validation",
    "design_estimand",
    "confounder_logic",
    "contradiction_null_findings",
    "citation_chaining",
}

# Strategy hint vocabularies — used only when question_type == treatment_strategy_comparison
# or when strategy vocabulary is inferred from the topic config.
# These are NOT applied to all question types.
CONTINUE_HINTS = (
    "continue",
    "continu",
    "persist",
    "maintain",
    "ongoing",
    "stay on",
)

STOP_HINTS = (
    "discontinu",
    "stop",
    "cessat",
    "cease",
    "withdraw",
    "terminat",
    "deprescrib",
    "hold",
)

# Supported question types. Controls which query families are activated by default
# and which design terms are used in the design_estimand family.
QUESTION_TYPES = {
    "exposure_outcome_association",
    "treatment_strategy_comparison",
    "prognosis",
    "diagnostic_measurement",
    "mechanism_mediation",
    "guideline_to_evidence",
    "methods_estimand",
}

# Supported review goals. Controls required outputs and retrieval depth.
REVIEW_GOALS = {
    "background_landscape",
    "decision_support",
    "protocol_support",
    "manuscript_positioning",
    "gap_mapping",
    "methods_support",
}

# Design terms per question type — used in the design_estimand query family.
# Only terms relevant to the declared question type are injected; no defaults are
# forced when question_type is absent.
QUESTION_TYPE_DESIGN_TERMS: dict[str, list[str]] = {
    "exposure_outcome_association": [
        "cohort", "case-control", "cross-sectional",
        "odds ratio", "risk ratio", "hazard ratio",
    ],
    "treatment_strategy_comparison": [
        "target trial emulation", "active comparator", "prior user design",
        "grace period", "intention-to-treat", "per-protocol",
        "new user design", "incident user",
    ],
    "prognosis": [
        "cohort", "prospective", "time-to-event",
        "survival analysis", "competing risk", "hazard ratio", "Kaplan-Meier",
    ],
    "diagnostic_measurement": [
        "diagnostic accuracy", "sensitivity", "specificity",
        "AUC", "ROC", "positive predictive value", "kappa", "agreement",
    ],
    "mechanism_mediation": [
        "mechanism", "pathway", "mediation", "biological plausibility",
        "intermediate", "causal pathway",
    ],
    "guideline_to_evidence": [
        "clinical guideline", "practice recommendation",
        "evidence synthesis", "systematic review", "meta-analysis",
    ],
    "methods_estimand": [
        "estimand", "target trial", "DAG", "directed acyclic graph",
        "confounding", "instrumental variable", "causal inference",
    ],
}

POPULATION_LIKE_TERMS = (
    "adult",
    "adults",
    "older",
    "elderly",
    "geriatric",
    "frail",
    "nursing home",
    "very elderly",
    "aged ",
    "years",
    "population",
    "community-dwelling",
    "hospital",
    "care home",
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def unique_nonempty(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        value = (value or "").strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def concise_seed_terms(values: list[str]) -> list[str]:
    seeds: list[str] = []
    for value in values:
        value = (value or "").strip()
        if not value:
            continue
        lowered = value.lower()
        word_count = len(value.split())
        if any(token in lowered for token in [" versus ", " vs ", "compared with", "compared to"]):
            continue
        if word_count > 8:
            continue
        seeds.append(value)
    return unique_nonempty(seeds)


def split_enumerated_terms(value: str) -> list[str]:
    """Split comma/semicolon-separated topic prose into queryable phrases."""
    value = (value or "").strip()
    if not value:
        return []
    if "," not in value and ";" not in value:
        return []
    parts = []
    for raw_part in value.replace(";", ",").split(","):
        part = re.sub(r"^(and|or)\s+", "", raw_part.strip(), flags=re.IGNORECASE)
        if part:
            parts.append(part)
    return unique_nonempty(parts)


def split_long_phrase(value: str) -> list[str]:
    """Recover shorter query terms from long natural-language labels.

    This is intentionally conservative. We only split on "with" when the source
    phrase is long enough that using it verbatim as an exact search phrase would
    likely suppress retrieval.
    """
    value = (value or "").strip()
    if not value:
        return []
    lowered = value.lower()
    pieces: list[str] = []
    if len(value.split()) > 8 and " with " in lowered:
        left, right = re.split(r"\bwith\b", value, maxsplit=1, flags=re.IGNORECASE)
        pieces.extend([left.strip(), right.strip()])
    return unique_nonempty([piece for piece in pieces if piece and len(piece.split()) <= 8])


def expand_query_terms(*values: str) -> list[str]:
    """Turn free-text topic fields into shorter, queryable seed terms."""
    expanded: list[str] = []
    for value in values:
        expanded.extend(concise_seed_terms([value]))
        expanded.extend(split_enumerated_terms(value))
        expanded.extend(split_long_phrase(value))
    return unique_nonempty(expanded)


def looks_like_population_term(term: str) -> bool:
    lowered = (term or "").strip().lower()
    if not lowered:
        return False
    return any(token in lowered for token in POPULATION_LIKE_TERMS)


def filter_exposure_terms_for_question_type(question_type: str, terms: list[str]) -> list[str]:
    clean = unique_nonempty(terms)
    if question_type != "treatment_strategy_comparison":
        return clean
    return [term for term in clean if not looks_like_population_term(term)]


def quoted(term: str) -> str:
    term = (term or "").strip()
    if not term:
        return ""
    if '"' in term:
        return term
    return f'"{term}"'


def boolean_group(terms: list[str], field_suffix: str = "") -> str:
    clean = [t for t in terms if t]
    if not clean:
        return ""
    pieces = [f"{quoted(term)}{field_suffix}" for term in clean]
    if len(pieces) == 1:
        return pieces[0]
    return "(" + " OR ".join(pieces) + ")"


def plain_group(terms: list[str]) -> str:
    clean = [quoted(term) for term in terms if term]
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    return "(" + " OR ".join(clean) + ")"


def join_and(parts: list[str]) -> str:
    clean = [part for part in parts if part]
    return " AND ".join(clean)


def contains_hint(text: str, hints: tuple[str, ...]) -> bool:
    lowered = (text or "").lower()
    return any(hint in lowered for hint in hints)


def infer_strategy_terms(cfg: dict, *texts: str) -> list[str]:
    """Return strategy comparison vocabulary for the query plan.

    If topic_config provides a ``strategy_vocabulary`` block with ``continue``
    and/or ``stop`` sub-lists, those override the hint-based inference so the
    caller can supply domain-appropriate synonyms without editing this file.
    """
    vocab = cfg.get("strategy_vocabulary") or {}
    if vocab:
        continue_v = list(vocab.get("continue") or [])
        stop_v = list(vocab.get("stop") or [])
        terms = continue_v + stop_v
        if terms:
            terms.extend(["versus", "comparison"])
            return unique_nonempty(terms)

    blob = " ".join(texts).lower()
    terms: list[str] = []
    if contains_hint(blob, CONTINUE_HINTS):
        terms.extend(["continuing", "continued use", "persistence"])
    if contains_hint(blob, STOP_HINTS):
        terms.extend(["discontinuation", "stopping", "cessation"])
    if terms:
        terms.extend(["versus", "comparison"])
    return unique_nonempty(terms)


def infer_trigger_terms(cfg: dict) -> list[str]:
    """Return clinical trigger vocabulary for the query plan.

    Terms are read exclusively from ``topic_config.json`` via the
    ``trigger_vocabulary`` list.  No domain-specific defaults are hard-coded
    here so the planner stays topic-agnostic.
    """
    vocab = cfg.get("trigger_vocabulary") or []
    return unique_nonempty(list(vocab))


def build_source_query(source: str, exposure_terms: list[str], outcome_terms: list[str], population_terms: list[str], extra_terms: list[str]) -> str:
    if source == "PubMed/MEDLINE":
        return join_and([
            boolean_group(exposure_terms, "[Title/Abstract]"),
            boolean_group(outcome_terms, "[Title/Abstract]"),
            boolean_group(population_terms, "[Title/Abstract]"),
            boolean_group(extra_terms, "[Title/Abstract]"),
        ])
    if source == "Embase":
        return join_and([
            boolean_group(exposure_terms, ":ti,ab"),
            boolean_group(outcome_terms, ":ti,ab"),
            boolean_group(population_terms, ":ti,ab"),
            boolean_group(extra_terms, ":ti,ab"),
        ])
    if source == "Web of Science":
        inner = join_and([
            plain_group(exposure_terms),
            plain_group(outcome_terms),
            plain_group(population_terms),
            plain_group(extra_terms),
        ])
        return f"TS=({inner})" if inner else ""
    if source == "Europe PMC":
        def _epmc_group(terms: list[str]) -> str:
            clean = [t for t in terms if t]
            if not clean:
                return ""
            pieces = [f'(TITLE:"{t}" OR ABSTRACT:"{t}")' for t in clean]
            if len(pieces) == 1:
                return pieces[0]
            return "(" + " OR ".join(pieces) + ")"
        return join_and([
            _epmc_group(exposure_terms),
            _epmc_group(outcome_terms),
            _epmc_group(population_terms),
            _epmc_group(extra_terms),
        ])
    # OpenAlex, Semantic Scholar, medRxiv, bioRxiv: plain free-text query
    return join_and([
        plain_group(exposure_terms),
        plain_group(outcome_terms),
        plain_group(population_terms),
        plain_group(extra_terms),
    ])


def default_date_limit(cfg: dict) -> str:
    time_range = cfg.get("time_range")
    if isinstance(time_range, list) and len(time_range) == 2:
        return f"{time_range[0]}-{time_range[1]}"
    return ""


def retrieval_target(base: int, review_goal: str) -> str:
    """Adjust recommended retrieval target based on review goal."""
    if review_goal == "background_landscape":
        return str(max(base, 50))
    if review_goal in {"decision_support", "protocol_support"}:
        return str(base)
    if review_goal == "gap_mapping":
        return str(base)
    return str(base)


def build_query_plan(cfg: dict) -> list[dict[str, str]]:
    exposure = (cfg.get("exposure") or "").strip()
    comparison = (cfg.get("comparison") or "").strip()
    outcome = (cfg.get("outcome") or "").strip()
    population = (cfg.get("population") or "").strip()
    design_type = (cfg.get("design_type") or "").strip()
    primary_estimand = (cfg.get("primary_estimand") or "").strip()
    mediator = (cfg.get("candidate_mediator") or "").strip()
    modifier = (cfg.get("candidate_modifier") or "").strip()
    confounders = cfg.get("confounders_core") or []
    harvest = cfg.get("harvest") or {}

    question_type = (cfg.get("question_type") or "").strip()
    review_goal = (cfg.get("review_goal") or "").strip()

    exposure_terms = filter_exposure_terms_for_question_type(
        question_type,
        concise_seed_terms([exposure, comparison]) + list(harvest.get("exposures") or []),
    )
    outcome_terms = unique_nonempty(
        expand_query_terms(outcome, harvest.get("outcome", "")) + list(harvest.get("outcomes") or [])
    )
    population_terms = unique_nonempty(
        expand_query_terms(population, harvest.get("population", ""))
    )
    if not outcome_terms and outcome:
        outcome_terms = [outcome]
    if not population_terms and population:
        population_terms = [population]

    # Strategy terms: only inferred when question_type is treatment_strategy_comparison,
    # or when the topic config text contains continuation/stopping language.
    if question_type == "treatment_strategy_comparison":
        strategy_terms = infer_strategy_terms(
            cfg, exposure, comparison, " ".join(harvest.get("exposures") or [])
        )
        if not strategy_terms:
            # Fallback: at least include generic strategy vocabulary
            strategy_terms = unique_nonempty(["continuing", "discontinuation", "versus", "comparison"])
    else:
        strategy_terms = infer_strategy_terms(
            cfg, exposure, comparison, " ".join(harvest.get("exposures") or [])
        )

    # Trigger terms: sourced exclusively from topic_config, no hardcoded defaults.
    trigger_terms = infer_trigger_terms(cfg)

    specific_outcomes = [
        term
        for term in outcome_terms
        if term.lower() not in {"clinical outcomes", "clinical outcome", "multiple clinical outcomes", "outcomes"}
    ]

    # Design terms for the design_estimand family are routed by question_type.
    # If question_type is absent, use only what the config explicitly provides.
    if question_type and question_type in QUESTION_TYPE_DESIGN_TERMS:
        type_design_terms = QUESTION_TYPE_DESIGN_TERMS[question_type]
    else:
        type_design_terms = []
    design_extra_terms = unique_nonempty([design_type, primary_estimand] + type_design_terms)

    plans = [
        {
            "search_round": "1",
            "parent_search_id": "",
            "concept_focus": "direct association",
            "query_family": "direct_association",
            "extra_terms": [],
            "recommended_retrieval_target": retrieval_target(40, review_goal),
            "rationale_trigger": "baseline field mapping",
            "scope": "map the main exposure-outcome literature",
        },
        {
            "search_round": "1",
            "parent_search_id": "",
            "concept_focus": "population and setting",
            "query_family": "population_setting",
            "extra_terms": population_terms[:3],
            "recommended_retrieval_target": retrieval_target(40, review_goal),
            "rationale_trigger": "baseline field mapping",
            "scope": "recover setting-specific and population-specific papers",
        },
        {
            "search_round": "1",
            "parent_search_id": "",
            "concept_focus": "measurement and validation",
            "query_family": "measurement_validation",
            "extra_terms": ["measurement", "validation", "scale", "instrument", "threshold"],
            "recommended_retrieval_target": retrieval_target(40, review_goal),
            "rationale_trigger": "baseline field mapping",
            "scope": "recover instrument, threshold, and psychometric evidence",
        },
        {
            "search_round": "1",
            "parent_search_id": "",
            "concept_focus": "design and estimand",
            "query_family": "design_estimand",
            "extra_terms": design_extra_terms,
            "recommended_retrieval_target": retrieval_target(40, review_goal),
            "rationale_trigger": "baseline field mapping",
            "scope": "recover design-specific methods and estimand choices",
        },
    ]

    # strategy_comparison is activated unconditionally when question_type is
    # treatment_strategy_comparison, or when strategy terms were inferred from the config text.
    if strategy_terms:
        strategy_extra = unique_nonempty(strategy_terms + ["target trial emulation", "grace period", "active comparator"])
        plans.append(
            {
                "search_round": "1",
                "parent_search_id": "",
                "concept_focus": "treatment strategy comparison",
                "query_family": "strategy_comparison",
                "extra_terms": strategy_extra,
                "recommended_retrieval_target": retrieval_target(30, review_goal),
                "rationale_trigger": "baseline field mapping for continuation versus discontinuation questions",
                "scope": "recover explicit continue-versus-stop comparative studies",
            }
        )

    if mediator or question_type == "mechanism_mediation":
        mechanism_extra = unique_nonempty([mediator, "mechanism", "mediation", "pathway"])
        plans.append(
            {
                "search_round": "2",
                "parent_search_id": "round1-anchor-reading",
                "concept_focus": "mechanism or mediation",
                "query_family": "mechanism_mediation",
                "extra_terms": mechanism_extra,
                "recommended_retrieval_target": "20",
                "rationale_trigger": "anchor papers suggested mediator or pathway language",
                "scope": "recover pathway evidence that sharpens interpretation boundaries",
            }
        )

    if modifier:
        plans.append(
            {
                "search_round": "2",
                "parent_search_id": "round1-anchor-reading",
                "concept_focus": "effect modification and subgroups",
                "query_family": "modifier_subgroup",
                "extra_terms": [modifier, "effect modification", "interaction", "subgroup"],
                "recommended_retrieval_target": "20",
                "rationale_trigger": "anchor papers suggested subgroup heterogeneity",
                "scope": "recover modifier and subgroup evidence",
            }
        )

    if confounders:
        plans.append(
            {
                "search_round": "2",
                "parent_search_id": "round1-anchor-reading",
                "concept_focus": "confounding structure",
                "query_family": "confounder_logic",
                "extra_terms": unique_nonempty(list(confounders)[:4] + ["confounding", "adjustment", "causal model"]),
                "recommended_retrieval_target": "20",
                "rationale_trigger": "anchor papers revealed dense confounding structure",
                "scope": "recover papers clarifying confounders, mediators, and colliders",
            }
        )

    if strategy_terms:
        trigger_extra = unique_nonempty(
            strategy_terms + trigger_terms + ["target trial emulation", "treatment strategy"]
        )
        plans.append(
            {
                "search_round": "2",
                "parent_search_id": "round1-anchor-reading",
                "concept_focus": "clinical trigger and treatment strategy",
                "query_family": "clinical_trigger_strategy",
                "extra_terms": trigger_extra,
                "recommended_retrieval_target": "20",
                "rationale_trigger": "anchor papers revealed a clinically triggered stop-versus-continue decision",
                "scope": "recover trigger-specific treatment strategy comparisons",
            }
        )

        for specific_outcome in specific_outcomes[:5]:
            plans.append(
                {
                    "search_round": "2",
                    "parent_search_id": "round1-anchor-reading",
                    "concept_focus": f"strategy comparison for outcome: {specific_outcome}",
                    "query_family": "outcome_specific_strategy",
                    "extra_terms": unique_nonempty([specific_outcome] + strategy_terms + trigger_terms),
                    "recommended_retrieval_target": "15",
                    "rationale_trigger": f"anchor reading suggested focused follow-up for outcome: {specific_outcome}",
                    "scope": "recover outcome-specific comparative strategy evidence",
                }
            )

    # gap_mapping goal boosts contradiction retrieval target
    contradiction_target = retrieval_target(30 if review_goal == "gap_mapping" else 20, review_goal)
    plans.append(
        {
            "search_round": "2",
            "parent_search_id": "round1-anchor-reading",
            "concept_focus": "contradictions and null findings",
            "query_family": "contradiction_null_findings",
            "extra_terms": ["null", "inconsistent", "contradictory", "heterogeneity"],
            "recommended_retrieval_target": contradiction_target,
            "rationale_trigger": "anchor reading should test whether only positive studies were captured",
            "scope": "recover contradictory findings and scope boundaries",
        }
    )

    plans.append(
        {
            "search_round": "3",
            "parent_search_id": "round2-synthesis-gap-check",
            "concept_focus": "citation chaining and landmark reviews",
            "query_family": "citation_chaining",
            "extra_terms": ["systematic review", "meta-analysis", "landmark review", "citation chaining"],
            "recommended_retrieval_target": "15",
            "rationale_trigger": "final gap check and reference chasing",
            "scope": "recover missing seminal papers and stabilize the evidence map",
        }
    )

    rows: list[dict[str, str]] = []
    date_limit = default_date_limit(cfg)
    search_id = 1
    for plan in plans:
        free_text_query = " ".join(
            part
            for part in [
                plain_group(exposure_terms),
                plain_group(outcome_terms),
                plain_group(population_terms),
                plain_group(plan["extra_terms"]),
            ]
            if part
        ).strip()

        # Determine which sources to include for this plan entry.
        # For clinical question types, preprints are restricted to Round 1
        # direct_association only; all other families and all Round 2/3 entries
        # use PRIMARY_SOURCES only.
        is_clinical = question_type in CLINICAL_QUESTION_TYPES
        family = plan["query_family"]
        rnd = str(plan["search_round"])
        include_preprints = not is_clinical  # default: preprints for non-clinical types
        if is_clinical:
            # Only include preprints in Round 1 direct_association
            include_preprints = (rnd == "1" and family == "direct_association")
        # Always skip preprints for certain families regardless of question type
        if family in PREPRINT_SKIP_FAMILIES:
            include_preprints = False

        sources_for_plan = list(PRIMARY_SOURCES)
        if include_preprints:
            sources_for_plan = sources_for_plan + list(PREPRINT_SOURCES)

        # Preprint retrieval target is lower than primary sources
        preprint_target = str(max(15, int(plan["recommended_retrieval_target"]) // 2))

        for source in sources_for_plan:
            row_retrieval_target = (
                preprint_target if source in PREPRINT_SOURCES
                else plan["recommended_retrieval_target"]
            )
            rows.append(
                {
                    "search_id": f"S{search_id:03d}",
                    "search_round": plan["search_round"],
                    "parent_search_id": plan["parent_search_id"],
                    "concept_focus": plan["concept_focus"],
                    "query_family": plan["query_family"],
                    "question_type": question_type,
                    "review_goal": review_goal,
                    "query": free_text_query,
                    "source": source,
                    "source_query": build_source_query(
                        source,
                        exposure_terms,
                        outcome_terms,
                        population_terms,
                        plan["extra_terms"],
                    ),
                    "date_searched": "",
                    "date_limit": date_limit,
                    "language_limit": "",
                    "recommended_retrieval_target": row_retrieval_target,
                    "n_retrieved": "",
                    "n_after_dedup": "",
                    "scope": plan["scope"],
                    "status": "planned",
                    "rationale_trigger": plan["rationale_trigger"],
                    "note": "",
                }
            )
            search_id += 1
    return rows


def build_strategy_markdown(cfg: dict, rows: list[dict[str, str]]) -> str:
    topic = cfg.get("topic", "study topic")
    question_type = (cfg.get("question_type") or "").strip()
    review_goal = (cfg.get("review_goal") or "").strip()
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row["search_round"], []).append(row)

    lines = [
        "# Search Strategy",
        "",
        f"**Topic:** {topic}",
    ]
    if question_type:
        lines.append(f"**Question type:** {question_type}")
    if review_goal:
        lines.append(f"**Review goal:** {review_goal}")
    lines.extend([
        "",
        "## Core Sources",
        "",
        "- OpenAlex (free, full-text unavailable; abstract via inverted index)",
        "- PubMed/MEDLINE (free; NCBI E-utilities; abstract + MeSH terms)",
        "- Semantic Scholar (free; add --ss-api-key for higher rate limits; abstract + open-access PDFs)",
        "- Europe PMC (free; EBI REST API; abstract + PMC open-access full text)",
        "- medRxiv (preprints; interval API + local keyword scoring)",
        "- bioRxiv (preprints; interval API + local keyword scoring)",
        "- Embase (subscription required; blocked_auth_required if credentials absent)",
        "- Web of Science (subscription required; blocked_auth_required if credentials absent)",
        "",
        "## Working Defaults",
        "",
        "- Round 1 broad mapping: target per source is set by retrieval_target() based on review_goal.",
        "- Read 12-20 anchor papers after deduplication before expanding.",
        "- Round 2 reading-driven expansion: about 20 records per triggered query family and source.",
        "- Round 3 citation chaining: about 15 targeted records per citation-focused family and source where applicable.",
        "",
    ])

    for round_id in sorted(grouped.keys(), key=int):
        lines.extend([f"## Round {round_id}", ""])
        seen_families: set[str] = set()
        for row in grouped[round_id]:
            family = row["query_family"]
            if family in seen_families:
                continue
            seen_families.add(family)
            lines.append(
                f"- `{family}`: {row['concept_focus']}; target {row['recommended_retrieval_target']} per source; trigger: {row['rationale_trigger']}."
            )
        lines.append("")

    lines.extend(
        [
            "## Logging Rule",
            "",
            "Log the actual source syntax, date searched, retrieval count, post-dedup count, and the reason a later-round query was added.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a multi-database iterative search plan from topic_config.json.")
    parser.add_argument("--topic-config", required=True, help="Path to topic_config.json")
    parser.add_argument("--output-dir", required=True, help="Directory to write search_strategy.md and search_log.csv")
    args = parser.parse_args()

    cfg = load_json(Path(args.topic_config))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = build_query_plan(cfg)
    write_csv(output_dir / "search_log.csv", rows, rows[0].keys() if rows else [])
    (output_dir / "search_strategy.md").write_text(build_strategy_markdown(cfg, rows), encoding="utf-8")


if __name__ == "__main__":
    main()
