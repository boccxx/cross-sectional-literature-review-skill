# Study Literature Review

Decision-grade literature review skill for study design, protocol framing, manuscript positioning, and opening-report work.

This skill is optimized for **research design questions**, especially when the review must do more than summarize papers.

It is designed to answer:

- what the field already knows
- what can be claimed safely
- what cannot yet be claimed
- which measurements and covariates are defensible
- what study design the evidence can actually support

## What Makes It Different

Compared with generic literature-review skills, this skill is strongest when the user needs:

- iterative multi-database retrieval
- design-aware screening
- direct vs indirect evidence separation
- claim discipline and downgrade logic
- protocol-ready registries, not just prose
- a real narrative review plus a separate evidence-map briefing

## Product Split

This skill produces two different products on purpose:

- `review_briefing.md`
  - pipeline-facing evidence map
  - registry summary
  - audit and writing input
- `literature_review_synthesis.md`
  - reader-facing narrative review
  - must follow the locked `review_type`: SANRA-aided structured narrative, PRISMA/SWiM systematic review without meta-analysis, or PRISMA quantitative synthesis
  - should not explain the workflow or the package

## Best-Fit Question Types

- `treatment_strategy_comparison`
- `prognosis`
- `exposure_outcome_association`
- `diagnostic_measurement`
- `guideline_to_evidence`
- `methods_estimand`

The current strongest path is clinical and observational research, especially pharmacoepidemiology and treatment-strategy questions.

## Delivery Presets

Use one of these practical output levels:

- `brief`
  - search + screening + key registries + `review_briefing.md`
  - use when evidence is still immature
- `decision_grade`
  - full registries + claim/effect logic + proposal/protocol outputs + narrative review
  - default target for real study preparation
- `full_package`
  - decision-grade package plus exports such as DOCX/PDF and citation verification
  - use when the review is close to delivery or submission

## Multilingual And Heavy Outputs

This skill now supports a practical heavy-delivery path without turning the whole workflow
into a rigid LaTeX production line.

Recommended pattern:

- write the primary review in the main working language
- build translated review variants from the same structured evidence package rather than manually duplicating prose
- optionally prepare translated review variants such as:
  - `literature_review_zh.md`
  - `literature_review_en.md`
  - `literature_review_ja.md`
- export each final markdown file to:
  - `.tex`
  - `.docx`
  - `.pdf`

Use [`scripts/export_review.py`](scripts/export_review.py) with:

- `--lang zh-CN|en|ja|de|fr|es`
- `--mainfont ...` when a specific PDF font is needed
- `--stem ...` for language-specific output names

For a heavier publication chain, add:

- [`scripts/run_fulltext_extraction.py`](scripts/run_fulltext_extraction.py)
  - prepares one auditable manual extraction packet per included paper
  - validates completed effect and bias rows before finalization
  - writes `effect_registry.csv`, `bias_registry.csv`, and `fulltext_inventory.csv`
- [`scripts/build_publication_package.py`](scripts/build_publication_package.py)
  - packages already completed narrative files without generating scientific prose
  - centralizes references into `references.bib`
  - emits delivery metrics, a publication manifest, and optional exports

## Core Outputs

- `search_log.csv`
- `candidate_records_raw.csv`
- `candidate_records_dedup.csv`
- `screening_decisions.csv`
- `study_registry.csv`
- `measurement_registry.csv`
- `confounder_registry.csv`
- `citation_registry.json`
- `evidence_to_decision_table.csv`
- `evidence_sufficiency_report.json`
- `review_contract.json`
- `review_briefing.md`
- `proposal_bridge.md`
- `protocol_inputs.json`
- `research_gaps.md`
- `related_work.md`
- `literature_review_synthesis.md`

Question-type-dependent outputs:

- `effect_registry.csv`
- `claim_registry.csv`
- `bias_registry.csv`

Optional delivery outputs:

- `fulltext_inventory.csv`
- `quality_appraisal_registry.csv`
- `references.bib`
- `reference_list_vancouver.md`
- `reference_list_apa.md`
- `publication_manifest.json`
- `delivery_quality_report.json`
- `literature_review.tex`
- `literature_review.docx`
- `literature_review.pdf`
- `citation_verification_report.csv`

## Quick Start

1. Prepare `study_manifest.json` or `topic_config.json`
2. Run `scripts/build_search_plan.py`
3. Run `scripts/run_live_search.py`
4. Screen and populate registries
5. Run `scripts/build_review_narrative.py`
6. Run `scripts/run_fulltext_extraction.py` when effect rows / quality appraisal / cleaner tiering are needed
7. Write any translated narrative variants from the same verified registries, then run `scripts/build_publication_package.py` for BibTeX, packaging, and exports
8. Run `scripts/validate_review_package.py`

## Operational Notes

- Keep `topic_config.json` topic fields concise. If the real question contains a long comma-separated outcome list or a long population sentence, put the short queryable phrases in `harvest.outcomes`, `harvest.exposures`, and `harvest.population`. The planner now decomposes long prose automatically, but explicit short harvest terms are still better.
- `run_live_search.py` now writes `live_search_diagnostics.json`. Use it when retrieval fails to distinguish DNS/network failures from SSL, rate-limit, and access-control problems.
- If the environment cannot reach academic sources, do not pretend retrieval happened. Record the failure, seed a small manually verified corpus, and state clearly that the package is a downgraded first pass rather than a full live-retrieval run.

## Narrative Standard

The target is not “any review-like output.”

The target for `literature_review_synthesis.md` is:

- the locked review product: **SANRA-aided structured narrative**, **PRISMA/SWiM systematic synthesis without meta-analysis**, or **PRISMA quantitative synthesis**
- organized by scientific question and outcome family
- centered on direct evidence, indirect support, and literature limitations
- free of workflow/package meta language

See:

- [`SKILL.md`](SKILL.md)
- [`references/narrative_review_standard.md`](references/narrative_review_standard.md)
- [`references/review_writing_blueprint.md`](references/review_writing_blueprint.md)
- [`references/review_workflow.md`](references/review_workflow.md)

## Current Strengths

- stronger design awareness than generic review skills
- stronger claim discipline than template-only review skills
- explicit downgrade logic when evidence is weak
- better fit for protocol and SAP preparation

## Current Boundaries

- the heavy pipeline is now much stronger, but still relies on open-access full text where available
- not the lightest choice for quick background summaries
- currently strongest in clinical and observational topics rather than fully domain-agnostic review work
