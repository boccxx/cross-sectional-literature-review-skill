#!/usr/bin/env python3
"""Build methods_snapshot.json and section_packets.json from existing review artifacts.

methods_snapshot.json provides the structured methods description that the narrative LLM
needs to write a complete, accurate Search and Screening section without guessing.

section_packets.json provides per-section drafting instructions that prevent the LLM
from writing template-style prose: each section has a goal, allowed_strength_ceiling,
anchor_paper_ids, and an anti_repetition_blacklist.

Usage:
    python build_methods_snapshot.py \\
        --review-dir ./literature_review \\
        [--topic-config topic_config.json]

Outputs:
    methods_snapshot.json      — structured methods data for narrative Methods section
    section_packets.json       — per-section drafting packets for LLM-guided writing
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path


def load_json(path: Path) -> dict | list:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def build_methods_snapshot(
    review_dir: Path,
    cfg: dict,
) -> dict:
    """Build methods_snapshot from search_log.csv and screening_decisions.csv."""
    search_log = read_csv(review_dir / "search_log.csv")
    screening = read_csv(review_dir / "screening_decisions.csv")
    candidate_raw = read_csv(review_dir / "candidate_records_raw.csv")
    candidate_dedup = read_csv(review_dir / "candidate_records_dedup.csv")
    study_registry = read_csv(review_dir / "study_registry.csv")
    review_contract = load_json(review_dir / "review_contract.json")

    # Databases searched
    sources_searched: dict[str, dict] = {}
    for row in search_log:
        source = normalize(row.get("source") or "")
        status = normalize(row.get("status") or "")
        date_s = normalize(row.get("date_searched") or "")
        if not source:
            continue
        if source not in sources_searched:
            sources_searched[source] = {"status": status, "date_searched": date_s}
        elif date_s and not sources_searched[source]["date_searched"]:
            sources_searched[source]["date_searched"] = date_s

    db_list = [
        {"source": s, "status": info["status"], "date_searched": info["date_searched"]}
        for s, info in sorted(sources_searched.items())
    ]

    search_date_map = {
        item["source"]: item["date_searched"]
        for item in db_list
        if item["date_searched"]
    }

    # Date limits from search_log
    date_limits_set = {
        normalize(row.get("date_limit") or "")
        for row in search_log
        if row.get("date_limit")
    }
    date_limits = "; ".join(sorted(date_limits_set)) or ""

    # PRISMA counts
    n_identified = len(candidate_raw)
    n_dedup = len(candidate_dedup)
    n_screened = len([r for r in screening if r.get("decision")])
    n_excluded_title_abstract = len(
        [r for r in screening if (r.get("screening_stage") or "") in ("title_abstract", "title-abstract")]
    )
    n_fulltext_assessed = len(
        [r for r in screening if (r.get("screening_stage") or "") in ("fulltext", "full_text")]
    )
    included_rows = [
        r for r in screening
        if (r.get("include_in_synthesis") or "").strip().lower() in ("yes", "true", "1")
    ]
    n_included = len(included_rows)
    if n_included == 0:
        # Fallback: count study_registry entries
        n_included = len([r for r in study_registry if r.get("paper_id")])

    # Exclusion reasons
    exclusion_reasons: dict[str, int] = defaultdict(int)
    for r in screening:
        if (r.get("decision") or "").strip().lower() in ("exclude", "excluded"):
            reason = normalize(r.get("exclusion_reason_code") or r.get("reason") or "not_stated")
            exclusion_reasons[reason] += 1

    # Inclusion criteria from topic_config
    harvest = cfg.get("harvest") or {}
    population = cfg.get("population") or ""
    exposure = cfg.get("exposure") or ""
    outcome = cfg.get("outcome") or ""
    question_type = cfg.get("question_type") or ""
    design_type = cfg.get("design_type") or ""

    inclusion_criteria: list[str] = []
    if population:
        inclusion_criteria.append(f"Population: {population}")
    if exposure:
        inclusion_criteria.append(f"Exposure/intervention: {exposure}")
    if outcome:
        inclusion_criteria.append(f"Outcome: {outcome}")
    if design_type:
        inclusion_criteria.append(f"Study design: {design_type}")

    # Language limits from search_log
    lang_limits_set = {
        normalize(row.get("language_limit") or "")
        for row in search_log
        if row.get("language_limit")
    }
    language_limits = "; ".join(sorted(lang_limits_set)) or "No language restriction specified"

    # Access limitations
    access_limitations: list[str] = []
    for row in search_log:
        if (row.get("status") or "").startswith("blocked"):
            access_limitations.append(
                f"{row['source']}: {row.get('status', '')} — {normalize(row.get('note', ''))}"
            )

    snapshot = {
        "_generated": date.today().isoformat(),
        "_instructions": (
            "This file is an internal intermediate — not a user-facing deliverable. "
            "The narrative LLM reads from here to write the Search and Screening section. "
            "Fill any TODO fields before running the narrative generation step."
        ),
        "review_question": (
            f"{exposure} vs comparison in {population}: effect on {outcome}"
            if (exposure and population and outcome)
            else cfg.get("topic") or "TODO: state the review question"
        ),
        "question_type": question_type,
        "review_type": (
            review_contract.get("review_type")
            if isinstance(review_contract, dict)
            else cfg.get("review_type")
        ) or cfg.get("review_type") or "structured_narrative",
        "reporting_framework": (
            review_contract.get("reporting_framework", [])
            if isinstance(review_contract, dict)
            else []
        ),
        "synthesis_method": (
            review_contract.get("synthesis_method", "")
            if isinstance(review_contract, dict)
            else ""
        ),
        "databases_searched": db_list,
        "executed_searches": [
            {
                "search_id": normalize(row.get("search_id") or ""),
                "source": normalize(row.get("source") or ""),
                "source_query": row.get("source_query") or row.get("query") or "",
                "date_searched": normalize(row.get("date_searched") or ""),
                "n_retrieved": normalize(row.get("n_retrieved") or ""),
                "n_after_dedup": normalize(row.get("n_after_dedup") or ""),
                "status": normalize(row.get("status") or ""),
            }
            for row in search_log
            if normalize(row.get("status") or "").lower() in {"retrieved", "completed", "complete", "success", "executed"}
        ],
        "search_dates": search_date_map,
        "date_limits": date_limits or "TODO: specify date range",
        "language_limits": language_limits,
        "inclusion_criteria": inclusion_criteria or ["TODO: list inclusion criteria"],
        "exclusion_criteria": ["TODO: list exclusion criteria"],
        "screening_process": (
            "Two-stage screening: title/abstract followed by full-text review. "
            "TODO: describe who screened and how disagreements were resolved."
        ),
        "fulltext_availability_limitations": (
            "TODO: describe any full-text access constraints "
            "(e.g., subscription-only journals, preprints without peer review)."
        ),
        "quality_appraisal_framework": "scoring_rubric.md + study_quality_framework.md",
        "prisma_counts": {
            "identified_total": n_identified,
            "after_dedup": n_dedup,
            "title_abstract_screened": n_screened,
            "fulltext_assessed": n_fulltext_assessed,
            "included": n_included,
            "excluded_reasons": dict(exclusion_reasons),
        },
        "access_limitations": access_limitations,
    }
    return snapshot


def build_section_packets(
    review_dir: Path,
    cfg: dict,
    question_type: str,
) -> dict:
    """Build section_packets.json from scored_candidates.csv and study_registry.csv."""
    scored = read_csv(review_dir / "scored_candidates.csv")
    study_reg = read_csv(review_dir / "study_registry.csv")

    # Identify anchor papers: record_relevance >= 4 and decision_role = anchor
    anchor_ids: list[str] = []
    direct_ids: list[str] = []
    indirect_ids: list[str] = []
    methods_ids: list[str] = []

    for row in scored:
        pid = (row.get("paper_id") or "").strip()
        if not pid:
            continue
        try:
            rel = int(float(row.get("record_relevance") or 0))
        except (ValueError, TypeError):
            rel = 0
        role = (row.get("decision_role") or "").strip().lower()
        directness = (row.get("likely_directness") or "").strip().lower()
        include = (row.get("include_in_review") or "").strip().lower()

        if include == "no":
            continue
        if role == "anchor":
            anchor_ids.append(pid)
        if directness == "direct":
            direct_ids.append(pid)
        elif directness == "indirect":
            indirect_ids.append(pid)
        elif directness == "background" or role == "methods":
            methods_ids.append(pid)

    # Fallback when scored_candidates.csv not yet filled: use study_registry tiers
    if not anchor_ids and study_reg:
        for row in study_reg:
            pid = (row.get("paper_id") or "").strip()
            tier = (row.get("synthesis_tier") or "").strip()
            eligible = (row.get("anchor_eligible") or "").strip().lower()
            if tier in ("core_direct_strict", "core_direct_broad") and eligible == "yes":
                anchor_ids.append(pid)
            elif tier == "core_direct_broad":
                direct_ids.append(pid)
            elif tier == "indirect_support":
                indirect_ids.append(pid)

    # Outcome families
    harvest = cfg.get("harvest") or {}
    outcome_families = list(harvest.get("outcomes") or [])
    if not outcome_families and cfg.get("outcome"):
        outcome_families = [cfg["outcome"]]

    # Bias types for this question_type
    bias_by_type = {
        "treatment_strategy_comparison": [
            "confounding by indication",
            "immortal time bias",
            "prevalent user bias",
            "time-zero alignment",
            "informative censoring",
        ],
        "exposure_outcome_association": [
            "confounding",
            "reverse causation",
            "OR as RR with common outcome",
            "cross-sectional temporality",
            "overadjustment",
        ],
        "prognosis": [
            "competing risks",
            "loss to follow-up",
            "case-mix variation",
            "outcome ascertainment differences",
        ],
    }
    relevant_biases = bias_by_type.get(question_type, ["confounding", "selection bias", "information bias"])

    packets: list[dict] = [
        {
            "section_id": "evidence_classification",
            "section_name": "Evidence Classification",
            "section_goal": (
                "Classify the evidence base by type before any individual papers are discussed. "
                "State what each type can and cannot support for this specific question."
            ),
            "allowed_strength_ceiling": "background_only",
            "anchor_paper_ids": [],
            "supporting_cluster_ids": [],
            "forbidden_paper_ids": [],
            "must_mention_limitations": [],
            "expected_outcome_families": [],
            "anti_repetition_blacklist": [
                "Study X found",
                "Study Y found",
                "Study Z found",
                "contributes to the mapped evidence",
            ],
            "drafting_note": (
                "This section should organise the evidence TYPES, not list papers. "
                "Each type entry: name, definition, count in this review, what it can/cannot say."
            ),
        },
        {
            "section_id": "direct_evidence",
            "section_name": "Direct Evidence",
            "section_goal": (
                "Synthesize only the strongest closest-match evidence. "
                "Provide a thematic judgment — direction, consistency, magnitude range, main anchor — "
                "rather than listing individual papers."
            ),
            "allowed_strength_ceiling": "suggestive",
            "anchor_paper_ids": anchor_ids[:5],
            "supporting_cluster_ids": [],
            "forbidden_paper_ids": indirect_ids + methods_ids,
            "must_mention_limitations": relevant_biases[:2],
            "expected_outcome_families": outcome_families,
            "anti_repetition_blacklist": [
                "Study X found",
                "In a cohort study,",
                "In an observational study,",
                "Using a retrospective design,",
            ],
            "drafting_note": (
                "Lead with the collective judgment. Mention at most 2 anchor studies by name. "
                "End with the main methodological limitation that constrains interpretation."
            ),
        },
        {
            "section_id": "indirect_evidence",
            "section_name": "Broader Supporting Evidence",
            "section_goal": (
                "Group indirect evidence into 2–4 thematic clusters. "
                "For each cluster state what it adds and what it cannot substitute for direct evidence."
            ),
            "allowed_strength_ceiling": "preliminary",
            "anchor_paper_ids": indirect_ids[:8],
            "supporting_cluster_ids": [],
            "forbidden_paper_ids": anchor_ids,
            "must_mention_limitations": ["indirect nature of evidence"],
            "expected_outcome_families": [],
            "anti_repetition_blacklist": [
                "provides indirect support",
                "also provides indirect support",
                "similarly provides",
                "Study X provides",
            ],
            "drafting_note": (
                "Do not write one paragraph per paper. Write one paragraph per CLUSTER. "
                "Suggested cluster structure: "
                "(1) initiation/efficacy evidence, "
                "(2) special subgroup evidence, "
                "(3) adherence/persistence descriptors, "
                "(4) guidelines or protocol evidence. "
                "Adapt to the actual question."
            ),
        },
        {
            "section_id": "methodological_challenges",
            "section_name": "Methodological Challenges",
            "section_goal": (
                "Discuss only the limitations that materially change interpretation strength. "
                "Be specific to this question type and the actual studies reviewed."
            ),
            "allowed_strength_ceiling": "background_only",
            "anchor_paper_ids": [],
            "supporting_cluster_ids": [],
            "forbidden_paper_ids": [],
            "must_mention_limitations": relevant_biases,
            "expected_outcome_families": [],
            "anti_repetition_blacklist": [
                "As with all observational studies",
                "Like all retrospective studies",
                "This is a limitation of all",
            ],
            "drafting_note": (
                "Each limitation entry: name it, explain why it is specifically relevant here, "
                "and state what it means for interpretation. "
                "Do not list generic observational-study limitations without explaining their specific impact."
            ),
        },
    ]

    # Add per-outcome-family packets
    for outcome_fam in outcome_families[:5]:
        # Find papers for this outcome
        outcome_anchor_ids = [
            row.get("paper_id", "")
            for row in study_reg
            if outcome_fam.lower() in (row.get("outcome_family_all") or row.get("outcome_family") or "").lower()
            and row.get("paper_id")
        ]
        packets.append({
            "section_id": f"outcome_{re.sub(r'[^a-z0-9]+', '_', outcome_fam.lower())}",
            "section_name": outcome_fam,
            "section_goal": (
                f"For {outcome_fam}: which studies provide direct evidence, "
                "which anchor them, how strong is the conclusion, and what is the main limitation."
            ),
            "allowed_strength_ceiling": "suggestive",
            "anchor_paper_ids": outcome_anchor_ids[:4],
            "supporting_cluster_ids": [],
            "forbidden_paper_ids": [],
            "must_mention_limitations": [],
            "expected_outcome_families": [outcome_fam],
            "anti_repetition_blacklist": [],
            "drafting_note": (
                "If there is no direct evidence for this outcome, say so in one sentence "
                "and explain what indirect evidence suggests (if any). "
                "Do not write a long paragraph that just repeats 'evidence is limited'."
            ),
        })

    return {
        "_generated": date.today().isoformat(),
        "_instructions": (
            "One entry per narrative section. "
            "The LLM drafts each section individually using anchor_paper_ids and anti_repetition_blacklist. "
            "After individual sections are drafted, run a global revision pass to "
            "remove cross-section repetition and verify claim ceilings."
        ),
        "packets": packets,
    }


def build_evidence_clusters(review_dir: Path, cfg: dict) -> dict:
    """Build evidence_clusters.json grouping indirect evidence by thematic cluster.

    Clusters are derived from scored_candidates.csv and study_registry.csv using
    query_family, outcome_family, and synthesis_tier.  The LLM writes ONE paragraph
    per cluster when drafting the Broader Supporting Evidence section.
    """
    scored_csv = review_dir / "scored_candidates.csv"
    study_csv = review_dir / "study_registry.csv"
    scored: list[dict] = read_csv(scored_csv)
    study_reg: list[dict] = read_csv(study_csv)

    # Identify indirect papers — those NOT in study_registry anchor tier
    anchor_ids = {
        r.get("paper_id", "").strip()
        for r in study_reg
        if (r.get("synthesis_tier") or "").lower() in ("core_direct_strict", "core_direct_broad")
        or (r.get("anchor_eligible") or "").lower() == "yes"
    }

    indirect_scored = [
        r for r in scored
        if r.get("paper_id", "").strip() not in anchor_ids
        and (r.get("decision_role") or "").lower() in ("support", "background", "methods")
        and (r.get("include_in_review") or "").lower() in ("yes", "maybe")
    ]

    # Group by query_family as a first-pass clustering proxy
    from collections import defaultdict
    clusters_by_family: dict[str, list[str]] = defaultdict(list)
    for r in indirect_scored:
        qf = (r.get("query_family") or "general").strip().lower()
        pid = r.get("paper_id", "").strip()
        if pid:
            clusters_by_family[qf].append(pid)

    # If scored_candidates lacks data, fall back to study_registry indirect papers
    if not clusters_by_family:
        for r in study_reg:
            tier = (r.get("synthesis_tier") or "").lower()
            if tier in ("supporting", "indirect", "background_policy", "appendix_only"):
                qf = (r.get("outcome_family") or "general").strip().lower()
                pid = r.get("paper_id", "").strip()
                if pid:
                    clusters_by_family[qf].append(pid)

    clusters = []
    for idx, (family, pids) in enumerate(list(clusters_by_family.items())[:5], start=1):
        # Clean up family name for display
        display_name = family.replace("_", " ").title()
        clusters.append({
            "cluster_id": f"C{idx}",
            "theme": display_name,
            "member_paper_ids": pids[:8],
            "what_this_cluster_can_support": (
                "TODO: state what this cluster can contribute to the narrative "
                "(e.g., plausibility, effect size estimates, subgroup context)"
            ),
            "what_it_cannot_support": (
                "TODO: state what this cluster cannot substitute for "
                "(e.g., 'cannot substitute for direct continue vs stop comparisons')"
            ),
            "preferred_anchor_ids": pids[:2],
            "synthesis_note": (
                f"TODO: write a 1–2 sentence synthesis of what these {len(pids)} papers "
                f"collectively suggest about {display_name}"
            ),
        })

    if not clusters:
        clusters = [{
            "cluster_id": "C1",
            "theme": "General indirect support",
            "member_paper_ids": [],
            "what_this_cluster_can_support": "TODO",
            "what_it_cannot_support": "TODO",
            "preferred_anchor_ids": [],
            "synthesis_note": "TODO: fill after screening is complete",
        }]

    return {
        "_generated": date.today().isoformat(),
        "_instructions": (
            "One entry per indirect evidence cluster. "
            "Populated automatically from scored_candidates.csv query_family groupings. "
            "Review and edit the TODO fields before narrative drafting. "
            "The LLM writes ONE paragraph per cluster — not one paragraph per paper. "
            "Each paragraph: state what the cluster suggests → what it cannot replace → bounded interpretation."
        ),
        "clusters": clusters,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build methods_snapshot.json and section_packets.json from review artifacts.",
    )
    parser.add_argument("--review-dir", required=True, help="Path to the literature_review directory")
    parser.add_argument("--topic-config", default="", help="Optional path to topic_config.json")
    parser.add_argument("--force", action="store_true", help="Overwrite existing output files")
    args = parser.parse_args()

    review_dir = Path(args.review_dir)
    if not review_dir.exists():
        print(f"[build_methods_snapshot] Review directory not found: {review_dir}")
        return

    cfg: dict = {}
    if args.topic_config and Path(args.topic_config).exists():
        try:
            cfg = json.loads(Path(args.topic_config).read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[build_methods_snapshot] Could not load topic_config: {exc}")

    question_type = cfg.get("question_type") or ""

    # Build methods_snapshot.json
    snapshot_path = review_dir / "methods_snapshot.json"
    if not snapshot_path.exists() or args.force:
        snapshot = build_methods_snapshot(review_dir, cfg)
        snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[build_methods_snapshot] Wrote {snapshot_path}")
    else:
        existing = json.loads(snapshot_path.read_text(encoding="utf-8"))
        if existing.get("_instructions"):
            # File is a placeholder — regenerate
            snapshot = build_methods_snapshot(review_dir, cfg)
            snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"[build_methods_snapshot] Updated placeholder → {snapshot_path}")
        else:
            print(f"[build_methods_snapshot] Skipped (already populated): {snapshot_path} — use --force to overwrite")

    # Build section_packets.json
    packets_path = review_dir / "section_packets.json"
    if not packets_path.exists() or args.force:
        packets = build_section_packets(review_dir, cfg, question_type)
        packets_path.write_text(json.dumps(packets, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[build_methods_snapshot] Wrote {packets_path}")
    else:
        print(f"[build_methods_snapshot] Skipped (already populated): {packets_path} — use --force to overwrite")

    # Build evidence_clusters.json
    clusters_path = review_dir / "evidence_clusters.json"
    if not clusters_path.exists() or args.force:
        clusters = build_evidence_clusters(review_dir, cfg)
        clusters_path.write_text(json.dumps(clusters, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[build_methods_snapshot] Wrote {clusters_path}")
    else:
        existing_cl = json.loads(clusters_path.read_text(encoding="utf-8"))
        # Regenerate if all clusters have empty member_paper_ids (template placeholder)
        all_empty = all(
            not c.get("member_paper_ids")
            for c in existing_cl.get("clusters", [{}])
        )
        if all_empty:
            clusters = build_evidence_clusters(review_dir, cfg)
            clusters_path.write_text(json.dumps(clusters, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"[build_methods_snapshot] Updated empty placeholder → {clusters_path}")
        else:
            print(f"[build_methods_snapshot] Skipped (already populated): {clusters_path} — use --force to overwrite")

    print()
    print("Next steps:")
    print("  1. Review and fill any TODO fields in methods_snapshot.json")
    print("  2. Review and edit cluster themes and synthesis_note in evidence_clusters.json")
    print("  3. Review anchor_paper_ids in section_packets.json and adjust if needed")
    print("  4. Run build_review_narrative.py to generate review_briefing.md")
    print("  5. Draft each section individually using section_packets (Stage N2)")
    print("  6. Apply global revision (Stage N3) before final output")


if __name__ == "__main__":
    main()
