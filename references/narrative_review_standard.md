# Narrative Review Standard

This file defines the target style for `literature_review_synthesis.md`.

The intended target is a **SANRA-style medical narrative review**, not an evidence-map memo
and not a workflow explanation. `review_briefing.md` carries pipeline-facing material.
`literature_review_synthesis.md` carries reader-facing synthesis.

## Product Split

- `review_briefing.md`
  - evidence map / registry summary / audit trail
  - may mention tiers, anchors, claim registries, and package logic
- `literature_review_synthesis.md`
  - reader-facing narrative review
  - must foreground the literature, not the tool

## Hard Narrative Rules

1. Do not explain the system inside the review body.
   Prohibited examples:
   - "the workflow therefore..."
   - "this upgrade..."
   - "the system is designed..."
   - "v2.1..."
   - "anchor eligibility..."
   - "narrative readiness..."

2. Organize by the scientific question, not by the package.
   The reader should encounter:
   - why the question matters
   - what direct evidence exists
   - what indirect evidence adds
   - which outcomes can and cannot be interpreted
   - what the main literature limitations are
   - what gaps remain

3. Keep the main evidence layer clean.
   The main narrative should only retain:
   - direct strategy-comparison evidence
   - truly informative indirect support
   - a small amount of necessary guideline or policy background

4. Outcome sections should follow the same internal logic.
   Each outcome family should answer:
   - is there direct evidence?
   - what are the strongest anchor studies?
   - how strong is the conclusion?
   - what is the main limitation?

5. Use a few anchor studies, not long citation piles.
   A typical outcome section should rely on 2-4 key studies, not every retained record.

6. Methodological limits must be written as literature limits, not tool rules.
   Preferred:
   - "Discontinuation is often triggered by clinical deterioration, raising concern about confounding by prognosis."
   Avoid:
   - "The workflow therefore separates core_direct_strict from core_direct_broad."

7. Keep Search and Screening brief and late.
   One compact section is enough in the main review. Detailed execution belongs in
   `search_log.csv`, `search_strategy.md`, and `review_briefing.md`.

8. Conclusions should state what the literature supports, not what the package allows.

## Practical Structure

Recommended section order:

1. Clinical importance and review question
2. Direct comparative evidence
3. Broader supporting evidence
4. Outcome-specific interpretation
5. Methodological limits
6. Clinical interpretation and research gap
7. Search basis
8. References

Read `references/review_writing_blueprint.md` and follow it unless the user explicitly
asks for a different review form.

## Paragraph-Level Rule

Each substantive evidence paragraph should usually follow this pattern:

1. scope judgment
2. 1-2 anchor studies
3. immediate limitation
4. bounded interpretation

This is the default antidote to paper-by-paper listing.

## Direct / Indirect / Guideline Separation

Use separate prose roles for each evidence layer:

- `direct comparative evidence`
  - supports the main direction-of-effect discussion
- `broader supporting evidence`
  - adds context, subgroup boundaries, or clinical plausibility
- `patient-centered evidence`
  - explains why discontinuation is considered and what trade-offs matter
- `guideline or policy evidence`
  - frames uncertainty and implementation gaps

Guidelines and prior reviews may inform the narrative but must not substitute for direct
comparative evidence.

## Introduction Rule

The opening should usually take three short paragraphs:

1. why the condition or treatment issue matters
2. why the decision is clinically difficult now
3. the exact review question and key outcomes

Do not open with search workflow, source lists, or screening counts.

## Conclusion Rule

The conclusion should always do three things:

1. state the most stable conclusion
2. state what cannot yet be generalized
3. state the most important next evidence need

Avoid conclusions that merely recap section order or restate package completeness.

## Internal Scoring Rubric

Use this to judge whether the draft reads like a mature narrative review:

- `narrative_form` (0-5)
  - does it read like a review article rather than an evidence brief?
- `core_evidence_purity` (0-5)
  - is the main evidence layer free of obviously irrelevant or low-directness studies?
- `synthesis_depth` (0-5)
  - does it synthesise across studies rather than list them?
- `claim_discipline` (0-5)
  - are claims appropriately constrained by the evidence?
- `readability` (0-5)
  - does the reader learn the field, rather than the pipeline?

Anything below roughly 18/25 should be treated as a drafting problem even if the package is structurally valid.
