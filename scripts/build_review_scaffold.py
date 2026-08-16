#!/usr/bin/env python3
"""Create a literature-review output scaffold.

All section headers in the narrative template are question_type-aware and
free of any domain-specific hardcoding (no statin, MACE, frailty, etc.).

If --topic-config is supplied, outcome family names are read from the config
and injected into the Outcome-Specific Interpretation section.  Otherwise
generic placeholders are used.

Usage:
    python build_review_scaffold.py <output_dir>
        [--topic-config topic_config.json]
        [--question-type treatment_strategy_comparison]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


# ---------------------------------------------------------------------------
# CSV headers — these define the canonical field order for every registry.
# Keep in sync with references/output_schema.md and validate_review_package.py
# ---------------------------------------------------------------------------

CSV_HEADERS: dict[str, str] = {
    "search_log.csv": (
        "search_id,search_round,parent_search_id,concept_focus,query_family,"
        "question_type,review_goal,query,source,source_query,date_searched,"
        "date_limit,language_limit,recommended_retrieval_target,n_retrieved,"
        "n_after_dedup,scope,status,rationale_trigger,note\n"
    ),
    "candidate_records_raw.csv": (
        "search_id,search_round,query_family,source,source_rank,title,authors,"
        "year,published_date,doi,url,abstract,publication_status,"
        "source_record_id,matched_query,local_relevance_score,strategy_match_score\n"
    ),
    "candidate_records_dedup.csv": (
        "search_id,search_round,query_family,source,source_rank,title,authors,"
        "year,published_date,doi,url,abstract,publication_status,"
        "source_record_id,matched_query,local_relevance_score,strategy_match_score\n"
    ),
    # scored_candidates.csv: produced by score_candidates.py (not a scaffold file)
    "screening_decisions.csv": (
        "paper_id,title,decision,screening_stage,role,reason,"
        "direct_question_match,design_integrity_ok,comparator_integrity_ok,"
        "time_zero_clear,prior_user_design,directness_tier,"
        "exclusion_reason_code,question_match_summary,include_in_synthesis,include_in_protocol\n"
    ),
    "study_registry.csv": (
        "paper_id,synthesis_tier,anchor_eligible,primary_role,secondary_role,"
        "publication_status,year,design,population,exposure,outcome,sample_size,"
        "setting,measures,core_findings,limitations,protocol_implication,"
        "suggested_methods,record_relevance,study_credibility,quality_signal,"
        "direct_question_match,design_integrity_ok,comparator_integrity_ok,"
        "time_zero_clear,prior_user_design,outcome_family,outcome_family_all,"
        "title,doi,authors\n"
    ),
    "measurement_registry.csv": (
        "construct,preferred_tool,evidence_role,reason_from_literature,"
        "key_example_paper_ids,supporting_evidence_row_ids,protocol_use,limitation_or_bias\n"
    ),
    "confounder_registry.csv": (
        "variable,classification,support_level,supporting_paper_ids,"
        "supporting_evidence_row_ids,rationale,recommended_main_model_role\n"
    ),
    "evidence_to_decision_table.csv": (
        "decision_id,decision,evidence_summary,supporting_paper_ids,"
        "supporting_evidence_row_ids,downstream_use,confidence\n"
    ),
    "effect_registry.csv": (
        "effect_id,study_id,paper_id,outcome_family,outcome,effect_measure,"
        "point_estimate,ci_lower,ci_upper,exposure_contrast,direction,effect_directness,"
        "supports_primary_direction_claim,population_subgroup,"
        "effect_trustworthiness,notes\n"
    ),
    # Unified claim_registry: merges both schema definitions from output_schema.md
    "claim_registry.csv": (
        "claim_id,outcome_family,claim_text,claim_type,allowed_strength,"
        "evidence_direction,anchor_required,supports_primary_direction_claim,"
        "eligible_anchor_paper_ids,supporting_paper_ids,counter_study_ids,"
        "supporting_evidence_row_ids,confidence,narrative_position,note\n"
    ),
    # Unified bias_registry: field names aligned with output_schema.md
    "bias_registry.csv": (
        "paper_id,bias_domain,severity,bias_direction,evidence_of_bias,reviewer_note\n"
    ),
    "quality_appraisal_registry.csv": (
        "paper_id,domain,judgment,raw_signal,evidence_source,note\n"
    ),
    "fulltext_inventory.csv": (
        "paper_id,title,doi,text_source,fulltext_status,open_access_url,source_file,"
        "deep_read_completed,deep_read_date,claim_bearing,note\n"
    ),
}

FILES: list[str] = [
    "review_contract.json",
    "search_log.csv",
    "candidate_records_raw.csv",
    "candidate_records_dedup.csv",
    "screening_decisions.csv",
    "study_registry.csv",
    "measurement_registry.csv",
    "confounder_registry.csv",
    "effect_registry.csv",
    "claim_registry.csv",
    "bias_registry.csv",
    "quality_appraisal_registry.csv",
    "fulltext_inventory.csv",
    "citation_registry.json",
    "evidence_to_decision_table.csv",
    "evidence_sufficiency_report.json",
    "methods_snapshot.json",
    "section_packets.json",
    "evidence_clusters.json",
    "publication_manifest.json",
    "delivery_quality_report.json",
    "review_briefing.md",
    "search_strategy.md",
    "research_gaps.md",
    "related_work.md",
    "protocol_inputs.json",
    "proposal_bridge.md",
]


# ---------------------------------------------------------------------------
# Outcome family helpers — question_type-aware, not domain-specific
# ---------------------------------------------------------------------------

QUESTION_TYPE_OUTCOME_SECTIONS: dict[str, list[str]] = {
    "treatment_strategy_comparison": [
        "Primary Outcome",
        "Secondary Outcomes",
        "Adverse Effects or Safety Outcomes",
        "Patient-Centered and Quality-of-Life Outcomes",
    ],
    "exposure_outcome_association": [
        "Primary Outcome",
        "Secondary Outcomes",
        "Effect Modification and Subgroups",
    ],
    "prognosis": [
        "Event-Free Survival or Time to Event",
        "Secondary Prognostic Outcomes",
        "Subgroup Variation",
    ],
    "diagnostic_measurement": [
        "Sensitivity and Specificity",
        "Positive and Negative Predictive Value",
        "Inter-Rater Reliability and Agreement",
    ],
    "mechanism_mediation": [
        "Primary Pathway Evidence",
        "Supporting Biological Mechanism Evidence",
        "Effect Mediated by Proposed Intermediary",
    ],
    "guideline_to_evidence": [
        "Guideline Recommendation vs Available Evidence",
        "Evidence Gaps Relative to Current Guidance",
    ],
    "methods_estimand": [
        "Target Trial Emulation Evidence",
        "Estimand Framework and Sensitivity Analyses",
    ],
}

GENERIC_OUTCOME_SECTIONS = [
    "Primary Outcome",
    "Secondary Outcomes",
]


def outcome_sections_for_type(question_type: str, outcome_families: list[str]) -> list[str]:
    """Return outcome section names: config-supplied families take priority,
    then question_type defaults, then generic."""
    if outcome_families:
        return outcome_families
    return QUESTION_TYPE_OUTCOME_SECTIONS.get(question_type, GENERIC_OUTCOME_SECTIONS)


# ---------------------------------------------------------------------------
# Narrative template builder — question_type-aware, domain-agnostic
# ---------------------------------------------------------------------------

def narrative_template(
    question_type: str,
    outcome_families: list[str],
    review_type: str = "structured_narrative",
) -> str:
    """Return the YAML front-matter + section skeleton for the narrative review.

    No statin-specific, disease-specific, or outcome-specific content is
    hardcoded here.  All outcome section headings come from the config or
    from question_type defaults.
    """
    sections_from_type = outcome_sections_for_type(question_type, outcome_families)
    outcome_section_md = "\n\n".join(
        f"## {name}\n\nTODO: for this outcome family — which studies provide direct evidence, "
        "which anchor them, how strong is the conclusion, and what is the main limitation?"
        for name in sections_from_type
    )

    intro_framing = {
        "treatment_strategy_comparison": (
            "TODO: explain the real-world decision burden, why strategy comparison "
            "cannot be replaced by general efficacy evidence, and what the target population needs."
        ),
        "exposure_outcome_association": (
            "TODO: explain the epidemiological significance of the exposure-outcome relationship, "
            "the population-level importance, and why this association warrants systematic review."
        ),
        "prognosis": (
            "TODO: explain the prognostic question, who it affects, and why current prognosis "
            "data are insufficient for clinical or public-health decision-making."
        ),
        "diagnostic_measurement": (
            "TODO: explain the diagnostic gap, what current measurement tools miss, "
            "and why a structured review of diagnostic accuracy evidence is needed."
        ),
        "mechanism_mediation": (
            "TODO: explain the mechanistic hypothesis, why pathway evidence matters "
            "for the broader research question, and what prior evidence is insufficient."
        ),
        "guideline_to_evidence": (
            "TODO: explain how the guideline recommendation arose, what evidence underpins it, "
            "and what evidence gaps challenge its current formulation."
        ),
    }.get(question_type, "TODO: explain the burden, importance, and why this question matters now.")

    decision_framing = {
        "treatment_strategy_comparison": (
            "TODO: explain why this is a strategy question — not just an efficacy or adherence question — "
            "and why existing literature on treatment initiation cannot directly answer it."
        ),
        "exposure_outcome_association": (
            "TODO: explain what designs and analytic approaches are needed to address confounding, "
            "reverse causation, and measurement error for this specific association."
        ),
    }.get(
        question_type,
        "TODO: explain why this question cannot be answered by adjacent or general literature.",
    )

    qt_label = question_type.replace("_", " ") if question_type else "the study question"
    methods_note = (
        f"Question type: `{qt_label}`" if question_type else "Question type: [set question_type in topic_config.json]"
    )

    review_label = {
        "structured_narrative": "Structured Narrative Review",
        "systematic_no_meta": "Systematic Review Without Meta-analysis",
        "systematic_meta": "Systematic Review and Meta-analysis",
    }[review_type]
    framework_note = {
        "structured_narrative": "SANRA is the narrative-quality aid; report the reproducible search and screening transparently.",
        "systematic_no_meta": "Report with PRISMA 2020/PRISMA-S and synthesize without meta-analysis using SWiM.",
        "systematic_meta": "Report with PRISMA 2020/PRISMA-S and prespecify the quantitative synthesis model.",
    }[review_type]

    return "\n".join([
        "---",
        f'title: "{review_label}"',
        "geometry: margin=1in",
        "fontsize: 12pt",
        'mainfont: "Times New Roman"',
        "---",
        "",
        "# Clinical or Scientific Importance and Review Question",
        "",
        f"<!-- {methods_note} -->",
        "",
        "## Why This Matters",
        "",
        intro_framing,
        "",
        "## Why This Cannot Be Answered by Adjacent Literature",
        "",
        decision_framing,
        "",
        "## Review Question and Target Outcome Families",
        "",
        "TODO: define the exact review question (population, exposure/comparison, outcomes, design scope).",
        "",
        "# Review Methods",
        "",
        f"TODO: {framework_note}",
        "Report databases, exact source-specific search strings, final search dates, restrictions,",
        "per-source yields, deduplication, two-stage screening, appraisal method, and synthesis method.",
        "",
        "# Evidence Map and Study Characteristics",
        "",
        "TODO: summarize the design, setting, sample, exposure/outcome measurement, adjustment set, and follow-up where applicable.",
        "",
        "| Study | Design and setting | Sample | Exposure/comparison | Outcome measure | Adjustment/follow-up | Main limitation |",
        "|---|---|---:|---|---|---|---|",
        "| TODO | TODO | TODO | TODO | TODO | TODO | TODO |",
        "",
        "# Effect Evidence Matrix",
        "",
        "TODO: report the main estimate and interval for each direct study; use NR only when the source genuinely does not report it.",
        "",
        "| Study | Design | Contrast | Outcome | Effect measure | Estimate (95% CI) | Risk-of-bias judgment |",
        "|---|---|---|---|---|---|---|",
        "| TODO | TODO | TODO | TODO | TODO | TODO | TODO |",
        "",
        "# Evidence Classification and Directness",
        "",
        "TODO: classify the evidence base by type before listing individual papers.",
        "Types might include: direct comparative studies, indirect supporting evidence,",
        "measurement-validation studies, systematic reviews or guidelines, mechanistic evidence.",
        "For each type, state what it can and cannot support for this specific question.",
        "",
        "# Direct Evidence",
        "",
        "TODO: synthesize only the strongest, closest-match evidence.",
        "Do not list papers one by one — synthesize across them by judgment:",
        "direction of evidence, consistency, main anchor studies, and collective limitation.",
        "",
        "# Broader Supporting Evidence",
        "",
        "TODO: group indirect or adjacent evidence into 2–4 clusters by theme.",
        "For each cluster: state what it contributes and what it cannot substitute.",
        "Do not annotate papers individually.",
        "",
        "# Outcome-Specific Interpretation",
        "",
        outcome_section_md,
        "",
        "# Risk of Bias, Heterogeneity, and Certainty",
        "",
        "TODO: give design-appropriate study-level judgments, explain heterogeneity by measurement/design/adjustment,",
        "identify counterevidence and plausible reporting/publication bias, and state outcome-specific certainty with reasons.",
        "Discuss only limitations that materially change interpretation strength.",
        "Focus on the bias types most relevant to this question type:",
        "  - For treatment_strategy_comparison: confounding by indication, time-zero issues, immortal time, prior-user bias",
        "  - For exposure_outcome_association: confounding, reverse causation, OR-as-RR, cross-sectional temporality",
        "  - For prognosis: competing risks, loss to follow-up, case-mix variation",
        "  - Adapt to the actual question_type.",
        "",
        "# Evidence Gaps and Research Implications",
        "",
        "## What Can Be Said Now",
        "",
        "TODO: state the most defensible conclusion — no stronger than the evidence allows.",
        "",
        "## What Should Not Be Overstated",
        "",
        "TODO: state what the current evidence does NOT justify — be explicit.",
        "",
        "## What Research Is Most Needed",
        "",
        "TODO: state the most important next-step evidence need and preferred study design.",
        "",
        "# Search and Screening Accounting",
        "",
        "TODO: keep this section brief (1–2 paragraphs) and factual.",
        "Report: databases searched, final date, inclusion criteria, records identified, duplicates removed,",
        "title/abstract and full-text screening totals, included studies, and full-text exclusions by reason.",
        "Do not let this section organize the review or appear before the evidence synthesis.",
        "",
        "# References",
        "",
    ])


# ---------------------------------------------------------------------------
# Methods snapshot template
# ---------------------------------------------------------------------------

METHODS_SNAPSHOT_TEMPLATE = {
    "_instructions": (
        "Fill this file before writing the narrative. "
        "build_review_narrative.py and the narrative LLM read from here. "
        "This is an internal intermediate file — not a user-facing deliverable."
    ),
    "review_question": "",
    "review_type": "structured_narrative",
    "reporting_framework": ["SANRA"],
    "synthesis_method": "thematic synthesis by design, outcome, and directness",
    "databases_searched": [],
    "search_dates": {},
    "date_limits": "",
    "language_limits": "No restriction (or specify)",
    "inclusion_criteria": [],
    "exclusion_criteria": [],
    "screening_process": "",
    "fulltext_availability_limitations": "",
    "quality_appraisal_framework": "scoring_rubric.md + study_quality_framework.md",
    "prisma_counts": {
        "identified_total": 0,
        "after_dedup": 0,
        "title_abstract_screened": 0,
        "fulltext_assessed": 0,
        "included": 0,
        "excluded_reasons": {},
    },
    "access_limitations": [],
}


# ---------------------------------------------------------------------------
# Section packets template
# ---------------------------------------------------------------------------

SECTION_PACKETS_TEMPLATE = {
    "_instructions": (
        "One entry per narrative section. "
        "Generated by build_review_narrative.py or manually from scored_candidates.csv. "
        "Consumed by the LLM when drafting each section individually. "
        "Each section should be drafted independently before global revision."
    ),
    "packets": [
        {
            "section_id": "direct_evidence",
            "section_name": "Direct Evidence",
            "section_goal": "Synthesize only the strongest exact-match or near-exact-match evidence",
            "allowed_strength_ceiling": "suggestive",
            "anchor_paper_ids": [],
            "supporting_cluster_ids": [],
            "forbidden_paper_ids": [],
            "must_mention_limitations": [],
            "expected_outcome_families": [],
            "anti_repetition_blacklist": [],
        },
        {
            "section_id": "indirect_evidence",
            "section_name": "Broader Supporting Evidence",
            "section_goal": "Group indirect evidence into 2-4 clusters by theme; state what each adds and cannot substitute",
            "allowed_strength_ceiling": "preliminary",
            "anchor_paper_ids": [],
            "supporting_cluster_ids": [],
            "forbidden_paper_ids": [],
            "must_mention_limitations": [],
            "expected_outcome_families": [],
            "anti_repetition_blacklist": [],
        },
    ],
}


# ---------------------------------------------------------------------------
# Search strategy template — lists all current core sources
# ---------------------------------------------------------------------------

SEARCH_STRATEGY_TEMPLATE = """# Search Strategy

## Core Sources

| Source | Access | Notes |
|---|---|---|
| OpenAlex | Free | Abstract only (inverted index); no full text |
| PubMed/MEDLINE | Free | NCBI E-utilities |
| Semantic Scholar | Free | Graph API; open-access PDF links for subset |
| Europe PMC | Free | EBI REST API; MEDLINE + PMC + preprints |
| medRxiv | Free | Preprints; interval API + local keyword scoring |
| bioRxiv | Free | Preprints; interval API + local keyword scoring |
| Embase | Subscription | Blocked unless institutional credentials provided |
| Web of Science | Subscription | Blocked unless institutional credentials provided |

## Round Structure

1. Round 1 broad mapping: direct association, population/setting, measurement, and design queries across the core sources.
2. Read anchor papers: identify better terminology, instruments, mechanisms, conflicting findings, and boundary conditions.
3. Run `score_candidates.py` to assign 4-dimensional scores (record_relevance, study_credibility, likely_directness, decision_role).
4. Round 2 expansion: add reading-driven queries triggered by the anchor papers.
5. Run `chase_citations.py` on high-scoring anchors (record_relevance ≥ 4) for forward + backward citation graph expansion.
6. Round 3 citation chaining: cited-by, reference chasing, and contradiction-focused follow-up.

## Default Volume Targets

- Round 1: inspect about 30-50 ranked records per core source; 40 is a good default target.
- Read at least 12-20 anchor papers (record_relevance ≥ 4) after deduplication before Round 2.
- Round 2: inspect about 15-30 records per triggered query family and source.
- Citation chase: up to 30 new records per anchor (forward + backward combined).
- Stop when an additional expansion cycle no longer changes downstream decisions.

## Logging Rule

For each query, log: search_round, parent_search_id, query_family, source, source_query,
date_searched, retrieval counts, and rationale_trigger in search_log.csv.

TODO: fill in actual search dates and retrieval counts as the review progresses.
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a literature-review output scaffold.",
    )
    parser.add_argument("output_dir", help="Directory for review artifacts")
    parser.add_argument(
        "--topic-config",
        default="",
        help="Optional path to topic_config.json; used to inject outcome family names into the narrative template",
    )
    parser.add_argument(
        "--review-type",
        choices=["structured_narrative", "systematic_no_meta", "systematic_meta"],
        default="",
        help="Product type; topic_config.review_type takes precedence when present",
    )
    parser.add_argument(
        "--question-type",
        default="",
        help="Override question_type (treatment_strategy_comparison / exposure_outcome_association / ...); "
        "ignored if topic_config.json already contains question_type",
    )
    args = parser.parse_args()

    root = Path(args.output_dir)
    root.mkdir(parents=True, exist_ok=True)

    # Resolve question_type and outcome families from config or CLI
    cfg: dict = {}
    if args.topic_config:
        cfg = load_json(Path(args.topic_config))
    question_type = cfg.get("question_type") or args.question_type or ""
    review_type = cfg.get("review_type") or args.review_type or "structured_narrative"
    if review_type not in {"structured_narrative", "systematic_no_meta", "systematic_meta"}:
        raise SystemExit(f"Unsupported review_type: {review_type}")
    harvest = cfg.get("harvest") or {}
    outcome_families = [o for o in (harvest.get("outcomes") or []) if o]

    # Create skeleton files
    for name in FILES:
        path = root / name
        if path.exists():
            existing = path.read_text(encoding="utf-8").strip()
            if existing and existing not in ("{}", "{}"):
                continue  # Never overwrite non-empty files
        if name in CSV_HEADERS:
            path.write_text(CSV_HEADERS[name], encoding="utf-8")
        elif name.endswith(".json"):
            path.write_text("{}\n", encoding="utf-8")
        else:
            path.write_text("", encoding="utf-8")

    contract_path = root / "review_contract.json"
    if contract_path.read_text(encoding="utf-8").strip() in ("{}", ""):
        frameworks = {
            "structured_narrative": ["SANRA"],
            "systematic_no_meta": ["PRISMA 2020", "PRISMA-S", "SWiM"],
            "systematic_meta": ["PRISMA 2020", "PRISMA-S"],
        }[review_type]
        synthesis_methods = {
            "structured_narrative": "thematic critical synthesis by design, outcome, and directness",
            "systematic_no_meta": "SWiM synthesis by design, outcome, directness, and effect direction without significance vote counting",
            "systematic_meta": "quantitative meta-analysis; specify effect harmonization, model, heterogeneity, and sensitivity analyses before release",
        }
        contract_template = {
            "contract_version": "3.0",
            "review_type": review_type,
            "reporting_framework": frameworks,
            "synthesis_method": synthesis_methods[review_type],
            "project_mode": cfg.get("project_mode", "research"),
            "question_type": question_type,
            "review_goal": cfg.get("review_goal", "protocol_support"),
            "delivery_preset": cfg.get("delivery_preset", "decision_grade"),
            "design_type": cfg.get("design_type", "cross_sectional"),
            "generated_at": "",
            "status": "draft",
            "downgrade_state": "",
            "topic": cfg.get("topic", ""),
            "primary_estimand": cfg.get("primary_estimand", ""),
            "evidence_sufficiency": "not_assessed",
            "decision_ids": [],
            "citation_ids": [],
            "older_search_cutoff_disclosed": False,
            "sparse_evidence_exception": {"applies": False},
            "deliverable_style": "narrative_review",
            "narrative_readiness": "draft",
            "anchor_density_by_outcome": {},
        }
        contract_path.write_text(json.dumps(contract_template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # search_strategy.md
    search_md = root / "search_strategy.md"
    if not search_md.exists() or not search_md.read_text(encoding="utf-8").strip():
        search_md.write_text(SEARCH_STRATEGY_TEMPLATE, encoding="utf-8")

    # literature_review_synthesis.md — question_type-aware, domain-agnostic
    review_md = root / "literature_review_synthesis.md"
    if not review_md.exists():
        review_md.write_text(narrative_template(question_type, outcome_families, review_type), encoding="utf-8")

    # review_briefing.md placeholder
    briefing_md = root / "review_briefing.md"
    if not briefing_md.exists() or not briefing_md.read_text(encoding="utf-8").strip():
        briefing_md.write_text(
            "# Review Briefing\n\nGenerated by `build_review_narrative.py`.\n\n"
            "This file is a pipeline-facing evidence map and writing input.\n"
            "Do not copy its language into `literature_review_synthesis.md`.\n",
            encoding="utf-8",
        )

    # proposal_bridge.md placeholder
    proposal_md = root / "proposal_bridge.md"
    if not proposal_md.exists() or not proposal_md.read_text(encoding="utf-8").strip():
        proposal_md.write_text(
            "\n".join([
                "# Proposal Bridge",
                "",
                "## Research Problem and Significance",
                "",
                "TODO: state why the topic matters now in scientific or public-health terms.",
                "",
                "## Current Evidence and Stable Findings",
                "",
                "TODO: summarize what the literature already supports with reasonable confidence.",
                "",
                "## Gap Statement",
                "",
                "TODO: define the unresolved gap precisely rather than claiming generic novelty.",
                "",
                "## Proposed Question Lock",
                "",
                "TODO: lock population, exposure, comparison, outcome, and primary estimand.",
                "",
                "## Measurement and Variable Feasibility",
                "",
                "TODO: justify why the planned variables and tools are actually measurable.",
                "",
                "## Confounder and Mechanism Boundary",
                "",
                "TODO: state the minimal sufficient adjustment logic and what stays out of the primary model.",
                "",
                "## Risks and Downgrade Triggers",
                "",
                "TODO: state what would weaken the proposal or force a narrower claim.",
                "",
            ]) + "\n",
            encoding="utf-8",
        )

    # methods_snapshot.json — structured intermediate for narrative methods section
    methods_path = root / "methods_snapshot.json"
    if not methods_path.exists() or methods_path.read_text(encoding="utf-8").strip() in ("{}", "{}"):
        methods_template = dict(METHODS_SNAPSHOT_TEMPLATE)
        methods_template["review_type"] = review_type
        methods_template["reporting_framework"] = {
            "structured_narrative": ["SANRA"],
            "systematic_no_meta": ["PRISMA 2020", "PRISMA-S", "SWiM"],
            "systematic_meta": ["PRISMA 2020", "PRISMA-S"],
        }[review_type]
        methods_path.write_text(json.dumps(methods_template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # section_packets.json — intermediate input for per-section LLM drafting
    packets_path = root / "section_packets.json"
    if not packets_path.exists() or packets_path.read_text(encoding="utf-8").strip() in ("{}", "{}"):
        packets_path.write_text(json.dumps(SECTION_PACKETS_TEMPLATE, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # evidence_clusters.json — groups indirect evidence by theme for cluster-based synthesis
    clusters_path = root / "evidence_clusters.json"
    if not clusters_path.exists() or clusters_path.read_text(encoding="utf-8").strip() in ("{}", "{}"):
        clusters_template = {
            "_instructions": (
                "Group indirect evidence into 2-4 thematic clusters. "
                "Populated by build_methods_snapshot.py after scored_candidates.csv is filled. "
                "Consumed by the LLM when drafting the Broader Supporting Evidence section. "
                "The LLM writes ONE paragraph per cluster — not one paragraph per paper."
            ),
            "clusters": [
                {
                    "cluster_id": "C1",
                    "theme": "TODO: name the first evidence cluster (e.g., 'initiation/efficacy evidence')",
                    "member_paper_ids": [],
                    "what_this_cluster_can_support": "TODO: state what this cluster can contribute",
                    "what_it_cannot_support": "TODO: state what this cluster cannot substitute",
                    "preferred_anchor_ids": [],
                    "synthesis_note": "TODO: 1-2 sentence synthesis of what this cluster collectively says",
                },
            ],
        }
        clusters_path.write_text(json.dumps(clusters_template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"[build_review_scaffold] Scaffold ready at: {root}")
    if question_type:
        print(f"  question_type: {question_type}")
    print(f"  review_type: {review_type}")
    if outcome_families:
        print(f"  outcome families injected: {', '.join(outcome_families)}")
    else:
        print("  outcome families: using question_type defaults (supply --topic-config to customise)")


if __name__ == "__main__":
    main()
