#!/usr/bin/env python3
"""Import a previously prepared local evidence corpus into the review package format.

This helper is a migration utility, not the default retrieval path for the
skill. It bootstraps curated local review tables into the review package
format used by the skill so legacy projects can be brought forward. A live
multi-database search should still be run and logged before treating the
result as a completed literature review.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def normalize(text: str) -> str:
    return (text or "").strip().lower()


def slugify_decision(decision_id: int) -> str:
    return f"D{decision_id:02d}"


def find_topic_config(start_dir: Path) -> dict:
    for candidate_dir in [start_dir, *start_dir.parents]:
        candidate = candidate_dir / "topic_config.json"
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
    return {}


def first_nonempty(values: list[str]) -> str:
    for value in values:
        if value and str(value).strip():
            return str(value).strip()
    return ""


def enrich_cfg(cfg: dict, evidence_rows: list[dict[str, str]], papers: list[dict[str, str]]) -> dict:
    enriched = dict(cfg)
    exposures = [row.get("exposure", "") for row in evidence_rows]
    outcomes = [row.get("outcome", "") for row in evidence_rows]
    populations = [row.get("population", "") for row in papers]
    settings = [row.get("setting", "") for row in evidence_rows]

    enriched.setdefault("design_type", "cross_sectional")
    if not enriched.get("exposure"):
        enriched["exposure"] = first_nonempty(exposures)
    if not enriched.get("outcome"):
        enriched["outcome"] = first_nonempty(outcomes)
    if not enriched.get("population"):
        enriched["population"] = first_nonempty(populations)
    if not enriched.get("setting"):
        enriched["setting"] = first_nonempty(settings)
    if not enriched.get("topic"):
        bits = [enriched.get("exposure", ""), enriched.get("outcome", ""), enriched.get("population", "")]
        enriched["topic"] = " ".join(bit for bit in bits if bit).strip() or "study topic"
    return enriched


def build_search_log(topic: str, queries: list[str]) -> list[dict[str, str]]:
    rows = []
    today = date.today().isoformat()
    for idx, q in enumerate(queries, start=1):
        rows.append(
            {
                "search_id": f"S{idx:02d}",
                "search_round": "0",
                "parent_search_id": "",
                "concept_focus": "legacy import seed",
                "query_family": "legacy_import_seed",
                "query": q,
                "source": "Imported prior corpus",
                "source_query": "not available from imported seed",
                "date_searched": today,
                "date_limit": "",
                "language_limit": "",
                "recommended_retrieval_target": "",
                "n_retrieved": "",
                "n_after_dedup": "",
                "scope": "screen for topical fit, measurement, methods, and design support",
                "status": "legacy_import",
                "rationale_trigger": "imported prepared evidence package; live database retrieval still required",
                "note": topic,
            }
        )
    return rows


def infer_publication_status(row: dict[str, str]) -> str:
    blob = " ".join(
        [row.get("title", ""), row.get("doi", ""), row.get("url", "")]
    ).lower()
    if any(token in blob for token in ["medrxiv", "biorxiv", "arxiv", "preprint", "preprints"]):
        return "preprint"
    return "peer_reviewed_or_unknown"


def infer_primary_role(paper: dict[str, str], evidence_row: dict[str, str]) -> str:
    title = normalize(paper.get("title", ""))
    design = normalize(paper.get("design", ""))
    implication = normalize(evidence_row.get("protocol_implication", ""))
    methods = normalize(evidence_row.get("suggested_methods", ""))

    if any(token in title for token in ["systematic review", "meta-analysis", "umbrella review", "scoping review"]):
        return "evidence_synthesis"
    if any(token in title for token in ["validation", "psychometric", "reliability", "validity"]):
        return "measurement_validation"
    if any(token in title + " " + implication + " " + methods for token in ["mediat", "mechanism", "pathway"]):
        return "mechanism_or_mediation"
    if any(token in title + " " + implication + " " + methods for token in ["modifier", "subgroup", "interaction"]):
        return "modifier_or_subgroup"
    if any(token in design for token in ["trial", "intervention", "cohort", "case-control", "cross-sectional", "observational"]):
        return "primary_population_study"
    return "primary_population_study"


def infer_secondary_role(evidence_row: dict[str, str]) -> str:
    implication = normalize(evidence_row.get("protocol_implication", ""))
    methods = normalize(evidence_row.get("suggested_methods", ""))
    if methods or any(token in implication for token in ["measure", "model", "adjust", "estimand", "threshold"]):
        return "methods_justification"
    return "background"


def infer_citation_roles(primary_role: str, evidence_row: dict[str, str]) -> list[str]:
    implication = normalize(evidence_row.get("protocol_implication", ""))
    roles: list[str] = []
    if primary_role == "evidence_synthesis":
        roles.append("background")
    if "measure" in implication or "threshold" in implication:
        roles.append("methods_justification")
    if any(token in implication for token in ["mediat", "mechanism", "pathway"]):
        roles.append("mechanism")
    if not roles:
        roles.append("background")
    return roles


def build_study_registry(
    papers: list[dict[str, str]],
    evidence: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for reference_number, row in enumerate(papers, start=1):
        evidence_row = evidence.get(row["paper_id"], {})
        primary_role = infer_primary_role(row, evidence_row)
        secondary_role = infer_secondary_role(evidence_row)
        rows.append(
            {
                "paper_id": row["paper_id"],
                "evidence_row_id": f"EV_{row['paper_id']}",
                "primary_role": primary_role,
                "secondary_role": secondary_role,
                "publication_status": infer_publication_status(row),
                "year": row.get("year", ""),
                "design": row.get("design", ""),
                "population": row.get("population", ""),
                "exposure": evidence_row.get("exposure", ""),
                "outcome": evidence_row.get("outcome", ""),
                "sample_size": evidence_row.get("sample_size", ""),
                "setting": evidence_row.get("setting", ""),
                "measures": evidence_row.get("measures", ""),
                "core_findings": evidence_row.get("core_findings", ""),
                "limitations": evidence_row.get("limitations", ""),
                "protocol_implication": evidence_row.get("protocol_implication", ""),
                "suggested_methods": evidence_row.get("suggested_methods", ""),
                "relevance_score": row.get("relevance_score", ""),
                "quality_signal": row.get("quality_signal", ""),
            }
        )
    return rows


def infer_measurement_role(
    construct: str,
    cfg: dict,
) -> tuple[str, str]:
    c = normalize(construct)
    exposure = normalize(cfg.get("exposure", ""))
    outcome = normalize(cfg.get("outcome", ""))
    mediator = normalize(cfg.get("candidate_mediator", ""))
    modifier = normalize(cfg.get("candidate_modifier", ""))

    if outcome and any(token for token in outcome.split() if token and token in c):
        return "outcome_measurement", "primary outcome"
    if exposure and any(token for token in exposure.split() if token and token in c):
        return "exposure_measurement", "primary exposure"
    if mediator and any(token for token in mediator.split() if token and token in c):
        return "mediator_measurement", "planned mediator"
    if modifier and any(token for token in modifier.split() if token and token in c):
        return "modifier_measurement", "planned effect modifier"
    return "construct_measurement", "supporting construct"


def build_measurement_registry(measurements: list[dict[str, str]], cfg: dict) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in measurements:
        evidence_role, protocol_use = infer_measurement_role(row.get("construct", ""), cfg)
        example_papers = row.get("key_example_papers", "")
        rows.append(
            {
                "construct": row.get("construct", ""),
                "preferred_tool": row.get("preferred_tool", ""),
                "evidence_role": evidence_role,
                "reason_from_literature": row.get("reason_from_literature", ""),
                "key_example_paper_ids": example_papers,
                "supporting_evidence_row_ids": ";".join(
                    f"EV_{pid.strip()}" for pid in example_papers.split(";") if pid.strip()
                ),
                "protocol_use": protocol_use,
                "limitation_or_bias": "justify tool choice against population, setting, and design fit",
            }
        )
    return rows


def infer_confounder_classification(variable: str, rationale: str) -> tuple[str, str]:
    blob = f"{variable} {rationale}".lower()
    if "collider" in blob:
        return "possible_collider", "do_not_adjust_without_strong_justification"
    if any(token in blob for token in ["mediat", "pathway"]):
        return "possible_mediator", "exclude_from_primary_model"
    if any(token in blob for token in ["modifier", "interaction", "effect modification", "subgroup"]):
        return "possible_effect_modifier", "prespecify_interaction_if_relevant"
    return "probable_confounder", "adjust_if_measured"


def build_confounder_registry(confounders: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in confounders:
        classification, role = infer_confounder_classification(
            row.get("variable", ""),
            row.get("rationale", ""),
        )
        rows.append(
            {
                "variable": row.get("variable", ""),
                "classification": classification,
                "support_level": "medium",
                "supporting_paper_ids": "",
                "supporting_evidence_row_ids": "",
                "rationale": row.get("rationale", ""),
                "recommended_main_model_role": role,
            }
        )
    return rows


def build_evidence_table(evidence_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in evidence_rows:
        decision = row.get("protocol_implication", "").strip()
        if decision:
            grouped[decision].append(row)
        methods_blob = row.get("suggested_methods", "")
        for method in re.split(r"[;|]", methods_blob):
            method = method.strip()
            if method:
                grouped[f"Use or evaluate method: {method}"].append(row)

    rows: list[dict[str, str]] = []
    for idx, (decision, supports) in enumerate(grouped.items(), start=1):
        findings = [r.get("core_findings", "").strip() for r in supports if r.get("core_findings", "").strip()]
        methods = [r.get("suggested_methods", "").strip() for r in supports if r.get("suggested_methods", "").strip()]
        summary_parts = []
        if findings:
            summary_parts.append(findings[0])
        if methods:
            summary_parts.append(f"Common method signal: {methods[0]}")
        summary = " ".join(summary_parts) if summary_parts else "Supported by retained evidence rows."

        decision_blob = decision.lower()
        if any(token in decision_blob for token in ["exposure", "outcome", "measure", "threshold", "instrument"]):
            downstream_use = "variable_definition"
        elif any(token in decision_blob for token in ["confound", "adjust", "covariat", "mediat", "modifier"]):
            downstream_use = "model_specification"
        elif any(token in decision_blob for token in ["estimand", "ratio", "hazard", "odds", "risk"]):
            downstream_use = "estimand"
        else:
            downstream_use = "background_and_rationale"

        rows.append(
            {
                "decision_id": slugify_decision(idx),
                "decision": decision,
                "evidence_summary": summary,
                "supporting_paper_ids": ";".join(r["paper_id"] for r in supports if r.get("paper_id")),
                "supporting_evidence_row_ids": ";".join(f"EV_{r['paper_id']}" for r in supports if r.get("paper_id")),
                "downstream_use": downstream_use,
                "confidence": "high" if len(supports) >= 3 else "moderate" if len(supports) == 2 else "limited",
            }
        )
    return rows


def build_citation_registry(
    topic: str,
    mode: str,
    papers: list[dict[str, str]],
    evidence: dict[str, dict[str, str]],
    evidence_table: list[dict[str, str]],
) -> dict:
    decision_lookup: dict[str, list[str]] = defaultdict(list)
    for decision_row in evidence_table:
        for paper_id in decision_row.get("supporting_paper_ids", "").split(";"):
            pid = paper_id.strip()
            if pid:
                decision_lookup[pid].append(decision_row["decision_id"])

    entries = []
    for row in papers:
        evidence_row = evidence.get(row["paper_id"], {})
        primary_role = infer_primary_role(row, evidence_row)
        secondary_role = infer_secondary_role(evidence_row)
        citation_roles = infer_citation_roles(primary_role, evidence_row)
        entries.append(
            {
                "citation_id": f"C_{row['paper_id']}",
                "reference_number": reference_number,
                "paper_id": row["paper_id"],
                "title": row.get("title", ""),
                "year": row.get("year", ""),
                "publication_status": infer_publication_status(row),
                "narrative_role": citation_roles[0],
                "claim_supported": evidence_row.get("protocol_implication", ""),
                "supporting_decision_ids": decision_lookup.get(row["paper_id"], []),
                "supporting_evidence_row_ids": [f"EV_{row['paper_id']}"],
                "roles": [primary_role, secondary_role],
                "doi": row.get("doi", ""),
            }
        )
    return {
        "project_mode": mode,
        "topic": topic,
        "entries": entries,
    }


def build_sufficiency_report(
    topic: str,
    mode: str,
    papers: list[dict[str, str]],
    evidence_rows: list[dict[str, str]],
    measurement_rows: list[dict[str, str]],
    confounder_rows: list[dict[str, str]],
    cfg: dict,
) -> dict:
    roles = Counter(infer_primary_role(p, {r["paper_id"]: r for r in evidence_rows}.get(p["paper_id"], {})) for p in papers)
    design_counts = Counter(normalize(p.get("design", "")) or "unknown" for p in papers)
    n_papers = len(papers)
    if n_papers >= 10:
        evidence_density = "high"
    elif n_papers >= 5:
        evidence_density = "moderate"
    else:
        evidence_density = "limited"

    if measurement_rows and confounder_rows:
        design_fit = "strong"
    elif measurement_rows or confounder_rows:
        design_fit = "adequate"
    else:
        design_fit = "limited"

    design_type = normalize(cfg.get("design_type", "observational"))
    if design_type == "cross_sectional":
        causal_temporality_risk = "moderate"
    elif design_type in {"cohort", "trial", "randomized_trial", "interventional"}:
        causal_temporality_risk = "lower"
    else:
        causal_temporality_risk = "context_dependent"

    key_gaps = []
    if any("cross-sectional" in normalize(p.get("design", "")) for p in papers):
        key_gaps.append("A substantial share of the evidence remains cross-sectional or otherwise temporally limited.")
    key_gaps.append("Measurement heterogeneity remains across retained studies.")
    if not confounder_rows:
        key_gaps.append("Confounder support remains under-specified.")

    key_strengths = []
    if roles.get("evidence_synthesis"):
        key_strengths.append("The retained set includes review-level evidence that helps stabilize the field-level summary.")
    if measurement_rows:
        key_strengths.append("The literature supports concrete measurement choices.")
    if confounder_rows:
        key_strengths.append("The literature identifies a plausible covariate structure for downstream modeling.")

    return {
        "project_mode": mode,
        "topic": topic,
        "evidence_density": evidence_density,
        "design_mix": ", ".join(sorted(k for k in design_counts if k)) or "unknown",
        "measurement_support": "strong" if measurement_rows else "limited",
        "confounder_support": "strong" if confounder_rows else "limited",
        "gap_confidence": "moderate",
        "design_fit": design_fit,
        "causal_temporality_risk": causal_temporality_risk,
        "estimand_feasibility": "adequate" if evidence_rows else "limited",
        "interpretation_risk": "moderate" if n_papers else "high",
        "mode_recommendation": mode,
        "downgrade_reason": None if n_papers >= 5 else "sparse_evidence_base",
        "role_counts": dict(roles),
        "key_gaps": key_gaps,
        "key_strengths": key_strengths,
    }


def build_review_contract(topic: str, mode: str, cfg: dict, evidence_table: list[dict[str, str]], papers: list[dict[str, str]]) -> dict:
    review_type = cfg.get("review_type", "structured_narrative")
    reporting_framework = {
        "structured_narrative": ["SANRA"],
        "systematic_no_meta": ["PRISMA 2020", "PRISMA-S", "SWiM"],
        "systematic_meta": ["PRISMA 2020", "PRISMA-S"],
    }.get(review_type, [])
    synthesis_method = {
        "structured_narrative": "thematic critical synthesis by design, outcome, and directness",
        "systematic_no_meta": "SWiM synthesis by design, outcome, directness, and effect direction without significance vote counting",
        "systematic_meta": "quantitative meta-analysis; model and heterogeneity plan require specification",
    }.get(review_type, "")
    return {
        "contract_version": "3.0",
        "review_type": review_type,
        "reporting_framework": reporting_framework,
        "synthesis_method": synthesis_method,
        "project_mode": mode,
        "question_type": cfg.get("question_type", ""),
        "review_goal": cfg.get("review_goal", ""),
        "design_type": cfg.get("design_type", "cross_sectional"),
        "generated_at": date.today().isoformat(),
        "status": "draft",
        "downgrade_state": "" if mode != "workflow_methods" else "workflow_methods_manuscript_only",
        "topic": topic,
        "primary_estimand": cfg.get("primary_estimand", ""),
        "evidence_sufficiency": "not_assessed",
        "decision_ids": [row["decision_id"] for row in evidence_table],
        "citation_ids": [f"C_{row['paper_id']}" for row in papers if row.get("paper_id")],
        # This helper builds a seed package, not a validated mature narrative review.
        "deliverable_style": "evidence_map",
        "narrative_readiness": "brief_only",
        "anchor_density_by_outcome": {},
        "delivery_preset": cfg.get("delivery_preset", "brief"),
        "older_search_cutoff_disclosed": False,
        "sparse_evidence_exception": {"applies": False},
    }


def build_protocol_inputs(topic: str, mode: str, cfg: dict, evidence_rows: list[dict[str, str]], confounders: list[dict[str, str]]) -> dict:
    suggested_methods = []
    for row in evidence_rows:
        methods = row.get("suggested_methods", "")
        if methods and methods not in suggested_methods:
            suggested_methods.append(methods)
    return {
        "project_mode": mode,
        "design_type": cfg.get("design_type", "cross_sectional"),
        "study_title_candidate": topic,
        "population": cfg.get("population", ""),
        "exposure": cfg.get("exposure", ""),
        "outcome": cfg.get("outcome", ""),
        "mediator": cfg.get("candidate_mediator", ""),
        "moderator": cfg.get("candidate_modifier", ""),
        "primary_estimand": cfg.get("primary_estimand", ""),
        "measurement_tools": cfg.get("measurement_tools", []),
        "confounders": [row.get("variable", "") for row in confounders if row.get("variable")],
        "effect_modifiers": [cfg.get("candidate_modifier", "")] if cfg.get("candidate_modifier") else [],
        "suggested_methods": suggested_methods,
        "evidence_gaps": cfg.get("evidence_gaps", []),
        "decision_ids": [],
    }


def build_proposal_bridge(topic: str, mode: str, cfg: dict, sufficiency_report: dict) -> str:
    population = cfg.get("population", "")
    exposure = cfg.get("exposure", "")
    outcome = cfg.get("outcome", "")
    estimand = cfg.get("primary_estimand", "")
    design_type = cfg.get("design_type", "cross_sectional")
    strengths = sufficiency_report.get("key_strengths", [])
    gaps = sufficiency_report.get("key_gaps", [])
    return (
        "# Proposal Bridge\n\n"
        "## Research Problem and Significance\n\n"
        f"The literature supports {topic} as a meaningful research problem"
        f"{' in ' + population if population else ''}.\n\n"
        "## Current Evidence and Stable Findings\n\n"
        + ("\n".join(f"- {item}" for item in strengths) if strengths else "- Evidence strengths need to be summarized from the retained studies.")
        + "\n\n## Gap Statement\n\n"
        + ("\n".join(f"- {item}" for item in gaps) if gaps else "- The key unresolved gap should be stated precisely from the retained evidence.")
        + "\n\n## Proposed Question Lock\n\n"
        + f"- Population: {population or 'FILL IN'}\n"
        + f"- Exposure: {exposure or 'FILL IN'}\n"
        + f"- Outcome: {outcome or 'FILL IN'}\n"
        + f"- Primary estimand: {estimand or 'FILL IN'}\n"
        + f"- Design type: {design_type}\n"
        + f"- Project mode: {mode}\n"
    )


def build_queries(topic: str, cfg: dict) -> list[str]:
    harvest = cfg.get("harvest", {})
    queries = []
    if harvest:
        core = " ".join([harvest.get("outcome", ""), *harvest.get("exposures", []), harvest.get("population", "")]).strip()
        if core:
            queries.append(core)
    exposure = cfg.get("exposure", "")
    outcome = cfg.get("outcome", "")
    population = cfg.get("population", "")
    design_type = cfg.get("design_type", "")
    generic = " ".join(part for part in [exposure, outcome, population, design_type] if part).strip()
    if generic:
        queries.append(generic)
    if topic and topic not in queries:
        queries.append(topic)
    return queries or ["study topic"]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import structured literature-review artifacts from prepared legacy review inputs."
    )
    parser.add_argument("--source-dir", required=True, help="Directory containing prepared legacy inputs such as papers_scored.csv and evidence_matrix.csv")
    parser.add_argument("--output-dir", required=True, help="Directory to write review artifacts")
    parser.add_argument("--project-mode", default="applied_methods", choices=["research", "applied_methods", "workflow_methods"])
    args = parser.parse_args()

    source = Path(args.source_dir)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    papers = read_csv(source / "papers_scored.csv")
    evidence_rows = read_csv(source / "evidence_matrix.csv")
    measurements = read_csv(source / "measurement_tools.csv")
    confounders = read_csv(source / "confounder_candidates.csv")
    cfg = enrich_cfg(find_topic_config(source), evidence_rows, papers)
    topic = cfg.get("topic", "study topic")
    queries = build_queries(topic, cfg)
    evidence_lookup = {row["paper_id"]: row for row in evidence_rows}

    write_csv(output / "search_log.csv", build_search_log(topic, queries), [
        "search_id", "search_round", "parent_search_id", "concept_focus", "query_family", "query", "source",
        "source_query", "date_searched", "date_limit", "language_limit", "recommended_retrieval_target",
        "n_retrieved", "n_after_dedup", "scope", "status", "rationale_trigger", "note"
    ])

    screening_rows = []
    for row in papers:
        evidence_row = evidence_lookup.get(row["paper_id"], {})
        primary_role = infer_primary_role(row, evidence_row)
        screening_rows.append(
            {
                "paper_id": row["paper_id"],
                "title": row.get("title", ""),
                "decision": "include",
                "screening_stage": "legacy_import",
                "role": primary_role,
                "reason": evidence_row.get("protocol_implication", "") or "retained in prepared local evidence package",
                "include_in_synthesis": "yes",
                "include_in_protocol": "yes" if row.get("relevance_score", "") else "no",
                "supporting_evidence_row_ids": f"EV_{row['paper_id']}",
            }
        )
    write_csv(output / "screening_decisions.csv", screening_rows, [
        "paper_id", "title", "decision", "screening_stage", "role", "reason", "include_in_synthesis", "include_in_protocol", "supporting_evidence_row_ids"
    ])

    study_registry = build_study_registry(papers, evidence_lookup)
    write_csv(output / "study_registry.csv", study_registry, [
        "paper_id", "evidence_row_id", "primary_role", "secondary_role", "publication_status", "year", "design", "population", "exposure", "outcome",
        "sample_size", "setting", "measures", "core_findings", "limitations", "protocol_implication",
        "suggested_methods", "relevance_score", "quality_signal"
    ])

    measurement_registry = build_measurement_registry(measurements, cfg)
    write_csv(output / "measurement_registry.csv", measurement_registry, [
        "construct", "preferred_tool", "evidence_role", "reason_from_literature",
        "key_example_paper_ids", "supporting_evidence_row_ids", "protocol_use", "limitation_or_bias"
    ])

    confounder_registry = build_confounder_registry(confounders)
    write_csv(output / "confounder_registry.csv", confounder_registry, [
        "variable", "classification", "support_level", "supporting_paper_ids", "supporting_evidence_row_ids", "rationale", "recommended_main_model_role"
    ])

    evidence_table = build_evidence_table(evidence_rows)
    write_csv(output / "evidence_to_decision_table.csv", evidence_table, [
        "decision_id", "decision", "evidence_summary", "supporting_paper_ids", "supporting_evidence_row_ids", "downstream_use", "confidence"
    ])

    citation_registry = build_citation_registry(topic, args.project_mode, papers, evidence_lookup, evidence_table)
    (output / "citation_registry.json").write_text(json.dumps(citation_registry, ensure_ascii=False, indent=2), encoding="utf-8")

    sufficiency_report = build_sufficiency_report(topic, args.project_mode, papers, evidence_rows, measurements, confounders, cfg)
    (output / "evidence_sufficiency_report.json").write_text(json.dumps(sufficiency_report, ensure_ascii=False, indent=2), encoding="utf-8")

    review_contract = build_review_contract(topic, args.project_mode, cfg, evidence_table, papers)
    (output / "review_contract.json").write_text(json.dumps(review_contract, ensure_ascii=False, indent=2), encoding="utf-8")

    protocol_inputs = build_protocol_inputs(topic, args.project_mode, cfg, evidence_rows, confounders)
    protocol_inputs["decision_ids"] = [row["decision_id"] for row in evidence_table]
    (output / "protocol_inputs.json").write_text(json.dumps(protocol_inputs, ensure_ascii=False, indent=2), encoding="utf-8")

    (output / "proposal_bridge.md").write_text(
        build_proposal_bridge(topic, args.project_mode, cfg, sufficiency_report),
        encoding="utf-8",
    )

    search_strategy = output / "search_strategy.md"
    if not search_strategy.exists():
        search_strategy.write_text(
            "# Search Strategy\n\n"
            f"**Topic:** {topic}\n\n"
            "## Core Queries\n\n"
            + "\n".join(f"- {q}" for q in queries)
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
