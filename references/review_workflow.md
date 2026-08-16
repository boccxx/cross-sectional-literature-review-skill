# Review Workflow

## Purpose

This workflow exists to produce a literature review package that can survive reuse by protocol, analysis, and manuscript skills.

## Core Sequence

1. Lock the topic frame.
   Capture project mode, population, setting, exposure, outcome, and optional mediator or modifier.

2. Plan the search.
   Build direct-topic, population-specific, measurement-oriented, and design-aware queries.
   Log dates, sources, and constraints using `search_reporting_standard.md`.

3. Run the first retrieval round across the core sources.
   Query OpenAlex, PubMed/MEDLINE, Embase, Web of Science, medRxiv, and bioRxiv unless a source is explicitly unavailable and logged.

4. Execute and capture the live retrieval.
   Use `run_live_search.py` or an equivalent source-specific workflow that produces raw payload captures and candidate-record tables.

5. Deduplicate and read anchor papers.
   Read enough of the strongest retained papers to understand terminology drift, named instruments, key mechanisms, contradictory findings, and design limits.

6. Expand the search based on reading.
   Add follow-up rounds for mechanism papers, measurement validation, subgroups, null findings, landmark reviews, and citation chaining.
   Log what triggered each new query family.

7. Screen and role-label.
   For each retained paper, record why it matters:
   - association evidence
   - measurement support
   - confounder logic
   - mechanism support
   - estimand or methods support
   - contradiction or scope-boundary evidence

8. Score and appraise.
   Use `scoring_rubric.md` for transfer value and `study_quality_framework.md` for evidential weight.

9. Build registries.
   Populate:
   - `study_registry.csv`
   - `measurement_registry.csv`
   - `confounder_registry.csv`
   - `citation_registry.json`

10. Translate evidence into decisions.
   Produce:
   - `evidence_to_decision_table.csv`
   - `evidence_sufficiency_report.json`
   - `review_contract.json`

11. Extract protocol-ready inputs.
   Produce:
   - `proposal_bridge.md`
   - `protocol_inputs.json`
   - `related_work.md`
   - `research_gaps.md`

12. Generate the narrative review.
   Treat `review_briefing.md` and the registries as the evidence-map layer, and
   `literature_review_synthesis.md` as the reader-facing review routed by `review_type`:
   SANRA-aided narrative, PRISMA/SWiM systematic synthesis without meta-analysis,
   or PRISMA quantitative synthesis.
   The review must read like a real academic document, include inline screening counts,
   and avoid package- or workflow-explanation language in the body.

13. Validate.
    Run `scripts/validate_review_package.py`.
    When the narrative exists, also run the external literature review standard validator.

## Practical Rule

If evidence is weak, narrow, or badly aligned, downgrade the downstream claim rather than compensating with stronger prose.

## Reader-Facing Rule

The main review should answer "what does the literature show?" not "what did the package do?"

- `review_briefing.md` may discuss tiers, anchors, registries, and package logic.
- `literature_review_synthesis.md` should discuss direct evidence, indirect support,
  outcome-specific interpretation, and literature limitations.
- Search mechanics belong in one compact late section, not threaded through the main body.

## Front-Shifted Use

If the user is still in the opening-report or topic-refinement stage, do not wait for a full protocol to make the review useful.

Use the review package to lock:

- significance
- gap
- innovation
- feasibility
- population-exposure-outcome framing
- estimand and interpretation boundary

## Loop Rule

Do not treat retrieval as a one-pass prelude. The default loop is:

1. search
2. deduplicate
3. read
4. discover missing concepts or unresolved tensions
5. search again with sharper queries
6. stop only when the new round is no longer changing the review's downstream decisions
