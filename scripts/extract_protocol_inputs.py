#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path


def unique_nonempty(values):
    seen = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return seen


def main() -> None:
    parser = argparse.ArgumentParser(description="Build protocol_inputs.json from an evidence matrix CSV.")
    parser.add_argument("evidence_matrix_csv")
    parser.add_argument("output_json")
    parser.add_argument("--title", default="")
    parser.add_argument("--project-mode", default="")
    parser.add_argument("--population", default="")
    parser.add_argument("--exposure", default="")
    parser.add_argument("--outcome", default="")
    parser.add_argument("--mediator", default="")
    parser.add_argument("--moderator", default="")
    args = parser.parse_args()

    rows = list(csv.DictReader(Path(args.evidence_matrix_csv).read_text(encoding="utf-8").splitlines()))
    payload = {
        "project_mode": args.project_mode,
        "study_title_candidate": args.title,
        "population": args.population,
        "exposure": args.exposure,
        "outcome": args.outcome,
        "mediator": args.mediator,
        "moderator": args.moderator,
        "measurement_tools": unique_nonempty(row.get("measures", "") for row in rows),
        "confounders": unique_nonempty(row.get("candidate_confounders", "") for row in rows),
        "effect_modifiers": unique_nonempty(row.get("candidate_effect_modifiers", "") for row in rows),
        "suggested_methods": unique_nonempty(row.get("suggested_methods", "") for row in rows),
        "evidence_gaps": unique_nonempty(row.get("protocol_implication", "") for row in rows),
    }
    Path(args.output_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
