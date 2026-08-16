# Review Writing Blueprint

This file defines the default writing architecture for `literature_review_synthesis.md`.

The target is not "a summary with citations." The target is a mature review article that:

- opens with a real clinical or scientific problem
- organizes evidence by question and outcome family
- separates direct evidence from indirect support
- states limitations where they matter
- ends with a bounded conclusion rather than a generic recap

## Core Position

Write the review as a sequence of judgments supported by a small number of key studies.
Do not write it as a sequence of papers.

Each major paragraph should answer:

1. What does this evidence layer suggest?
2. Which 1-2 studies most justify that statement?
3. What is the main reason to be cautious?
4. How far can this conclusion be taken?

If a paragraph does not do those four things, it usually degrades into either:

- annotated bibliography style
- background exposition with no decision value
- workflow chatter

## Preferred Section Order

Use this order unless the question type strongly requires another structure.

1. `Clinical Importance and Review Question`
2. `Direct Comparative Evidence`
3. `Broader Supporting Evidence`
4. `Outcome-Specific Interpretation`
5. `Methodological Limits`
6. `Clinical Interpretation and Research Gap`
7. `Search Basis`
8. `References`

### Section Purpose

`Clinical Importance and Review Question`
- why the topic matters now
- why the continue/stop or exposure/outcome decision is clinically real
- what exact question the review answers

`Direct Comparative Evidence`
- only exact-match or near-exact-match studies
- should carry the main direction-of-effect discussion

`Broader Supporting Evidence`
- disease-specific, subgroup-specific, mechanism, setting-specific, or policy-adjacent evidence
- useful for context and boundaries, not for replacing direct evidence

`Outcome-Specific Interpretation`
- one subsection per outcome family
- each subsection answers: directness, anchors, conclusion strength, main limitation

`Methodological Limits`
- only limitations that materially change interpretation strength

`Clinical Interpretation and Research Gap`
- what is most defensible now
- what should not be overgeneralized
- what study design or data are needed next

`Search Basis`
- one short late section
- numeric and factual
- never the organizing spine of the document

## Standard Intro Pattern

The opening should usually take 3 short paragraphs:

1. Disease burden / clinical prevalence / why the population matters
2. Why the decision is difficult now
3. The exact review question and target outcomes

Do not open with search mechanics, source lists, screening counts, or workflow history.

## Standard Paragraph Pattern

The default evidence paragraph is a four-move unit:

1. `Scope sentence`
   Example shape: "The most direct evidence comes from..."

2. `Anchor-study sentence(s)`
   Summarize 1-2 key studies and their most relevant result.

3. `Constraint sentence`
   State the most important limitation immediately, not three paragraphs later.

4. `Interpretive sentence`
   End by stating what the paragraph can support:
   - direct support
   - indirect support
   - context only
   - gap-defining evidence

This is the default building block for review body prose.

## Evidence-Layer Separation

The review should keep four layers distinct.

### Layer 1: Direct comparative evidence

Eligible for main direction-of-effect claims.

### Layer 2: Broader observational or setting-specific evidence

Useful when it sharpens plausibility, boundaries, or subgroup interpretation.
Must be labeled as indirect when it does not match the main question exactly.

### Layer 3: Patient-centered / symptom / preference evidence

Useful for explaining why discontinuation is considered and what trade-offs matter.
Must not substitute for hard-outcome comparison.

### Layer 4: Guidelines / policy / prior reviews

Useful for framing uncertainty, variation, and practice gaps.
Must not anchor empirical outcome claims.

## Outcome-Family Rule

Each outcome family subsection should answer the same three questions:

1. Is there direct evidence?
2. What are the strongest anchor studies?
3. What is the strongest safe conclusion?

Recommended default outcome families for treatment-strategy reviews:

- `All-Cause Mortality`
- `Cardiovascular Events / MACE`
- `Hospitalization`
- `Patient-Centered Outcomes`
- `Adverse Effects`

If an outcome family has no direct evidence, say so plainly and move it into a gap-oriented interpretation.

## Methodological Limits Rule

Only keep limitations that change how strongly the reader should believe the synthesis.

Preferred categories:

- confounding by prognosis / frailty / indication
- exposure or discontinuation misclassification
- heterogeneous clinical triggers or settings
- weak measurement of patient-centered outcomes

Avoid generic limitations like:

- "more studies are needed"
- "sample sizes varied"
- "there may be bias"

## Conclusion Rule

The conclusion should follow a fixed three-step close:

1. State the most stable main conclusion.
2. State what cannot be generalized.
3. State the most important next evidence need.

That pattern is more useful than a broad recap.

## Anti-Patterns

Treat these as draft failures:

- one-paper-one-sentence enumeration across a whole section
- section openings that begin with search counts
- using guideline language to support empirical effect claims
- long lists of all retained papers
- writing the review as if it were an evidence package explainer
- repeating the same "Study X found..." sentence frame

## Prompt vs Template

For writing-quality upgrades, template-first usually outperforms prompt-only tuning.

Reason:
- prompt changes affect tone and constraint
- template changes affect the shape of every section and paragraph

Best practice is layered:

1. strong structure template
2. explicit narrative rules
3. final prompt reminders in `review_briefing.md`

Do not rely on prompt wording alone to fix structural dryness.
