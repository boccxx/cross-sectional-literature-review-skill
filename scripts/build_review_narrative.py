#!/usr/bin/env python3
"""build_review_narrative.py — produce a structured data briefing for LLM-written narrative.

This script does NOT write the literature review.
Its job is to aggregate all structured data (registries, search counts, citations,
evidence sufficiency) into a single, readable briefing document that the LLM
can consume to write the actual narrative synthesis.

The LLM reads this briefing and follows the Narrative Spine Requirement in SKILL.md.
Scripts handle data. The LLM handles writing.

Usage:
    python build_review_narrative.py <project_root> [--output <path>]
    python build_review_narrative.py <project_root> --review-dir <review_dir>

Output:
    <review_dir>/review_briefing.md   — structured data summary for LLM writing
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from core.project_modes import normalize_project_mode  # noqa: E402


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def read_json(path: Path) -> Any:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def csv_to_md(rows: list[dict], col_map: dict | None = None, max_rows: int = 50) -> str:
    if not rows:
        return "_No data._"
    cols = list(col_map.keys()) if col_map else list(rows[0].keys())
    headers = [col_map.get(c, c) if col_map else c for c in cols]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join([":---"] * len(cols)) + " |",
    ]
    for row in rows[:max_rows]:
        cells = [str(row.get(c, "")).strip().replace("\n", " ")[:120] for c in cols]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Manifest loader
# ---------------------------------------------------------------------------

def load_manifest(project_root: Path) -> dict:
    p = project_root / "study_manifest.json"
    if not p.exists():
        sys.exit(
            f"ERROR: study_manifest.json not found in {project_root}.\n"
            "Copy core/schemas/study_manifest_template.json, fill in your topic, and re-run."
        )
    m = json.loads(p.read_text(encoding="utf-8"))
    topic = m.get("topic", {})
    required = ["population", "setting", "exposure", "outcome"]
    empty = [f for f in required if not str(topic.get(f, "")).strip()]
    if empty:
        sys.exit(
            f"ERROR: study_manifest.json topic fields are empty: {empty}\n"
            "Fill in all topic fields before running this script."
        )
    return m


# ---------------------------------------------------------------------------
# PRISMA numbers — strict: numbers or 'not available', never guessed
# ---------------------------------------------------------------------------

def extract_screening_numbers(review_dir: Path, n_retained: int) -> dict[str, str]:
    search_log = read_csv(review_dir / "search_log.csv")
    screen_dec = read_csv(review_dir / "screening_decisions.csv")

    n_retrieved: str = "not available"
    if search_log:
        totals = [r.get("n_retrieved") or "" for r in search_log]
        totals = [t for t in totals if str(t).strip().isdigit()]
        if totals:
            n_retrieved = str(sum(int(t) for t in totals))

    n_dedup: str = "not available"
    if search_log:
        dedup_vals = [r.get("n_after_dedup") or "" for r in search_log]
        dedup_vals = [v for v in dedup_vals if str(v).strip().isdigit()]
        if dedup_vals:
            n_dedup = str(max(int(v) for v in dedup_vals))

    # Fall back to candidate_records_dedup.csv row count when search_log column is absent
    if n_dedup == "not available":
        dedup_csv = review_dir / "candidate_records_dedup.csv"
        if dedup_csv.exists():
            dedup_rows = read_csv(dedup_csv)
            if dedup_rows:
                n_dedup = str(len(dedup_rows))

    if n_retrieved == "not available":
        raw_csv = review_dir / "candidate_records_raw.csv"
        if raw_csv.exists():
            raw_rows = read_csv(raw_csv)
            if raw_rows:
                n_retrieved = str(len(raw_rows))

    n_screened: str = "not available"
    n_included: str = "not available"
    n_excluded: str = "not available"
    if screen_dec:
        n_screened = str(len(screen_dec))
        inc = sum(1 for r in screen_dec if str(r.get("decision", "")).lower() == "include")
        exc = sum(1 for r in screen_dec if str(r.get("decision", "")).lower() == "exclude")
        n_included = str(inc) if inc > 0 else "not available"
        n_excluded = str(exc) if exc > 0 else "not available"

    return {
        "n_retrieved": n_retrieved,
        "n_dedup": n_dedup,
        "n_screened": n_screened,
        "n_included": str(n_retained) if n_retained > 0 else "not available",
        "n_excluded": n_excluded,
    }


# ---------------------------------------------------------------------------
# Main briefing builder
# ---------------------------------------------------------------------------

def build_briefing(project_root: Path, review_dir: Path) -> str:
    manifest     = load_manifest(project_root)
    topic_cfg    = manifest["topic"]
    exposure     = topic_cfg["exposure"]
    outcome      = topic_cfg["outcome"]
    population   = topic_cfg["population"]
    setting      = topic_cfg["setting"]
    comparison   = topic_cfg.get("comparison", "")
    design_type  = (manifest.get("design_type") or "observational").strip()
    mode         = normalize_project_mode(manifest.get("project_mode", "research"))
    question_type = (manifest.get("question_type") or "").strip()
    review_goal  = (manifest.get("review_goal") or "").strip()

    # Load review contract for supplementary fields
    rc           = read_json(review_dir / "review_contract.json")
    estimand     = rc.get("primary_estimand", "") or topic_cfg.get("primary_estimand", "")
    mediator     = rc.get("mediator", "") or topic_cfg.get("candidate_mediator", "")
    moderator    = rc.get("moderator", "") or topic_cfg.get("candidate_modifier", "")
    review_type  = rc.get("review_type", "structured_narrative")
    reporting_framework = rc.get("reporting_framework", [])
    synthesis_method = rc.get("synthesis_method", "")

    # Registries
    study_reg      = read_csv(review_dir / "study_registry.csv")
    measure_reg    = read_csv(review_dir / "measurement_registry.csv")
    confounder_reg = read_csv(review_dir / "confounder_registry.csv")
    evidence_dec   = read_csv(review_dir / "evidence_to_decision_table.csv")
    effect_reg     = read_csv(review_dir / "effect_registry.csv")
    claim_reg      = read_csv(review_dir / "claim_registry.csv")
    bias_reg       = read_csv(review_dir / "bias_registry.csv")
    citation_reg   = read_json(review_dir / "citation_registry.json")
    suff_report    = read_json(review_dir / "evidence_sufficiency_report.json")

    # harvest outcomes / confounders from manifest
    harvest = manifest.get("harvest") or topic_cfg.get("harvest") or {}
    harvest_outcomes: list[str] = []
    if isinstance(harvest, dict):
        harvest_outcomes = [str(o).strip() for o in (harvest.get("outcomes") or []) if str(o).strip()]
    confounders_list: list[str] = list(manifest.get("confounders_core") or
                                        topic_cfg.get("confounders_core") or [])
    trigger_vocab: list[str] = list(manifest.get("trigger_vocabulary") or
                                     topic_cfg.get("trigger_vocabulary") or [])

    # Screening numbers
    n_retained = len(study_reg)
    nums = extract_screening_numbers(review_dir, n_retained)

    # Role / tier counts
    from collections import Counter
    role_counts = Counter(r.get("primary_role", "other") for r in study_reg)
    tier_counts = Counter(r.get("synthesis_tier", "unassigned") for r in study_reg)
    anchor_counts = Counter((r.get("anchor_eligible") or "no").strip().lower() for r in study_reg)

    # Citations
    entries = citation_reg.get("entries", []) if isinstance(citation_reg, dict) else []

    # Sufficiency
    suff_level = suff_report.get("level", "") if isinstance(suff_report, dict) else ""
    suff_notes = suff_report.get("notes", "") if isinstance(suff_report, dict) else ""
    deliverable_style = rc.get("deliverable_style", "") if isinstance(rc, dict) else ""
    narrative_readiness = rc.get("narrative_readiness", "") if isinstance(rc, dict) else ""
    anchor_density_by_outcome = rc.get("anchor_density_by_outcome", {}) if isinstance(rc, dict) else {}

    # ---- Assemble briefing ----
    L: list[str] = []

    L += [
        "# Review Briefing",
        "",
        "> **For the LLM writing the narrative synthesis.**",
        "> This document aggregates all structured review data into one place.",
        "> Read every section, then write the literature review following the",
        "> Narrative Spine Requirement in SKILL.md.",
        "> Do NOT reproduce this briefing verbatim — synthesise from it.",
        "",
    ]

    # ---- Topic ----
    L += [
        "## Topic",
        "",
        f"- **Exposure:** {exposure}",
        f"- **Comparison:** {comparison}" if comparison else "",
        f"- **Outcome:** {outcome}",
        f"- **Population:** {population}",
        f"- **Setting:** {setting}",
        f"- **Primary estimand:** {estimand}" if estimand else "",
        f"- **Question type:** {question_type}" if question_type else "",
        f"- **Review goal:** {review_goal}" if review_goal else "",
        f"- **Review type:** {review_type}",
        f"- **Reporting framework:** {', '.join(reporting_framework) if isinstance(reporting_framework, list) else reporting_framework}",
        f"- **Synthesis method:** {synthesis_method}",
        f"- **Design type:** {design_type}",
        f"- **Project mode:** {mode}",
        "",
    ]
    # Remove empty lines
    L = [line for line in L if line != ""]

    L.append("")

    if harvest_outcomes:
        L += ["### Outcomes of interest (from harvest config)", ""]
        for o in harvest_outcomes:
            L.append(f"- {o}")
        L.append("")

    if confounders_list:
        L += ["### Pre-specified confounders (from manifest)", ""]
        for c in confounders_list:
            L.append(f"- {c}")
        L.append("")

    if mediator:
        L += [f"### Candidate mediator: {mediator}", ""]
    if moderator:
        L += [f"### Candidate effect modifier: {moderator}", ""]
    if trigger_vocab:
        L += ["### Clinical trigger vocabulary (from config)", ""]
        for t in trigger_vocab:
            L.append(f"- {t}")
        L.append("")

    # ---- Search and Screening ----
    L += [
        "## Search and Screening (PRISMA numbers)",
        "",
        f"| Stage | n |",
        f"|---|---|",
        f"| Retrieved (all sources) | {nums['n_retrieved']} |",
        f"| After deduplication | {nums['n_dedup']} |",
        f"| Screened (title/abstract) | {nums['n_screened']} |",
        f"| Excluded at title/abstract | {nums['n_excluded']} |",
        f"| Full-text assessed / included | {nums['n_included']} |",
        f"| Retained for synthesis | {n_retained} |",
        "",
        "_Values shown as 'not available' come directly from missing CSV columns — do not estimate._",
        "",
    ]

    # Search log source breakdown
    search_log = read_csv(review_dir / "search_log.csv")
    if search_log:
        source_status: dict[str, dict[str, int]] = {}
        for row in search_log:
            src = row.get("source", "unknown")
            status = row.get("status", "planned")
            source_status.setdefault(src, {})
            source_status[src][status] = source_status[src].get(status, 0) + 1
        L += ["### Source execution summary", ""]
        L += ["| Source | retrieved | blocked / planned |",
              "|---|---|---|"]
        for src, counts in sorted(source_status.items()):
            retrieved = counts.get("retrieved", 0)
            not_retrieved = sum(v for k, v in counts.items() if k != "retrieved")
            L.append(f"| {src} | {retrieved} | {not_retrieved} |")
        L.append("")

    # ---- Cite-Ready Reference List ----
    # This section produces a compact inline-citation guide so the LLM can embed
    # publication-facing numeric markers while keeping registry IDs in the briefing.
    # It is placed BEFORE the full study registry table so it is easy to scan.
    #
    # Author/DOI data is cross-referenced from scored_candidates.csv (which carries
    # these fields from the live search) when study_registry.csv does not have them.
    if study_reg:
        # Build a lookup from scored_candidates.csv (paper_id → row) for fallback metadata.
        scored_lookup: dict[str, dict] = {}
        scored_path = review_dir / "scored_candidates.csv"
        if scored_path.exists():
            for sc_row in read_csv(scored_path):
                pid_key = (sc_row.get("paper_id") or "").strip()
                if pid_key:
                    scored_lookup[pid_key] = sc_row

        L += [
            "## Cite-Ready Reference List (use these for inline citations)",
            "",
            "> **How to cite inline:** use the numeric marker assigned in `citation_registry.json`, for example `[1]`.",
            "> Keep PaperID and citation_id in the registry and binding map; do not expose internal IDs in publication prose.",
            "> Every factual claim about a specific study must use its registered number and match the numbered References entry.",
            "",
        ]
        ref_by_paper = {
            str(entry.get("paper_id", "")): entry.get("reference_number")
            for entry in entries
            if entry.get("paper_id") and entry.get("reference_number")
        }
        for row in study_reg[:50]:
            pid = row.get("paper_id", "")
            yr  = row.get("year", "n.d.")
            # Try study_registry first, then fall back to scored_candidates
            fallback = scored_lookup.get(pid, {})
            authors_raw = (row.get("authors") or row.get("author") or
                           fallback.get("authors") or fallback.get("author") or "")
            title_short = (row.get("title") or fallback.get("title") or "")[:80]
            doi = (row.get("doi") or fallback.get("doi") or
                   row.get("url") or fallback.get("url") or "")
            if authors_raw:
                first_seg = authors_raw.split(";")[0].strip()
                if "," in first_seg:
                    # "LastName, FirstName" or "LastName, FI." format
                    first_author = first_seg.split(",")[0].strip()
                else:
                    # "LastName FI" or "LastName FI." format (PubMed E-utilities / OpenAlex)
                    first_author = first_seg.split()[0].strip() if first_seg else "—"
                n_authors = len([a for a in authors_raw.split(";") if a.strip()])
                author_token = f"{first_author} et al." if n_authors > 2 else first_author
            else:
                author_token = "—"
            role = row.get("primary_role", "")
            reference_number = ref_by_paper.get(pid, "unassigned")
            L.append(f"- **Reference [{reference_number}]** (registry paper_id `{pid}`) {author_token}, {yr} — _{title_short}_ — doi:{doi} [{role}]")
        L.append("")

    # ---- Study Registry ----
    L += ["## Retained Studies (study_registry.csv)", ""]
    if study_reg:
        L += [f"**Total retained: {n_retained}**", ""]
        L += [f"**Role breakdown:** {dict(role_counts)}", ""]
        if tier_counts:
            L += [f"**Synthesis tier breakdown:** {dict(tier_counts)}", ""]
        if anchor_counts:
            L += [f"**Anchor eligibility:** {dict(anchor_counts)}", ""]
        study_cols = {
            "paper_id": "ID",
            "synthesis_tier": "Tier",
            "anchor_eligible": "Anchor",
            "primary_role": "Role",
            "year": "Year",
            "design": "Design",
            "population": "Population",
            "exposure": "Exposure",
            "outcome": "Outcome",
            "direct_question_match": "Question match",
            "comparator_integrity_ok": "Comparator",
            "time_zero_clear": "Time zero",
            "prior_user_design": "Prior user",
            "sample_size": "N",
            "core_findings": "Core findings",
            "limitations": "Limitations",
            "protocol_implication": "Protocol implication",
            "quality_signal": "Quality",
        }
        L.append(csv_to_md(study_reg, study_cols, max_rows=50))
        L.append("")
    else:
        L += [
            "_study_registry.csv is empty. This means screening and data extraction have not yet been completed._",
            "_The narrative synthesis section on evidence (Section 4) should reflect this honestly: no screened and extracted evidence is available yet._",
            "",
        ]

    # ---- Effect Registry ----
    if effect_reg:
        L += ["## Effect Estimates (effect_registry.csv)", ""]
        effect_cols = {
            "paper_id": "Paper",
            "outcome_family": "Outcome family",
            "outcome": "Outcome",
            "exposure_contrast": "Contrast",
            "effect_measure": "Measure",
            "point_estimate": "Estimate",
            "ci_lower": "CI lower",
            "ci_upper": "CI upper",
            "effect_directness": "Directness",
            "supports_primary_direction_claim": "Primary claim",
            "population_subgroup": "Subgroup",
            "effect_trustworthiness": "Trust",
            "note": "Note",
        }
        L.append(csv_to_md(effect_reg, effect_cols, max_rows=40))
        L.append("")

    # ---- Claim Registry ----
    if claim_reg:
        L += ["## Claim Registry (claim_registry.csv)", ""]
        claim_cols = {
            "claim_id": "ID",
            "outcome_family": "Outcome family",
            "claim_text": "Claim",
            "allowed_strength": "Max strength",
            "anchor_required": "Anchor req",
            "supports_primary_direction_claim": "Primary claim",
            "eligible_anchor_paper_ids": "Eligible anchors",
            "supporting_paper_ids": "Papers",
            "note": "Note",
        }
        L.append(csv_to_md(claim_reg, claim_cols, max_rows=30))
        L.append("")

    # ---- Bias Registry ----
    if bias_reg:
        L += ["## Bias Assessment (bias_registry.csv)", ""]
        bias_cols = {
            "paper_id": "Paper",
            "bias_domain": "Domain",
            "severity": "Severity",
            "direction": "Direction",
            "note": "Note",
        }
        L.append(csv_to_md(bias_reg, bias_cols, max_rows=40))
        L.append("")

    # ---- Measurement Registry ----
    L += ["## Measurement Registry (measurement_registry.csv)", ""]
    if measure_reg:
        measure_cols = {
            "construct": "Construct",
            "preferred_tool": "Preferred tool",
            "evidence_role": "Evidence role",
            "reason_from_literature": "Justification",
            "protocol_use": "Protocol use",
            "limitation_or_bias": "Limitation",
        }
        L.append(csv_to_md(measure_reg, measure_cols, max_rows=20))
        L.append("")
    else:
        L += ["_measurement_registry.csv is empty._", ""]

    # ---- Confounder Registry ----
    L += ["## Confounder Registry (confounder_registry.csv)", ""]
    if confounder_reg:
        conf_cols = {
            "variable": "Variable",
            "classification": "Role",
            "support_level": "Support",
            "rationale": "Rationale",
            "recommended_main_model_role": "Model action",
        }
        L.append(csv_to_md(confounder_reg, conf_cols, max_rows=20))
        L.append("")
    else:
        L += ["_confounder_registry.csv is empty._", ""]

    # ---- Evidence-to-Decision ----
    L += ["## Evidence-to-Decision (evidence_to_decision_table.csv)", ""]
    if evidence_dec:
        etd_cols = {
            "decision_id": "ID",
            "decision": "Decision",
            "evidence_summary": "Evidence summary",
            "supporting_paper_ids": "Papers",
            "confidence": "Confidence",
            "downstream_use": "Use",
        }
        L.append(csv_to_md(evidence_dec, etd_cols, max_rows=20))
        L.append("")
    else:
        L += ["_evidence_to_decision_table.csv is empty._", ""]

    # ---- Evidence Sufficiency ----
    L += ["## Evidence Sufficiency (evidence_sufficiency_report.json)", ""]
    if deliverable_style:
        L.append(f"**Deliverable style:** {deliverable_style}")
    if narrative_readiness:
        L.append(f"**Narrative readiness:** {narrative_readiness}")
    if anchor_density_by_outcome:
        L.append(f"**Anchor density by outcome:** {anchor_density_by_outcome}")
    if suff_level:
        L.append(f"**Level:** {suff_level}")
    if suff_notes:
        L.append(f"**Notes:** {suff_notes}")
    if not suff_level and not suff_notes:
        L.append("_evidence_sufficiency_report.json is empty._")
    L.append("")

    # ---- Citations ----
    L += ["## Citation Registry (citation_registry.json)", ""]
    if entries:
        for i, e in enumerate(entries, start=1):
            doi_part = f" doi:{e['doi']}" if e.get("doi") else ""
            pmid_part = f" PMID:{e['pmid']}" if e.get("pmid") else ""
            role_part = f" [{e['role']}]" if e.get("role") else ""
            L.append(
                f"{i}. **{e.get('title', '—')}** ({e.get('year', 'n.d.')}). "
                f"*{e.get('authors', '')}*. {e.get('journal', '')}"
                f"{doi_part}{pmid_part}{role_part}"
            )
        L.append("")
    else:
        L += ["_citation_registry.json is empty or has no entries._",
              "_Populate it after screening and full-text reading._", ""]

    # ---- Methods Snapshot (structured methods layer for narrative) ----
    methods_snap = read_json(review_dir / "methods_snapshot.json")
    if methods_snap and isinstance(methods_snap, dict) and "_instructions" not in methods_snap:
        L += [
            "## Methods Snapshot (methods_snapshot.json)",
            "",
            "> Use this block when writing the Search and Screening section.",
            "> All values here are machine-derived from the actual project files — use them verbatim.",
            "",
        ]
        for k, v in methods_snap.items():
            if v and str(v).strip() not in ("TODO", "not available", "null", ""):
                if isinstance(v, list):
                    L.append(f"**{k}:**")
                    for item in v:
                        L.append(f"  - {item}")
                elif isinstance(v, dict):
                    L.append(f"**{k}:** {json.dumps(v, ensure_ascii=False)}")
                else:
                    L.append(f"**{k}:** {v}")
        L.append("")

    # ---- Section Packets (per-section drafting guidance) ----
    section_pkts = read_json(review_dir / "section_packets.json")
    pkt_list: list[dict] = []
    if isinstance(section_pkts, dict):
        pkt_list = section_pkts.get("sections", [])
    elif isinstance(section_pkts, list):
        pkt_list = section_pkts
    if pkt_list:
        L += [
            "## Section Drafting Packets (section_packets.json)",
            "",
            "> **MANDATORY:** Draft each section below INDIVIDUALLY.",
            "> Do NOT write the entire review in one pass.",
            "> For each section: read its packet, write that section, stop.",
            "> Only after all sections are drafted, apply Stage N3 global revision.",
            "",
        ]
        for pkt in pkt_list:
            sname = pkt.get("section_name") or pkt.get("section") or "unnamed"
            L.append(f"### Section: {sname}")
            for k, v in pkt.items():
                if k in ("section_name", "section"):
                    continue
                if v:
                    if isinstance(v, list):
                        L.append(f"- **{k}:**")
                        for item in v:
                            L.append(f"  - {item}")
                    else:
                        L.append(f"- **{k}:** {v}")
            L.append("")

    # ---- Evidence Clusters (for indirect evidence synthesis) ----
    ev_clusters = read_json(review_dir / "evidence_clusters.json")
    cluster_list: list[dict] = []
    if isinstance(ev_clusters, dict):
        cluster_list = ev_clusters.get("clusters", [])
    if cluster_list:
        # Only surface clusters with member papers (skip template placeholders)
        real_clusters = [c for c in cluster_list if c.get("member_paper_ids")]
        if real_clusters:
            L += [
                "## Evidence Clusters (evidence_clusters.json)",
                "",
                "> Use these clusters when writing the Broader Supporting Evidence section.",
                "> Write ONE paragraph per cluster — NOT one paragraph per paper.",
                "",
            ]
            for cl in real_clusters:
                cid = cl.get("cluster_id") or "?"
                theme = cl.get("theme") or ""
                L.append(f"**Cluster {cid} — {theme}**")
                if cl.get("member_paper_ids"):
                    L.append(f"  Papers: {', '.join(cl['member_paper_ids'])}")
                if cl.get("what_this_cluster_can_support"):
                    L.append(f"  Can support: {cl['what_this_cluster_can_support']}")
                if cl.get("what_it_cannot_support"):
                    L.append(f"  Cannot substitute: {cl['what_it_cannot_support']}")
                if cl.get("synthesis_note"):
                    L.append(f"  Synthesis note: {cl['synthesis_note']}")
                L.append("")

    # ---- Candidate pool summary (for orientation, not for prose) ----
    dedup_csv = review_dir / "candidate_records_dedup.csv"
    if dedup_csv.exists():
        dedup_rows = read_csv(dedup_csv)
        if dedup_rows and n_retained == 0:
            L += [
                "## Candidate Pool (not yet screened)",
                "",
                f"_study_registry.csv is empty but candidate_records_dedup.csv has {len(dedup_rows)} records._",
                "_The following are unscreened candidates. Do NOT treat them as retained studies._",
                "_Use them to orient yourself to what the candidate pool contains before writing._",
                "",
            ]
            cand_cols = {
                "title": "Title",
                "authors": "Authors",
                "year": "Year",
                "doi": "DOI",
                "query_family": "Query family",
                "local_relevance_score": "Score",
            }
            L.append(csv_to_md(dedup_rows, cand_cols, max_rows=60))
            L.append("")

    # ---- Writing instructions (reminder) ----
    L += [
        "---",
        "",
        "## Writing Instructions for the LLM",
        "",
        "Use the data above to write the literature review narrative.",
        "Treat this briefing as the evidence-map layer, not as prose to imitate.",
        f"The selected product is `{review_type}`; follow its declared reporting framework and synthesis method.",
        "Use `references/review_writing_blueprint.md` as the default writing architecture.",
        "",
        "---",
        "",
        "### Stage N1 — Section Planning (do this mentally before writing anything)",
        "",
        "Before drafting, read the Section Drafting Packets above and confirm for each section:",
        "- Which 2–4 anchor papers will this section rely on?",
        "- What is the single central judgment for this section?",
        "- What is the main methodological limitation to name?",
        "- What is the allowed_strength_ceiling? Will no claim exceed it?",
        "- Are there forbidden papers that must not appear as primary support?",
        "",
        "---",
        "",
        "### Stage N2 — Per-Section Drafting (write one section at a time)",
        "",
        "**Write each section individually, not the whole review at once.**",
        "For each section, follow this paragraph structure:",
        "1. Open with a scope judgment (what the evidence as a whole shows) — not with a paper name.",
        "2. Name at most 2 anchor papers with their specific finding and key design feature.",
        "3. State the most important limitation immediately after the finding.",
        "4. End with a bounded interpretation aligned to the section's allowed_strength_ceiling.",
        "",
        "**Anti-listing rule (strictly enforced):**",
        "NEVER write: 'Study X found Y. Study Z found W. Study A also found B.'",
        "INSTEAD write: 'The available direct comparative evidence, concentrated in cohort studies from",
        "Scandinavia and the UK, consistently shows [direction] for [outcome] [3,7],",
        "though all estimates carry [main confounding limitation].'",
        "",
        "**For the Broader Supporting Evidence section:**",
        "Write ONE paragraph per evidence cluster from the Evidence Clusters above.",
        "Do not write one paragraph per paper.",
        "Each cluster paragraph should state what the cluster collectively suggests,",
        "then immediately state what it cannot substitute for.",
        "",
        "**For Outcome-specific sections with no direct evidence:**",
        "Write one sentence stating the gap and one sentence on what indirect evidence implies.",
        "Do NOT write a long paragraph just to say 'evidence is limited.'",
        "",
        "---",
        "",
        "### Stage N3 — Global Revision (after all sections are drafted)",
        "",
        "Before producing the final output, apply these global constraints:",
        "1. Find all sentence openers used 3+ times across sections — delete or vary them.",
        "2. Find all paragraphs that only say 'evidence is limited' without a specific finding — delete or replace.",
        "3. Check every direction-of-effect claim against claim_registry.csv allowed_strength — downgrade if needed.",
        "4. Remove ALL pipeline meta-language: pipeline, registry, tier, candidate pool, briefing, anchor_eligible, skill.",
        "5. Keep the Review Methods reproducible (normally 450–700 words) and the late flow-accounting paragraph compact.",
        "6. Verify every study-specific claim has its registered numeric inline marker, for example [3] or [3,7].",
        "7. Check that no indirect or background paper is being used to support a primary direction-of-effect claim.",
        "8. Populate the main-body Study Characteristics and Effect Evidence Matrix tables from the registries.",
        "",
        "---",
        "",
        "### Follow the Narrative Spine",
        "",
        "1. Open with why this question matters — not with search logistics.",
        "2. Explain why existing literature types cannot directly answer the specific question.",
        "3. Write the direct evidence section around the strongest studies, not every retained study.",
        "4. Use indirect supporting evidence only to interpret context, measurement, bias, and patient perspective.",
        "5. Synthesise by outcome dimension or theme — not by listing papers one by one.",
        "6. Describe methodological challenges as literature limitations, not as package logic.",
        "7. State the research gaps and design implications.",
        "8. Keep Search and Screening brief and late in the review.",
        "",
        "### Evidence-layer separation",
        "",
        "- Direct comparative evidence supports the main direction-of-effect discussion.",
        "- Broader evidence sharpens plausibility or boundaries — must be labeled indirect when not exact-match.",
        "- Patient-centered or symptom evidence explains trade-offs — does not replace hard-outcome evidence.",
        "- Guideline or policy material frames uncertainty — must not anchor empirical outcome claims.",
        "",
        "**Do not reproduce this briefing.** Write prose that a reviewer or epidemiologist would write.",
        "**Do not mention the briefing, the pipeline, or package logic** in the narrative body.",
        "**Inline PRISMA counts** must come from the PRISMA table above — not from narrative estimation.",
        "**Claim strength** must not exceed what claim_registry.csv records as `allowed_strength`.",
        "**Only studies with `anchor_eligible=yes` may support primary direction-of-effect claims.**",
        "**Do not let `appendix_only` or `background_policy` studies support main conclusions.**",
        "**Use `outcome_family` to organise direct evidence and evidence gaps.**",
        "**Do not write one-paper-one-sentence lists across a whole section.**",
        "If the study_registry is empty, say so honestly: no screened evidence is available yet,",
        "and describe what the candidate pool suggests about the field.",
        "",
        "### Forbidden main-text language",
        "",
        "These terms belong in the briefing or validator, not in the main review body:",
        "- workflow, pipeline, upgrade, system, tier, anchor_eligible",
        "- review_briefing.md, study_registry.csv, claim_registry.csv, effect_registry.csv",
        "- candidate pool, screening architecture, package logic, narrative_readiness",
        "",
        "### Inline Citation Requirement (MANDATORY)",
        "",
        "Every sentence that attributes a specific finding, estimate, design feature, or",
        "descriptive fact to a named study MUST include an inline citation. Use the",
        "'Cite-Ready Reference List' above to look up the correct numeric reference marker.",
        "",
        "Required citation format:",
        "  [reference_number] immediately after the supported clause, e.g. [3] or [3,7]",
        "",
        "Examples of CORRECT inline citations:",
        "  'A population-based cohort reported a higher adjusted outcome rate in the exposed group",
        "   [3].'",
        "  'A measurement study found acceptable reliability for the prespecified instrument",
        "   [7].'",
        "",
        "Examples of INCORRECT (missing citations — must be fixed before delivery):",
        "  'A cohort study found a higher outcome rate.' ← no registered numeric citation",
        "  'Guidelines recommend the intervention.' ← no registered numeric citation",
        "",
        "The References section at the end must list every numeric marker cited in the body",
        "in Vancouver or APA format using the full bibliographic data from citation_registry.json.",
        "",
    ]

    return "\n".join(L)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a structured data briefing for LLM-written literature review narrative."
    )
    parser.add_argument("project_root",
                        help="Path to the project root (must contain study_manifest.json)")
    parser.add_argument("--review-dir", default=None,
                        help="Path to literature_review/ dir (defaults to <project_root>/literature_review)")
    parser.add_argument("--output", default=None,
                        help="Output path (default: <review_dir>/review_briefing.md)")
    args = parser.parse_args()

    project_root = Path(args.project_root)
    review_dir   = Path(args.review_dir) if args.review_dir else project_root / "literature_review"
    out_path     = Path(args.output) if args.output else review_dir / "review_briefing.md"

    text = build_briefing(project_root, review_dir)
    write_text(out_path, text)
    print(f"Review briefing written to: {out_path}")
    print("Next step: read the briefing and write the narrative following SKILL.md Narrative Spine Requirement.")


if __name__ == "__main__":
    main()
