#!/usr/bin/env python3
"""Semantic/provenance checks that structural CSV validation cannot provide."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
from typing import Any


EXECUTED = {"retrieved", "completed", "searched", "executed"}
PLACEHOLDER_ABSTRACT = re.compile(
    r"identity[- ]resolved candidate|retained for direct evidence|abstract unavailable|placeholder|todo|tbd",
    re.I,
)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "yes", "true", "y"}


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def record_key(row: dict[str, str]) -> str:
    doi = (row.get("doi") or "").strip().lower().removeprefix("https://doi.org/")
    return f"doi:{doi}" if doi else f"title:{norm(row.get('title', ''))}"


def raw_candidate_identity(row: dict[str, Any]) -> tuple[str, str, str]:
    source_id = norm(str(row.get("source_record_id") or ""))
    doi = str(row.get("doi") or "").strip().lower().removeprefix("https://doi.org/")
    title = norm(str(row.get("title") or ""))
    return source_id, doi, title


def integer(row: dict[str, str], field: str, errors: list[str], label: str) -> int:
    value = (row.get(field) or "").strip()
    if not value.isdigit():
        errors.append(f"{label} lacks integer {field}")
        return 0
    return int(value)


def validate_semantics(root: Path) -> list[str]:
    errors: list[str] = []
    log = read_csv(root / "search_log.csv")
    raw = read_csv(root / "candidate_records_raw.csv")
    dedup = read_csv(root / "candidate_records_dedup.csv")
    screening = read_csv(root / "screening_decisions.csv")
    studies = read_csv(root / "study_registry.csv")
    effects = read_csv(root / "effect_registry.csv")
    appraisals = read_csv(root / "quality_appraisal_registry.csv")
    fulltexts = read_csv(root / "fulltext_inventory.csv")
    citations = load_json(root / "citation_registry.json").get("entries", [])
    decisions = read_csv(root / "evidence_to_decision_table.csv")
    claims = read_csv(root / "claim_registry.csv")
    diagnostics = load_json(root / "live_search_diagnostics.json")
    flow = load_json(root / "flow_counts.json")
    contract = load_json(root / "review_contract.json")
    protocol = load_json(root / "protocol_inputs.json")
    narrative = (root / "literature_review_synthesis.md").read_text(encoding="utf-8") if (root / "literature_review_synthesis.md").exists() else ""

    # 1. Search ledger and raw payloads must be one-to-one, with no stale files.
    executed = [row for row in log if (row.get("status") or "").strip().lower() in EXECUTED]
    ledger_files: set[str] = set()
    raw_by_search = Counter(row.get("search_id", "") for row in raw)
    dedup_by_search = Counter(row.get("search_id", "") for row in dedup)
    for row in executed:
        sid = (row.get("search_id") or "").strip()
        label = f"search {sid or '?'}"
        raw_file = (row.get("raw_file") or "").strip()
        if not raw_file:
            errors.append(f"{label} is executed but has no raw_file binding")
            continue
        path = root / raw_file
        ledger_files.add(str(path.resolve()))
        if not path.is_file():
            errors.append(f"{label} raw_file does not exist: {raw_file}")
            continue
        try:
            payload = load_json(path)
        except Exception as exc:
            errors.append(f"{label} raw payload is not valid JSON: {exc}")
            continue
        for field in ("search_id", "source", "query", "source_query"):
            if str(payload.get(field, "")).strip() != str(row.get(field, "")).strip():
                errors.append(f"{label} raw payload {field} does not match search_log.csv")
        exported = integer(row, "n_exported", errors, label)
        api_hits = integer(row, "api_total_hits", errors, label)
        if api_hits < exported:
            errors.append(f"{label} api_total_hits is smaller than n_exported")
        if int(payload.get("exported_count", -1)) != exported:
            errors.append(f"{label} raw exported_count does not match n_exported")
        exported_records = payload.get("exported_records")
        if not isinstance(exported_records, list):
            errors.append(f"{label} raw payload is metadata-only and lacks exported_records provider objects")
            exported_records = []
        if len(exported_records) != exported:
            errors.append(f"{label} raw exported_records count {len(exported_records)} does not match n_exported {exported}")
        raw_identities: list[tuple[str, str, str]] = []
        for index, record in enumerate(exported_records, start=1):
            if not isinstance(record, dict):
                errors.append(f"{label} exported_records item {index} is not an object")
                continue
            if not isinstance(record.get("raw_record"), dict) or not record.get("raw_record"):
                errors.append(f"{label} exported_records item {index} lacks the actual provider raw_record object")
            identity = raw_candidate_identity(record)
            if not any(identity):
                errors.append(f"{label} exported_records item {index} lacks source ID, DOI, and title identity")
            raw_identities.append(identity)
        candidate_identities = [raw_candidate_identity(item) for item in raw if item.get("search_id") == sid]
        if Counter(raw_identities) != Counter(candidate_identities):
            errors.append(f"{label} exported provider objects do not identity-match candidate rows by source ID/DOI/title")
        if row.get("source") in {"medRxiv", "bioRxiv"}:
            harvested_records = (payload.get("payload") or {}).get("harvested_records")
            if not isinstance(harvested_records, list) or not harvested_records:
                errors.append(f"{label} preprint payload lacks interval-harvested provider record objects")
            else:
                harvested_keys = {
                    (
                        str(item.get("doi") or "").strip().lower().removeprefix("https://doi.org/"),
                        norm(str(item.get("title") or "")),
                    )
                    for item in harvested_records if isinstance(item, dict)
                }
                for record in exported_records:
                    key = (
                        str(record.get("doi") or "").strip().lower().removeprefix("https://doi.org/"),
                        norm(str(record.get("title") or "")),
                    )
                    if key not in harvested_keys:
                        errors.append(f"{label} exported preprint record is absent from archived interval provider objects: {key}")
        if raw_by_search[sid] != exported:
            errors.append(f"{label} candidate raw rows {raw_by_search[sid]} do not match n_exported {exported}")
        owned = integer(row, "n_after_dedup", errors, label)
        if dedup_by_search[sid] != owned:
            errors.append(f"{label} deduplicated ownership count {dedup_by_search[sid]} does not match n_after_dedup {owned}")

    actual_raw_files = {
        str(path.resolve()) for path in (root / "raw_results").glob("*.json")
    } if (root / "raw_results").is_dir() else set()
    if actual_raw_files != ledger_files:
        stale = sorted(Path(path).name for path in actual_raw_files - ledger_files)
        missing = sorted(Path(path).name for path in ledger_files - actual_raw_files)
        errors.append(f"raw_results/search_log one-to-one mapping failed; stale={stale}, missing={missing}")
    if len(raw) != sum(int(row.get("n_exported") or 0) for row in executed):
        errors.append("candidate_records_raw row count does not equal summed executed-search n_exported")
    if len(dedup) != sum(int(row.get("n_after_dedup") or 0) for row in executed):
        errors.append("candidate_records_dedup row count does not equal summed n_after_dedup ownership")
    if len({record_key(row) for row in dedup}) != len(dedup):
        errors.append("candidate_records_dedup still contains duplicate DOI/title identities")
    if not {record_key(row) for row in dedup}.issubset({record_key(row) for row in raw}):
        errors.append("candidate_records_dedup contains records absent from candidate_records_raw")
    if diagnostics:
        if int(diagnostics.get("candidate_row_count", -1)) != len(raw):
            errors.append("live_search_diagnostics candidate_row_count conflicts with candidate_records_raw")
        if int(diagnostics.get("dedup_candidate_row_count", -1)) != len(dedup):
            errors.append("live_search_diagnostics dedup_candidate_row_count conflicts with candidate_records_dedup")
        if int(diagnostics.get("raw_payload_count", -1)) != len(actual_raw_files):
            errors.append("live_search_diagnostics raw_payload_count conflicts with raw_results")

    # 2. Candidate abstracts must be content, not repeated screening boilerplate.
    if raw:
        abstracts = [(row.get("abstract") or "").strip() for row in raw]
        substantive = [a for a in abstracts if len(a) >= 80 and not PLACEHOLDER_ABSTRACT.search(a)]
        if len(substantive) / len(abstracts) < 0.70:
            errors.append(f"candidate_records_raw has authentic/substantive abstracts for only {len(substantive)}/{len(abstracts)} rows; require at least 70%")
        dominant = Counter(norm(a) for a in abstracts if a).most_common(1)
        if dominant and dominant[0][1] / len(abstracts) > 0.10:
            errors.append("candidate_records_raw contains a dominant repeated abstract/placeholder string")
    if any(PLACEHOLDER_ABSTRACT.search((row.get("abstract") or "")) for row in dedup):
        errors.append("candidate_records_dedup contains placeholder abstract text")

    # 3. Screening is one row per deduplicated record and flow comes from row-level states.
    required_screen_cols = {"report_sought", "report_retrieved", "content_assessed", "full_text_assessed", "content_level", "access_type", "evidence_lane", "source_file"}
    if screening and not required_screen_cols.issubset(screening[0]):
        errors.append("screening_decisions.csv lacks report/full-text/content-level provenance columns")
    screening_keys = [record_key(row) for row in screening]
    if Counter(screening_keys) != Counter(record_key(row) for row in dedup):
        errors.append("screening_decisions must map one-to-one to candidate_records_dedup by DOI/title")
    computed_flow = {
        "api_total_hits": sum(int(row.get("api_total_hits") or 0) for row in executed),
        "records_exported": len(raw),
        "records_after_deduplication": len(dedup),
        "title_abstract_screened": len(screening),
        "total_content_assessed": sum(truthy(row.get("content_assessed")) for row in screening),
        "total_full_text_access": sum(truthy(row.get("content_assessed")) and row.get("access_type") == "full_text" for row in screening),
        "total_authoritative_abstract_access": sum(truthy(row.get("content_assessed")) and row.get("access_type") == "authoritative_abstract" for row in screening),
        "direct_empirical_content_assessed": sum(truthy(row.get("content_assessed")) and row.get("evidence_lane") == "direct_empirical" for row in screening),
        "direct_empirical_full_text_access": sum(truthy(row.get("content_assessed")) and row.get("evidence_lane") == "direct_empirical" and row.get("access_type") == "full_text" for row in screening),
        "direct_empirical_authoritative_abstract_access": sum(truthy(row.get("content_assessed")) and row.get("evidence_lane") == "direct_empirical" and row.get("access_type") == "authoritative_abstract" for row in screening),
        "direct_empirical_included": sum(truthy(row.get("include_in_synthesis")) and row.get("evidence_lane") == "direct_empirical" for row in screening),
        "direct_empirical_excluded": sum(row.get("decision") == "exclude" and row.get("evidence_lane") == "direct_empirical" and truthy(row.get("content_assessed")) for row in screening),
        "contextual_content_assessed": sum(truthy(row.get("content_assessed")) and row.get("evidence_lane") == "contextual" for row in screening),
        "contextual_full_text_access": sum(truthy(row.get("content_assessed")) and row.get("evidence_lane") == "contextual" and row.get("access_type") == "full_text" for row in screening),
        "contextual_authoritative_abstract_access": sum(truthy(row.get("content_assessed")) and row.get("evidence_lane") == "contextual" and row.get("access_type") == "authoritative_abstract" for row in screening),
        "contextual_included": sum(truthy(row.get("include_in_synthesis")) and row.get("evidence_lane") == "contextual" for row in screening),
        "included_in_synthesis": sum(truthy(row.get("include_in_synthesis")) for row in screening),
    }
    for field, value in computed_flow.items():
        if int(flow.get(field, -1)) != value:
            errors.append(f"flow_counts.json {field}={flow.get(field)} does not match row-level truth {value}")
    if int(flow.get("direct_empirical_content_assessed", -1)) - int(flow.get("direct_empirical_excluded", -1)) != int(flow.get("direct_empirical_included", -1)):
        errors.append("flow direct empirical arithmetic must satisfy content assessed minus excluded equals included")
    if int(flow.get("direct_empirical_included", -1)) + int(flow.get("contextual_included", -1)) != int(flow.get("included_in_synthesis", -1)):
        errors.append("flow total must distinguish direct empirical from contextual sources")
    if int(flow.get("total_sources_cited", -1)) != int(flow.get("included_in_synthesis", -1)):
        errors.append("flow total_sources_cited must equal the role-resolved included evidence set")
    if int(flow.get("total_full_text_access", -1)) + int(flow.get("total_authoritative_abstract_access", -1)) != int(flow.get("total_content_assessed", -1)):
        errors.append("flow access arithmetic must distinguish full text from authoritative abstract content")
    for row in screening:
        if truthy(row.get("full_text_assessed")) and not truthy(row.get("report_retrieved")):
            errors.append(f"{row.get('paper_id')} claims full-text assessment without report retrieval")
        if truthy(row.get("full_text_assessed")) != (row.get("access_type") == "full_text" and truthy(row.get("content_assessed"))):
            errors.append(f"{row.get('paper_id')} full_text_assessed conflicts with access_type/content_assessed")
        if truthy(row.get("include_in_synthesis")) and not truthy(row.get("content_assessed")):
            errors.append(f"{row.get('paper_id')} is included without content assessment")
        source_file = root / (row.get("source_file") or "")
        if truthy(row.get("content_assessed")) and (not source_file.is_file() or source_file.stat().st_size == 0):
            errors.append(f"{row.get('paper_id')} content assessment lacks archived source_file")
        if row.get("evidence_lane") == "contextual" and (row.get("role") or "").lower() in {"direct_evidence", "counterevidence", "inconsistent_evidence"}:
            errors.append(f"{row.get('paper_id')} contextual source is mislabeled as a direct empirical report")

    # 4. Full-text/content locators must bind every numerical direct effect to an archived source.
    fulltext_by_id = {row.get("paper_id", ""): row for row in fulltexts}
    direct_ids = {
        row.get("paper_id", "") for row in studies
        if (row.get("primary_role") or "").strip().lower() in {"direct_evidence", "counterevidence", "inconsistent_evidence"}
    }
    for effect in effects:
        pid = (effect.get("paper_id") or effect.get("study_id") or "").strip()
        if pid not in direct_ids:
            continue
        for field in ("source_file", "source_locator", "evidence_snippet"):
            if len((effect.get(field) or "").strip()) < (20 if field == "evidence_snippet" else 3):
                errors.append(f"direct effect {effect.get('effect_id')} ({pid}) lacks substantive {field}")
        source = root / (effect.get("source_file") or "")
        if not source.is_file() or source.stat().st_size == 0:
            errors.append(f"direct effect {effect.get('effect_id')} ({pid}) source_file is missing/empty")
        if pid not in fulltext_by_id:
            errors.append(f"direct effect {effect.get('effect_id')} ({pid}) has no fulltext_inventory row")
    central_direct_ids = {
        str(pid).strip() for pid in contract.get("central_direct_paper_ids", []) if str(pid).strip()
    }
    if not central_direct_ids:
        central_direct_ids = {
            row.get("paper_id", "") for row in studies
            if truthy(row.get("anchor_eligible")) and (row.get("primary_role") or "").strip().lower() == "direct_evidence"
        }
    for central in sorted(central_direct_ids):
        rows = [row for row in effects if row.get("paper_id") == central]
        if not rows or any(not row.get("source_locator") or not row.get("source_file") for row in rows):
            errors.append(f"central direct study {central} lacks content-level effect provenance")

    # 5. Study and appraisal registries must contain paper-specific facts.
    if studies:
        key_fields = ("population", "exposure", "outcome", "setting", "measures", "core_findings", "limitations")
        signatures = Counter(tuple(norm(row.get(field, "")) for field in key_fields) for row in studies)
        if signatures.most_common(1)[0][1] / len(studies) > 0.15:
            errors.append("study_registry.csv is dominated by repeated template study-characteristic rows")
        for row in studies:
            if any(len((row.get(field) or "").strip()) < 12 for field in key_fields):
                errors.append(f"study_registry.csv {row.get('paper_id')} lacks study-specific characteristic detail")
    appraisal_by_id: dict[str, list[dict[str, str]]] = defaultdict(list)
    appraisal_signatures: Counter[tuple[str, str]] = Counter()
    for row in appraisals:
        appraisal_by_id[row.get("paper_id", "")].append(row)
        appraisal_signatures[(norm(row.get("raw_signal", "")), norm(row.get("evidence_source", "")))] += 1
        source_ref = (row.get("evidence_source") or "").split("::", 1)[0]
        if "::" not in (row.get("evidence_source") or ""):
            errors.append(f"appraisal {row.get('paper_id')}:{row.get('domain')} lacks source_file::locator evidence_source")
        elif not (root / source_ref).is_file():
            errors.append(f"appraisal {row.get('paper_id')}:{row.get('domain')} references missing source {source_ref}")
        if len((row.get("raw_signal") or "").strip()) < 35:
            errors.append(f"appraisal {row.get('paper_id')}:{row.get('domain')} raw_signal is not study-specific")
        capability = (row.get("source_capability") or "").strip().lower()
        judgment = (row.get("judgment") or "").strip().lower()
        domain = (row.get("domain") or "").strip().lower()
        signal = (row.get("raw_signal") or "").strip().lower()
        if capability == "authoritative_abstract" and any(token in signal for token in ("does not report", "does not provide", "omits", "insufficient")):
            if not any(token in judgment for token in ("unclear", "not assessable")):
                errors.append(f"appraisal {row.get('paper_id')}:{row.get('domain')} overjudges an unreported abstract-only domain")
        if capability == "authoritative_abstract" and any(token in domain for token in ("selection", "attrition")) and any(token in judgment for token in ("low concern", "adequate")):
            errors.append(f"appraisal {row.get('paper_id')}:{row.get('domain')} assigns favorable selection/attrition judgment from abstract-only access")
        design = next((item.get("design", "").lower() for item in studies if item.get("paper_id") == row.get("paper_id")), "")
        if capability == "full_text" and any(token in design for token in ("cohort", "prospective", "longitudinal")) and any(token in domain for token in ("selection", "attrition")):
            if not re.search(r"\b\d[\d,]*(?:%|\b)", signal) or not any(token in signal for token in ("retained", "leaving", "excluded", "follow-up", "remaining", "entered")):
                errors.append(f"cohort appraisal {row.get('paper_id')} lacks actual participant-flow/attrition facts despite full-text access")
    if appraisals and appraisal_signatures.most_common(1)[0][1] / len(appraisals) > 0.10:
        errors.append("quality_appraisal_registry.csv repeats the same signal/source across too many domains")
    claim_bearing = {row.get("paper_id", "") for row in fulltexts if truthy(row.get("claim_bearing"))}
    for pid in claim_bearing:
        if len(appraisal_by_id.get(pid, [])) < 4:
            errors.append(f"claim-bearing study {pid} lacks four study-specific appraisal domains")

    # 6. Counterevidence and citation bindings must be semantically specific.
    study_role = {row.get("paper_id", ""): (row.get("primary_role") or "").strip().lower() for row in studies}
    effect_direction = defaultdict(set)
    for row in effects:
        effect_direction[row.get("paper_id", "")].add((row.get("direction") or "").strip().lower())
    for claim in claims:
        for pid in re.split(r"[,;|]", claim.get("counter_study_ids") or ""):
            pid = pid.strip()
            if not pid:
                continue
            if study_role.get(pid) not in {"counterevidence", "inconsistent_evidence"}:
                errors.append(f"claim {claim.get('claim_id')} counter study {pid} is not classified as genuine counter/inconsistent evidence")
            if not (effect_direction.get(pid, set()) & {"null", "mixed", "heterogeneous", "inconsistent"}):
                errors.append(f"claim {claim.get('claim_id')} counter study {pid} has no null/mixed/inconsistent effect row")
    decision_papers = {row.get("decision_id", ""): set(re.split(r"[,;|]", row.get("supporting_paper_ids") or "")) for row in decisions}
    citation_signatures = Counter()
    for entry in citations:
        pid = str(entry.get("paper_id", ""))
        decision_ids = {str(x).strip() for x in entry.get("supporting_decision_ids", []) if str(x).strip()}
        effect_ids = {str(x).strip() for x in entry.get("supporting_evidence_row_ids", []) if str(x).strip()}
        claim_ids = {str(x).strip() for x in entry.get("supporting_claim_ids", []) if str(x).strip()}
        citation_signatures[(entry.get("claim_supported", ""), tuple(sorted(decision_ids)), tuple(sorted(effect_ids)), tuple(sorted(claim_ids)))] += 1
        if not claim_ids:
            errors.append(f"citation {entry.get('citation_id')} lacks specific supporting_claim_ids")
        if entry.get("evidence_lane") == "contextual":
            for field in ("content_source_file", "content_locator", "content_snippet"):
                if len(str(entry.get(field) or "").strip()) < (35 if field == "content_snippet" else 5):
                    errors.append(f"contextual citation {entry.get('citation_id')} lacks substantive {field}")
            content_source = root / str(entry.get("content_source_file") or "")
            if not content_source.is_file() or content_source.stat().st_size == 0:
                errors.append(f"contextual citation {entry.get('citation_id')} references missing archived content")
        for did in decision_ids:
            if pid not in decision_papers.get(did, set()):
                errors.append(f"citation {entry.get('citation_id')} claims decision {did} but {pid} is absent from that decision row")
        for eid in effect_ids:
            owner = next((row.get("paper_id") for row in effects if row.get("effect_id") == eid), None)
            if owner != pid:
                errors.append(f"citation {entry.get('citation_id')} effect {eid} belongs to {owner}, not {pid}")
    if citations and citation_signatures.most_common(1)[0][1] / len(citations) > 0.15:
        errors.append("citation_registry.json is dominated by generic all-purpose claim/decision bindings")

    # 7. Protocol decisions must be locked identically across contract, protocol,
    # decisions, confounder registry, and reader-facing narrative.
    decision_text = " ".join((row.get("decision") or "") for row in decisions).lower()
    contract_lock = " ".join(str(contract.get(field, "")) for field in ("primary_estimand", "secondary_estimand", "primary_contrast", "primary_adjustment_policy")).lower()
    protocol_lock = " ".join(str(protocol.get(field, "")) for field in ("comparison", "primary_estimand", "secondary_estimand", "mediator")).lower()
    for label, text in (("review_contract", contract_lock), ("protocol_inputs", protocol_lock), ("evidence_to_decision_table", decision_text), ("narrative", narrative.lower())):
        if "p75" not in text or "prevalence ratio" not in text:
            errors.append(f"{label} does not lock the primary weighted P75 prevalence-ratio contrast")
        if not ("10-percentage-point" in text or "10 percentage-point" in text):
            errors.append(f"{label} does not lock the per-10-point exposure estimand as secondary")
    sensitivity_terms = ("bmi", "sleep", "diet quality", "inflammation")
    sensitivity_rows = [row for row in read_csv(root / "confounder_registry.csv") if all(term in (row.get("variable") or "").lower() for term in sensitivity_terms)]
    if len(sensitivity_rows) != 1 or "sensitivity-only" not in sensitivity_rows[0].get("recommended_main_model_role", "").lower() or "not a primary confounder" not in sensitivity_rows[0].get("classification", "").lower():
        errors.append("confounder_registry must classify BMI/sleep/diet quality/inflammation as sensitivity-only and not primary confounders")
    primary_confounder_blob = " ".join(str(x).lower() for x in protocol.get("confounders", []))
    if any(term in primary_confounder_blob for term in sensitivity_terms):
        errors.append("protocol_inputs confounders improperly include sensitivity-only BMI/sleep/diet quality/inflammation")
    if set(str(x).lower() for x in protocol.get("sensitivity_only_variables", [])) != {"bmi", "sleep", "overall diet quality", "inflammation"}:
        errors.append("protocol_inputs sensitivity_only_variables must exactly enumerate BMI, sleep, overall diet quality, and inflammation")
    if narrative:
        opening = narrative.split("## Evidence Map", 1)[0]
        if "dietary interventions" in opening.lower() and not re.search(r"dietary interventions[^\n]{0,220}\[29\]", opening, re.I):
            errors.append("narrative dietary-intervention opening claim is not bound to reference [29]")
        umbrella_context = " ".join(part for part in narrative.split("\n\n") if "umbrella" in part.lower())
        if not all(token in umbrella_context.lower() for token in ("class i", "class ii", "low quality")):
            errors.append("narrative umbrella evidence must state class I combined common disorders, class II depressive outcomes, and low quality separately")

    # 8. Flow display and its visual inspection are release evidence, not optional decoration.
    for name in ("flow_diagram.svg", "flow_diagram.png", "visual_inspection_report.json"):
        path = root / name
        if not path.is_file() or path.stat().st_size == 0:
            errors.append(f"missing visual flow artifact: {name}")
    visual = load_json(root / "visual_inspection_report.json")
    if visual.get("status") != "pass" or not visual.get("inspected_file_sha256"):
        errors.append("visual_inspection_report.json must record a passed human/agent inspection and inspected file hash")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate literature-review provenance and semantic integrity.")
    parser.add_argument("review_dir")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    root = Path(args.review_dir)
    errors = validate_semantics(root)
    report = {"validator": "review_semantic_provenance", "status": "fail" if errors else "pass", "errors": errors, "review_dir": str(root)}
    if args.output:
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if errors:
        raise SystemExit("\n".join(errors))
    print("Literature review semantic/provenance validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
