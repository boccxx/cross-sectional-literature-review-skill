#!/usr/bin/env python3
"""Prepare and validate topic-neutral per-paper evidence extraction packets."""
from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path


ALLOWED_DIRECTIONS = {"favorable", "harmful", "null", "mixed", "unclear"}
ALLOWED_DIRECTNESS = {"direct", "indirect", "background"}
ALLOWED_TRUST = {"high", "moderate", "low", "not_applicable"}
ALLOWED_BIAS_SEVERITY = {"high", "moderate", "low", "none_detected", "unclear"}
ALLOWED_BIAS_DIRECTION = {"towards_null", "away_from_null", "uncertain", "not_applicable"}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def included_records(review_dir: Path) -> list[dict[str, str]]:
    scored = read_csv(review_dir / "scored_candidates.csv")
    if scored:
        rows = [row for row in scored if row.get("include_in_review", "").strip().lower() in {"yes", "true", "1", "include"}]
        if rows:
            return rows
    screening = read_csv(review_dir / "screening_decisions.csv")
    include_ids = {
        row.get("paper_id", "")
        for row in screening
        if row.get("include_in_synthesis", "").strip().lower() in {"yes", "true", "1"}
        or row.get("decision", "").strip().lower() == "include"
    }
    studies = read_csv(review_dir / "study_registry.csv")
    return [row for row in studies if row.get("paper_id", "") in include_ids] or studies


def packet_template(record: dict[str, str]) -> dict:
    paper_id = record.get("paper_id") or record.get("id") or ""
    return {
        "paper_id": paper_id,
        "citation_title": record.get("title", ""),
        "source_file_or_url": record.get("fulltext_path") or record.get("url") or "",
        "text_source": "abstract | fulltext | unavailable",
        "deep_read_date": "",
        "claim_bearing": "yes | no",
        "study_design": record.get("study_design") or record.get("design") or "",
        "population_summary": record.get("population", ""),
        "direct_question_match": "yes | no | unclear",
        "comparator_integrity_ok": "yes | no | unclear | NA",
        "time_zero_clear": "yes | no | unclear | NA",
        "prior_user_design": "yes | no | unclear | NA",
        "effect_rows": [],
        "bias_appraisal": [],
        "quality_appraisal": [
            {
                "domain": "",
                "judgment": "",
                "raw_signal": "",
                "evidence_source": "section/table/page",
                "note": "",
            }
        ],
        "study_contribution": {"can_support": "", "cannot_support": "", "main_limitation": ""},
        "review_status": "needs_manual_extraction",
    }


def prepare(review_dir: Path) -> int:
    packets_dir = review_dir / "fulltext_extractions"
    packets_dir.mkdir(parents=True, exist_ok=True)
    created = 0
    for record in included_records(review_dir):
        paper_id = record.get("paper_id") or record.get("id") or ""
        if not paper_id:
            continue
        path = packets_dir / f"{paper_id}.json"
        if not path.exists():
            write_json(path, packet_template(record))
            created += 1
    print(f"Prepared {created} new extraction packet(s) in {packets_dir}")
    return created


def validate_packet(path: Path, payload: dict) -> list[str]:
    errors: list[str] = []
    paper_id = payload.get("paper_id") or path.stem
    if payload.get("review_status") != "complete":
        errors.append(f"{paper_id}: review_status must be 'complete'")
    for field in ("study_design", "population_summary", "direct_question_match"):
        if not str(payload.get(field, "")).strip():
            errors.append(f"{paper_id}: missing {field}")
    if not str(payload.get("deep_read_date", "")).strip():
        errors.append(f"{paper_id}: deep_read_date is required for a completed extraction")
    if str(payload.get("text_source", "")).strip().lower() in {"", "abstract", "unavailable", "abstract | fulltext | unavailable"}:
        errors.append(f"{paper_id}: completed deep reading requires a full-text or authoritative-report text_source")
    contribution = payload.get("study_contribution", {})
    for field in ("can_support", "cannot_support", "main_limitation"):
        if not str(contribution.get(field, "")).strip():
            errors.append(f"{paper_id}: study_contribution.{field} is empty")
    for idx, row in enumerate(payload.get("effect_rows", []), start=1):
        prefix = f"{paper_id} effect row {idx}"
        for field in ("outcome_family", "outcome", "effect_measure", "direction", "quote_text", "quote_source", "effect_directness", "effect_trustworthiness"):
            if not str(row.get(field, "")).strip():
                errors.append(f"{prefix}: missing {field}")
        if row.get("direction") not in ALLOWED_DIRECTIONS:
            errors.append(f"{prefix}: invalid direction")
        if row.get("effect_directness") not in ALLOWED_DIRECTNESS:
            errors.append(f"{prefix}: invalid effect_directness")
        if row.get("effect_trustworthiness") not in ALLOWED_TRUST:
            errors.append(f"{prefix}: invalid effect_trustworthiness")
        estimate = str(row.get("point_estimate", "")).strip()
        if not estimate:
            errors.append(f"{prefix}: missing point_estimate; use NR only after checking the full text")
        elif estimate.lower() not in {"nr", "not reported"}:
            if not str(row.get("ci_lower", "")).strip() or not str(row.get("ci_upper", "")).strip():
                errors.append(f"{prefix}: numeric point_estimate requires ci_lower and ci_upper")
    for idx, row in enumerate(payload.get("bias_appraisal", []), start=1):
        prefix = f"{paper_id} bias row {idx}"
        if row.get("severity") not in ALLOWED_BIAS_SEVERITY:
            errors.append(f"{prefix}: invalid severity")
        if row.get("bias_direction") not in ALLOWED_BIAS_DIRECTION:
            errors.append(f"{prefix}: invalid bias_direction")
        if not str(row.get("evidence_of_bias", "")).strip():
            errors.append(f"{prefix}: evidence_of_bias is empty")
    appraisal = payload.get("quality_appraisal", [])
    if len({str(row.get("domain", "")).strip().lower() for row in appraisal if str(row.get("domain", "")).strip()}) < 4:
        errors.append(f"{paper_id}: quality_appraisal must cover at least 4 distinct design-appropriate domains")
    for idx, row in enumerate(appraisal, start=1):
        prefix = f"{paper_id} quality row {idx}"
        for field in ("domain", "judgment", "raw_signal", "evidence_source"):
            value = str(row.get(field, "")).strip()
            if not value or value.lower() in {"todo", "tbd", "fill in", "section/table/page"}:
                errors.append(f"{prefix}: missing or placeholder {field}")
    return errors


def finalize(review_dir: Path) -> None:
    packets = sorted((review_dir / "fulltext_extractions").glob("*.json"))
    if not packets:
        raise SystemExit("No extraction packets found; run without --finalize first.")
    effect_rows: list[dict] = []
    bias_rows: list[dict] = []
    inventory_rows: list[dict] = []
    quality_rows: list[dict] = []
    errors: list[str] = []
    for path in packets:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{path.name}: invalid JSON: {exc}")
            continue
        errors.extend(validate_packet(path, payload))
        paper_id = payload.get("paper_id") or path.stem
        inventory_rows.append(
            {
                "paper_id": paper_id,
                "title": payload.get("citation_title", ""),
                "text_source": payload.get("text_source", ""),
                "fulltext_status": payload.get("review_status", ""),
                "source_file": payload.get("source_file_or_url", ""),
                "deep_read_completed": "yes" if payload.get("review_status") == "complete" else "no",
                "deep_read_date": payload.get("deep_read_date") or date.today().isoformat(),
                "claim_bearing": payload.get("claim_bearing", "yes"),
                "note": payload.get("study_contribution", {}).get("main_limitation", ""),
            }
        )
        for idx, row in enumerate(payload.get("effect_rows", []), start=1):
            effect_rows.append(
                {
                    "effect_id": row.get("effect_id") or f"{paper_id}_E{idx:02d}",
                    "study_id": paper_id,
                    "paper_id": paper_id,
                    "outcome_family": row.get("outcome_family", ""),
                    "outcome": row.get("outcome", ""),
                    "effect_measure": row.get("effect_measure", ""),
                    "point_estimate": row.get("point_estimate", ""),
                    "ci_lower": row.get("ci_lower", ""),
                    "ci_upper": row.get("ci_upper", ""),
                    "exposure_contrast": row.get("exposure_contrast", ""),
                    "direction": row.get("direction", ""),
                    "effect_directness": row.get("effect_directness", ""),
                    "supports_primary_direction_claim": row.get("supports_primary_direction_claim", "no"),
                    "population_subgroup": row.get("population_subgroup", ""),
                    "effect_trustworthiness": row.get("effect_trustworthiness", ""),
                    "notes": row.get("quote_text", ""),
                }
            )
        for row in payload.get("bias_appraisal", []):
            bias_rows.append(
                {
                    "paper_id": paper_id,
                    "bias_domain": row.get("bias_domain", ""),
                    "severity": row.get("severity", ""),
                    "bias_direction": row.get("bias_direction", ""),
                    "evidence_of_bias": row.get("evidence_of_bias", ""),
                    "reviewer_note": row.get("reviewer_note", ""),
                }
            )
        for row in payload.get("quality_appraisal", []):
            quality_rows.append(
                {
                    "paper_id": paper_id,
                    "domain": row.get("domain", ""),
                    "judgment": row.get("judgment", ""),
                    "raw_signal": row.get("raw_signal", ""),
                    "evidence_source": row.get("evidence_source", ""),
                    "note": row.get("note", ""),
                }
            )
    if errors:
        raise SystemExit("Extraction validation failed:\n" + "\n".join(errors))
    write_csv(review_dir / "effect_registry.csv", effect_rows, ["effect_id", "study_id", "paper_id", "outcome_family", "outcome", "effect_measure", "point_estimate", "ci_lower", "ci_upper", "exposure_contrast", "direction", "effect_directness", "supports_primary_direction_claim", "population_subgroup", "effect_trustworthiness", "notes"])
    write_csv(review_dir / "bias_registry.csv", bias_rows, ["paper_id", "bias_domain", "severity", "bias_direction", "evidence_of_bias", "reviewer_note"])
    write_csv(review_dir / "quality_appraisal_registry.csv", quality_rows, ["paper_id", "domain", "judgment", "raw_signal", "evidence_source", "note"])
    write_csv(review_dir / "fulltext_inventory.csv", inventory_rows, ["paper_id", "title", "text_source", "fulltext_status", "source_file", "deep_read_completed", "deep_read_date", "claim_bearing", "note"])
    print(f"Finalized {len(effect_rows)} effect row(s), {len(bias_rows)} bias row(s), and {len(quality_rows)} quality-appraisal row(s).")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare or validate topic-neutral per-paper evidence extraction packets.")
    parser.add_argument("project_root")
    parser.add_argument("--review-dir", default="")
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    root = Path(args.project_root)
    review_dir = Path(args.review_dir) if args.review_dir else root / "literature_review"
    if args.finalize:
        finalize(review_dir)
    else:
        prepare(review_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
