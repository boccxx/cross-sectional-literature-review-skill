#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def unique(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        v = value.strip()
        if v and v not in out:
            out.append(v)
    return out


def build_text(review_dir: Path) -> str:
    contract = read_json(review_dir / "review_contract.json")
    suff = read_json(review_dir / "evidence_sufficiency_report.json")
    study = read_csv(review_dir / "study_registry.csv")
    measurement = read_csv(review_dir / "measurement_registry.csv")
    confounders = read_csv(review_dir / "confounder_registry.csv")
    decisions = read_csv(review_dir / "evidence_to_decision_table.csv")
    protocol_inputs = read_json(review_dir / "protocol_inputs.json")

    topic = contract.get("topic", "the target study question")
    population = contract.get("population") or protocol_inputs.get("population", "")
    exposure = contract.get("exposure") or protocol_inputs.get("exposure", "")
    outcome = contract.get("outcome") or protocol_inputs.get("outcome", "")
    estimand = contract.get("primary_estimand") or protocol_inputs.get("primary_estimand", "")
    mode = contract.get("project_mode", "")
    design_type = contract.get("design_type", "")

    strength_items = suff.get("key_strengths", [])
    if not strength_items:
        strength_items = [row.get("decision", "") for row in decisions[:3] if row.get("decision")]

    gap_items = suff.get("key_gaps", [])
    if not gap_items:
        gap_items = protocol_inputs.get("evidence_gaps", [])

    tools = unique([row.get("preferred_tool", "") for row in measurement])
    core_confounders = unique(
        [row.get("variable", "") for row in confounders if "confounder" in row.get("classification", "")]
    )
    mechanism_variables = unique(
        [row.get("variable", "") for row in confounders if "mediator" in row.get("classification", "")]
    )
    designs = unique([row.get("design", "") for row in study])

    lines = [
        "# Proposal Bridge",
        "",
        "## Research Problem and Significance",
        "",
        f"The literature supports {topic} as a meaningful research problem"
        + (f" in {population}" if population else "")
        + ".",
        "",
        "## Current Evidence and Stable Findings",
        "",
    ]
    if strength_items:
        lines.extend([f"- {item}" for item in strength_items])
    else:
        lines.append("- The retained literature is sufficient to define a bounded research problem.")

    lines.extend([
        "",
        "## Gap Statement",
        "",
    ])
    if gap_items:
        lines.extend([f"- {item}" for item in gap_items])
    else:
        lines.append("- The main unresolved gap should be stated more precisely after screening and synthesis.")

    lines.extend([
        "",
        "## Proposed Question Lock",
        "",
        f"- Population: {population or 'FILL IN'}",
        f"- Exposure: {exposure or 'FILL IN'}",
        f"- Outcome: {outcome or 'FILL IN'}",
        f"- Primary estimand: {estimand or 'FILL IN'}",
        f"- Design type: {design_type or 'FILL IN'}",
        f"- Project mode: {mode or 'FILL IN'}",
        "",
        "## Measurement and Variable Feasibility",
        "",
        f"- Common study designs in the retained evidence: {', '.join(designs) if designs else 'not yet summarized'}",
        f"- Candidate measurement tools: {', '.join(tools) if tools else 'not yet summarized'}",
        "",
        "## Confounder and Mechanism Boundary",
        "",
        f"- Core confounder candidates: {', '.join(core_confounders) if core_confounders else 'not yet summarized'}",
        f"- Variables that should stay out of the primary model unless justified: {', '.join(mechanism_variables) if mechanism_variables else 'none yet classified'}",
        "",
        "## Risks and Downgrade Triggers",
        "",
        f"- Evidence sufficiency recommendation: {suff.get('mode_recommendation', 'not available')}",
        f"- Design fit: {suff.get('design_fit', 'not available')}",
        f"- Causal-temporality risk: {suff.get('causal_temporality_risk', 'not available')}",
        f"- Interpretation risk: {suff.get('interpretation_risk', 'not available')}",
        "",
        "## Opening-Report Use",
        "",
        "Use this bridge to write significance, gap, innovation, and feasibility sections in the opening report without overstating causality or evidence strength.",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build proposal_bridge.md from a review package.")
    parser.add_argument("review_dir")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    review_dir = Path(args.review_dir)
    output = Path(args.output) if args.output else review_dir / "proposal_bridge.md"
    output.write_text(build_text(review_dir), encoding="utf-8")


if __name__ == "__main__":
    main()
