# Output Schema

## search_log.csv

Suggested columns:

- search_id
- search_round
- parent_search_id
- concept_focus
- query_family
- question_type (propagated from topic_config; identifies routing used)
- review_goal (propagated from topic_config; identifies depth and output requirements)
- query
- source
- source_query
- date_searched
- date_limit
- language_limit
- recommended_retrieval_target
- n_retrieved
- n_after_dedup
- scope
- status
- rationale_trigger
- note

## screening_decisions.csv

Suggested columns:

- paper_id
- title
- decision
- screening_stage
- role
- reason
- direct_question_match
- design_integrity_ok
- comparator_integrity_ok
- time_zero_clear
- prior_user_design
- directness_tier
- exclusion_reason_code
- question_match_summary
- include_in_synthesis
- include_in_protocol

## candidate_records_raw.csv

Suggested columns:

- search_id
- search_round
- query_family
- source
- source_rank
- title
- authors
- year
- published_date
- doi
- url
- abstract
- publication_status
- source_record_id
- matched_query
- local_relevance_score
- strategy_match_score (0–3; 0 = not a strategy query or no match; 3 = both-side + design vocabulary)

## candidate_records_dedup.csv

Suggested columns:

- same as `candidate_records_raw.csv`, after DOI/title deduplication

## study_registry.csv

Suggested columns:

- paper_id
- synthesis_tier
- anchor_eligible
- primary_role
- secondary_role
- publication_status
- year
- design
- population
- exposure
- outcome
- sample_size
- setting
- measures
- core_findings
- limitations
- protocol_implication
- suggested_methods
- record_relevance (0–5; from scoring_rubric.md Dimension 1)
- study_credibility (strong / adequate / limited / weak; from Dimension 2)
- quality_signal (free-text summary of key quality signals)
- direct_question_match (`yes` / `no` / `unclear`; from eligibility_criteria.md)
- design_integrity_ok (`yes` / `no` / `unclear`)
- comparator_integrity_ok (`yes` / `no` / `unclear`)
- time_zero_clear (`yes` / `no` / `unclear`)
- prior_user_design (`yes` / `no` / `unclear`)
- outcome_family
- outcome_family_all
- title
- doi
- authors

## measurement_registry.csv

Suggested columns:

- construct
- preferred_tool
- evidence_role
- reason_from_literature
- key_example_paper_ids
- supporting_evidence_row_ids
- protocol_use
- limitation_or_bias

## confounder_registry.csv

Suggested columns:

- variable
- classification
- support_level
- supporting_paper_ids
- supporting_evidence_row_ids
- rationale
- recommended_main_model_role

## citation_registry.json

Suggested fields per entry:

- citation_id
- reference_number
- paper_id
- title
- publication_status
- narrative_role
- claim_supported
- supporting_decision_ids
- supporting_evidence_row_ids

## quality_appraisal_registry.csv

Suggested columns:

- paper_id
- domain
- judgment
- raw_signal
- evidence_source
- note

## fulltext_inventory.csv

Suggested columns:

- paper_id
- title
- doi
- text_source
- fulltext_status
- open_access_url
- source_file
- deep_read_completed
- deep_read_date
- claim_bearing
- note

## evidence_to_decision_table.csv

Suggested columns:

- decision_id
- decision
- evidence_summary
- supporting_paper_ids
- supporting_evidence_row_ids
- downstream_use
- confidence

## evidence_sufficiency_report.json

Suggested fields:

- level
- notes
- evidence_density
- design_mix
- measurement_support
- confounder_support
- gap_confidence
- design_fit
- causal_temporality_risk
- estimand_feasibility
- interpretation_risk
- mode_recommendation
- downgrade_reason

## review_contract.json

Suggested fields:

- project_mode
- review_type (`structured_narrative`, `systematic_no_meta`, or `systematic_meta`)
- reporting_framework (for example `SANRA`, or `PRISMA 2020` + `PRISMA-S` + `SWiM`)
- synthesis_method
- question_type
- review_goal
- design_type
- topic
- primary_estimand
- evidence_sufficiency
- decision_ids
- citation_ids
- deliverable_style
- narrative_readiness
- anchor_density_by_outcome

## literature_review_synthesis.md

Default presentation expectations:

- no generator branding or author placeholders in the title block
- review title and opening page should read like a real evidence review
- project-mode disclosure belongs in scope or methods text, not decorative metadata
- use restrained academic formatting suitable for DOCX/PDF export
- target style follows `review_type`: SANRA-aided narrative, PRISMA/SWiM systematic synthesis without meta-analysis, or PRISMA quantitative synthesis
- mature `decision_grade`/`full_package` bodies require at least 4,500 words, 30 identity-resolved references, 12 documented deep reads, and populated study-characteristics/effect tables unless a valid sparse-evidence exception is recorded
- do not mention package internals such as `review_briefing.md`, `study_registry.csv`,
  `claim_registry.csv`, `effect_registry.csv`, `anchor_eligible`, `narrative_readiness`,
  `core_direct_strict`, `core_direct_broad`, or version labels such as `v2.1`
- search and screening should appear as one compact late section, not as the organizing frame
- main sections should foreground the scientific question, direct evidence,
  indirect support, outcome-specific interpretation, literature limitations, and gaps
- multilingual variants should be separate files rather than mixed-language prose
- heavy-delivery mode may additionally emit `literature_review_zh.md`, `references.bib`,
  `reference_list_vancouver.md`, `reference_list_apa.md`, `publication_manifest.json`,
  and `delivery_quality_report.json`

## review_briefing.md

Default presentation expectations:

- pipeline-facing evidence map and audit document
- may mention tiers, anchors, registries, claims, bias tables, and package logic
- not intended to read like journal prose
- should give the LLM enough structure to write the narrative without copying the briefing wording

## literature_review.tex / .docx / .pdf

Default expectations:

- `.tex` is an export artifact for editing, submission preparation, or downstream formatting
- `.docx` and `.pdf` are delivery artifacts, not the source of truth
- multilingual exports should use language-tagged stems or filenames when more than one language is produced

## protocol_inputs.json

Suggested fields:

- project_mode
- study_title_candidate
- population
- exposure
- outcome
- mediator
- moderator
- primary_estimand
- measurement_tools
- confounders
- effect_modifiers
- suggested_methods
- evidence_gaps

## proposal_bridge.md

Default expectations:

- states significance, gap, innovation, and feasibility in evidence-backed language
- locks the proposed population, exposure, comparison, outcome, and primary estimand
- translates review findings into opening-report-ready claims without overstating causality

## effect_registry.csv

Required when `question_type` is `treatment_strategy_comparison`, `exposure_outcome_association`,
or `prognosis`.  Recommended otherwise.

One row per effect estimate.  A single paper may contribute multiple rows
(e.g., main analysis, subgroup, sensitivity analysis).

Suggested columns:

- effect_id (stable row identifier used by claim_registry.csv)
- study_id (links to paper_id in study_registry.csv)
- paper_id
- outcome_family
- outcome
- effect_measure (OR / RR / HR / PR / RD / MD / other)
- point_estimate
- ci_lower
- ci_upper
- exposure_contrast
- effect_directness
- supports_primary_direction_claim
- population_subgroup
- effect_trustworthiness
- notes

## claim_registry.csv

Required for all completed reviews.  One row per claim that appears in the narrative.

This is the **unified schema** — the two earlier definitions (pre-2026) are merged here.
Key addition: `evidence_direction` separates the factual direction from the prose text,
preventing the narrative generator from hard-wiring a claim direction.

Columns (canonical, must match build_review_scaffold.py and validate_review_package.py):

- `claim_id` (e.g., "C01", "C02")
- `outcome_family` (links to effect_registry.csv outcome_family)
- `claim_text` (the exact claim as it appears or will appear in the narrative)
- `claim_type` (primary_association / mechanism / measurement / design_justification / gap_statement / feasibility)
- `allowed_strength` (**definitive / suggestive / preliminary / background_only** — see scoring_rubric.md)
- `evidence_direction` (**favorable / harmful / null / mixed / heterogeneous / insufficient / unclear**)
  — must be set BEFORE claim_text is written; prevents the generator from defaulting to a harm narrative
- `anchor_required` (yes / no)
- `supports_primary_direction_claim` (yes / no)
- `eligible_anchor_paper_ids` (comma-separated paper_ids from study_registry.csv)
- `supporting_paper_ids` (additional supporting paper_ids)
- `counter_study_ids` (paper_ids of studies that contradict or qualify this claim)
- `supporting_evidence_row_ids` (comma-separated row identifiers from effect_registry.csv, required for primary claims)
- `confidence` (free-text assessment of why this strength was assigned)
- `narrative_position` (introduction / main_synthesis / discussion / gap_section)
- `note`

**Enforcement rules:**
- `allowed_strength` must be one of: `definitive`, `suggestive`, `preliminary`, `background_only`
- `evidence_direction` must be set before narrative drafting
- Every primary claim (`supports_primary_direction_claim = yes`) must have at least one `supporting_evidence_row_ids` entry
- Primary claims must not use `appendix_only` studies as eligible anchors

## bias_registry.csv

See `study_quality_framework.md` for when this file is required vs recommended.

One row per bias domain assessed per study.

Columns (canonical, must match build_review_scaffold.py):

- `paper_id`
- `bias_domain` (e.g., confounding_by_indication, immortal_time_bias, time_zero_alignment, prevalent_user_bias,
  selection_bias, outcome_misclassification, exposure_misclassification, overadjustment, reverse_causation)
- `severity` (high / moderate / low / none_detected / unclear)
- `bias_direction` (towards_null / away_from_null / uncertain / not_applicable)
  — renamed from `direction` for unambiguous field identification
- `evidence_of_bias` (free-text: specific evidence or reasoning for this judgment)
  — was missing in older schema; required for non-unclear severity
- `reviewer_note` (optional additional annotation)

## methods_snapshot.json

Internal intermediate file. Populated before narrative writing. Consumed by
`build_review_narrative.py` and the narrative LLM.

Fields:

- `review_question`
- `databases_searched` (list)
- `search_dates` (object: {source: date_searched})
- `date_limits`
- `language_limits`
- `inclusion_criteria` (list)
- `exclusion_criteria` (list)
- `screening_process`
- `fulltext_availability_limitations`
- `quality_appraisal_framework`
- `prisma_counts` (object: identified_total, after_dedup, screened, fulltext_assessed, included, excluded_reasons)
- `access_limitations` (list)

## section_packets.json

Internal intermediate file. One entry per narrative section.
Consumed by the LLM when drafting each section independently.

Fields per entry:

- `section_id`
- `section_name`
- `section_goal`
- `allowed_strength_ceiling` (definitive / suggestive / preliminary / background_only)
- `anchor_paper_ids` (list)
- `supporting_cluster_ids` (list)
- `forbidden_paper_ids` (list — studies that should not be cited as primary support in this section)
- `must_mention_limitations` (list)
- `expected_outcome_families` (list)
- `anti_repetition_blacklist` (list — sentence openers or phrases to avoid)

## Search Strategy Expectations

`search_strategy.md` should document:

- All core sources searched:
  - Free: OpenAlex, PubMed/MEDLINE, Semantic Scholar, Europe PMC, medRxiv, bioRxiv
  - Subscription (log as blocked_auth_required if absent): Embase, Web of Science
- Round structure: broad mapping, reading-driven expansion, citation chaining
- `score_candidates.py` run and scored_candidates.csv produced
- `chase_citations.py` run on high-scoring anchors (record_relevance ≥ 4)
- Practical default volume targets for each round
- Why later query families were added after reading
- Any source access limitations or deviations from the default stack
