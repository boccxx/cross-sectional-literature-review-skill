---
name: cross-sectional-literature-review
description: Build auditable, decision-grade literature reviews for cross-sectional study planning, protocol inputs, related work, and manuscript positioning. Use when Codex must search and screen biomedical evidence, appraise study quality, create citation/effect/measurement/confounder registries, constrain claims, or write a narrative review that feeds the cross-sectional study suite.
---

# Cross-Sectional Literature Review

Turn literature into traceable study decisions. Do not treat retrieval counts, a paper list, or a generated briefing as a completed review.

## Operating Contract

Enforce four truths:

1. **Retrieval truth:** distinguish planned, attempted, blocked, and completed searches.
2. **Evidence truth:** read and appraise papers before assigning effect direction or claim strength.
3. **Narrative truth:** write from registries and extracted evidence; never invent citations, counts, estimates, or certainty.
4. **Handoff truth:** downstream protocol and manuscript claims must not exceed the review's sufficiency verdict.

Use the canonical `project_mode` values:

- `research`: real study and empirical manuscript intended
- `applied_methods`: real evidence base, but downstream data are synthetic, pilot, or internal-validation data
- `workflow_methods`: workflow or methods demonstration only

Treat legacy `simulation` and `methods_demo` inputs as aliases for `applied_methods` and `workflow_methods`; write only canonical values to new contracts.

## Delivery Presets

Select the smallest defensible preset:

| Preset | Use when | Minimum outcome |
|---|---|---|
| `brief` | corpus is immature or the user needs an evidence map | search/screening artifacts, core registries, `review_briefing.md` |
| `decision_grade` | evidence must shape a protocol, SAP, or manuscript position | complete decision registries, sufficiency verdict, proposal/protocol bridge, narrative if ready |
| `full_package` | near circulation, handoff, or submission | `decision_grade` plus citation verification and DOCX/PDF/TeX exports |

Do not promise a preset that the evidence, access, or package completeness cannot support. Read `references/mode_policy.md` and `references/downgrade_policy.md` when the requested mode or preset is uncertain.

## Intake Gate

Before retrieval, resolve or record as open:

- population, setting, exposure/comparison, and outcome families
- intended study design and downstream decision
- date, language, and study-design limits
- `project_mode`, `question_type`, and `review_goal`
- `review_type = structured_narrative | systematic_no_meta | systematic_meta`
- candidate mediators/modifiers only as hypotheses, not settled roles

Use the allowed `question_type` and `review_goal` values in `references/output_schema.md`. Keep manifest topic labels short; put synonyms, instruments, thresholds, and long outcome lists in retrieval configuration or registries.

Route reporting and synthesis by `review_type`; never blend the three products implicitly:

- `structured_narrative`: use SANRA as a quality aid; retain reproducible search and screening without falsely claiming a systematic review
- `systematic_no_meta`: use PRISMA 2020/PRISMA-S and SWiM; group by design/outcome/directness and never count “positive” studies as the synthesis
- `systematic_meta`: use PRISMA 2020/PRISMA-S and prespecify effect harmonization, model, heterogeneity, small-study bias, and sensitivity analyses

Read `references/review_type_and_release_standard.md` before retrieval and drafting.

If missing inputs would materially change eligibility or search syntax, ask targeted questions or produce `open_questions`; do not silently guess.

## Hard Stops

Stop or downgrade when any of these applies:

- no reproducible question or eligibility boundary
- a live search is required but only a fixed local corpus was inspected
- required sources are unsearched and not logged as blocked/unavailable
- an included paper has not been read deeply enough to support the extracted claim
- citation identity or DOI/title matching is unresolved for a claim-bearing source
- claim direction is not traceable to `effect_registry.csv` or per-paper extraction
- a `research` claim is requested but sufficiency recommends a weaker mode
- the narrative contains unsupported study-specific statements or fabricated screening counts
- a package is marked `ready` while queries/counts are placeholders, quality appraisal is empty, or deep reading is undocumented

Use explicit states such as `preliminary_review`, `protocol_draft_only`, or `research_manuscript_blocked`; never hide a downgrade in prose.

## Workflow

### 1. Build the project scaffold and search plan

Use:

```bash
python3 cross-sectional-literature-review/scripts/build_review_scaffold.py --help
python3 cross-sectional-literature-review/scripts/build_search_plan.py --help
```

Record source, query, query purpose, search date, limits, and execution status. Read `references/search_reporting_standard.md`.

### 2. Execute retrieval and preserve raw evidence

Unless the user supplied a fixed corpus, query the free core sources supported by `run_live_search.py`: PubMed/MEDLINE, OpenAlex, Europe PMC, Semantic Scholar, medRxiv, and bioRxiv. Log Embase and Web of Science as `blocked_auth_required` unless valid access exists.

```bash
python3 cross-sectional-literature-review/scripts/run_live_search.py --help
```

A completed run must produce real counts, candidate tables, diagnostics, and raw payloads. Read `references/live_retrieval_standard.md`. Do not describe interval retrieval plus local ranking of preprints as native free-text search.

For every executed search row, preserve the exact source-specific query, execution date, restrictions, hit count, retained/downloaded count, and status. `exposure AND outcome`, empty counts, TODO dates, or prose reconstructions of queries are release blockers. Refresh a search older than six months or disclose and justify the older cutoff.

### 3. Deduplicate, screen, and role-label

Maintain explicit inclusion/exclusion reasons. Assign evidence roles such as direct comparison, indirect support, measurement validation, mechanism, methods, guideline/policy, contradiction, or background.

Reconcile identification, deduplication, title/abstract screening, full-text assessment, exclusion-by-reason, and inclusion totals. Give each full-text exclusion one specific reason code and explanatory reason. A suspicious all-included flow cannot be called complete without a documented sparse-evidence boundary.

### 4. Score candidates, then read anchors

```bash
python3 cross-sectional-literature-review/scripts/score_candidates.py --help
```

Use LLM relevance scores to prioritize reading, not to replace reading. Appraise design-specific credibility using `references/scoring_rubric.md` and `references/study_quality_framework.md`.

### 5. Expand from what the papers reveal

Run reading-driven searches for terminology, instruments, mechanisms, confounding, contradictions, and subgroups. Use citation chasing after anchor identification:

```bash
python3 cross-sectional-literature-review/scripts/chase_citations.py --help
```

Stop only when another focused round no longer changes downstream decisions or adds decision-relevant evidence.

### 6. Extract per-paper evidence before synthesis

For each included claim-bearing paper, record:

- study design, population, directness, comparator integrity, and time zero
- each effect row with outcome, measure, estimate/interval, direction, source location, and trustworthiness
- design-specific bias domains and likely direction
- what the paper can and cannot support

Use `unclear` when evidence is insufficient. Direct quotation snippets must stay within applicable copyright limits and serve verification, not reproduce the paper.

Record deep reading in `fulltext_inventory.csv` with `deep_read_completed`, date, source, and claim-bearing status. Complete at least four design-appropriate appraisal domains per included claim-bearing study and record a study-specific signal plus its source location; repeated template judgments are invalid. For direct studies, extract a point estimate and interval or explicitly record `NR` after checking the full text.

Run full-text refinement when possible:

```bash
python3 cross-sectional-literature-review/scripts/run_fulltext_extraction.py --help
```

### 7. Build registries and decision objects

Populate at minimum:

- `study_registry.csv`
- `measurement_registry.csv`
- `confounder_registry.csv`
- `citation_registry.json`
- `claim_registry.csv`
- `effect_registry.csv` when the question attributes effects or prognosis
- `bias_registry.csv` at the tier required by `references/study_quality_framework.md`
- `evidence_to_decision_table.csv`
- `evidence_sufficiency_report.json`
- `review_contract.json`

Do not select confounders by significance or citation frequency. Separate confounders, mediators, modifiers, and possible colliders using substantive/causal reasoning and record uncertainty.

### 8. Verify citations before prose

```bash
python3 cross-sectional-literature-review/scripts/verify_citations.py --help
```

Resolve `likely_mismatch` and `doi_not_found` records before they support narrative claims. A valid DOI alone does not prove that a paper supports the proposed statement.

### 9. Produce proposal and protocol bridges

Generate `proposal_bridge.md` and `protocol_inputs.json` from registered evidence. Preserve uncertainty: literature outputs may propose, but must not pretend to freeze, sampling operations, institutional governance, or final sample-size decisions.

```bash
python3 cross-sectional-literature-review/scripts/build_proposal_bridge.py --help
python3 cross-sectional-literature-review/scripts/extract_protocol_inputs.py --help
```

### 10. Build the briefing, plan sections, and write the narrative

Run:

```bash
python3 cross-sectional-literature-review/scripts/build_methods_snapshot.py --help
python3 cross-sectional-literature-review/scripts/build_review_narrative.py <project_root>
```

`build_review_narrative.py` writes `review_briefing.md`; it does **not** write the finished review. Read the briefing, `section_packets.json`, `evidence_clusters.json`, and the referenced registries. Then write `literature_review_synthesis.md` section by section.

Read both before drafting:

- `references/narrative_review_standard.md`
- `references/review_writing_blueprint.md`

Use a three-pass narrative process:

1. plan each section's judgment, anchors, strength ceiling, and main limitation
2. draft evidence by theme/outcome rather than one paper at a time
3. globally revise citations, claim strength, repeated phrasing, and meta-language

Make the main body independently useful. Include populated Study Characteristics and Effect Evidence Matrix tables, then synthesize direct evidence separately by cross-sectional and prospective/longitudinal design where both exist. Cover measurement validity, counterevidence, heterogeneity by design/measurement/adjustment, study-level risk of bias, reporting/publication bias, outcome-specific certainty with reasons, and ranked research gaps. Do not move these essentials out of the body.

For `decision_grade` and `full_package`, a one-study narrative is not decision-grade: register at least three eligible claim-bearing sources unless the search proves that fewer exist and the package is explicitly released as a scoped evidence gap rather than a completed review. Allocate space by evidence tension and decision importance, not one paragraph per paper. Each substantive paragraph must add at least one distinct study finding, comparison, limitation, mechanism hypothesis, or design consequence. Theme-swapped boilerplate and near-duplicate paragraphs are hard failures.

For a mature topic, apply the publication-body gate: at least 4,500 body words, 30 identity-resolved references, and 12 documented deep-read studies before `decision_grade` or `full_package` release. Target 5,500–6,500 body words, 45–70 verified references, and 12–20 deep reads. These are completeness signals, not padding targets. Permit lower counts only through `sparse_evidence_exception` with a precise scope boundary, saturated searches, and a defensible rationale; the validator still requires truthful synthesis and tables.

Every study-specific finding needs the numeric inline marker assigned by `citation_registry.reference_number`; the binding layer must resolve that number to the citation/study registry. Internal paper/citation IDs stay in registries, not reader-facing prose. Numbered References entries must match registered title and, when available, first author, year, and DOI. Direct evidence may support direction-of-effect claims; indirect, background, guideline, or policy evidence may not substitute for it.

### 11. Validate and export

```bash
python3 cross-sectional-literature-review/scripts/validate_review_package.py <review_dir>
python3 external_standards/scripts/validate_literature_review_standard.py <review_dir> --output <report.json>
python3 cross-sectional-literature-review/scripts/export_review.py --help
```

For `full_package`, also build the publication package. The release validator requires a real PDF parser (`pdfinfo` from Poppler or `pypdf`), exact citation-verification coverage, and `publication_manifest.json` v2.1. DOCX, PDF, and TeX exports embed the SHA-256 of the current synthesis; stale exports, missing sources, manifest hash/size drift, and source-fingerprint mismatches are hard failures.

## Required Artifact Matrix

Read `references/output_schema.md` for exact columns and contracts. The following distinctions are mandatory:

- retrieval artifacts prove what was searched
- screening artifacts prove why records moved forward
- evidence registries prove what studies can support
- decision objects prove how literature influenced the planned study
- `review_briefing.md` is an internal evidence map
- `literature_review_synthesis.md` is the reader-facing review

Do not mix pipeline commentary into the narrative body. Put detailed counts in the compact Search and Screening section and full mechanics in logs/appendices.

## Claim and Writing Gates

- Cross-sectional evidence does not establish temporality or causality.
- For common outcomes, do not interpret an odds ratio as a prevalence/risk ratio.
- Use `definitive` only when the claim registry's prespecified evidence threshold is met.
- A narrative paragraph should normally state a collective judgment, cite one or two anchors, name the material limitation, and end with a bounded interpretation.
- Numeric results must be used selectively to establish magnitude, precision, inconsistency, or a decision boundary; do not produce a catalogue of estimates without synthesis.
- The final synthesis must distinguish convergence, counterevidence, design heterogeneity, residual uncertainty, and the exact implication for the proposed cross-sectional study.
- If no direct evidence exists for an outcome, state the gap briefly; do not inflate indirect evidence into a substitute.
- Use SANRA as a narrative-review quality aid, not as a systematic-review reporting guideline. Use PRISMA/PRISMA-S elements only for transparent search and screening reporting where applicable.
- Do not infer certainty from the number of statistically significant studies. Base certainty on design, bias, directness, consistency, precision, and reporting limitations.

## Resource Routing

Load only what the current stage needs:

- retrieval: `references/search_reporting_standard.md`, `references/live_retrieval_standard.md`, `references/eligibility_criteria.md`
- product route and release depth: `references/review_type_and_release_standard.md`
- appraisal: `references/scoring_rubric.md`, `references/study_quality_framework.md`
- contracts/handoff: `references/output_schema.md`, `references/proposal_bridge_standard.md`, `references/mode_policy.md`, `references/downgrade_policy.md`
- narrative: `references/narrative_review_standard.md`, `references/review_writing_blueprint.md`
- end-to-end overview: `references/review_workflow.md`

## Release Gate

Release only when required files exist, validators pass, citation and claim IDs resolve, screening numbers reconcile, no unsupported definitive language remains, and the delivery preset matches actual package completeness. Report blocked sources, unavailable full texts, and residual uncertainty explicitly.
