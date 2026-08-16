# Review Type and Release Standard

## Contents

1. Product-type lock
2. Main-body architecture
3. Search and screening truth
4. Appraisal and deep-reading standard
5. Mature-topic release gate
6. Sparse-evidence exception

## 1. Product-type lock

Set exactly one `review_type` in `review_contract.json` before searching.

| Review type | Required route | Synthesis boundary |
|---|---|---|
| `structured_narrative` | SANRA quality aid plus transparent reproducible search | Thematic critical synthesis; do not claim systematic completeness unless achieved |
| `systematic_no_meta` | PRISMA 2020, PRISMA-S, SWiM | Group by prespecified design/outcome/directness; no vote counting by significance |
| `systematic_meta` | PRISMA 2020 and PRISMA-S | Quantitative model, effect harmonization, heterogeneity, influence and small-study-bias plan |

Put the selected frameworks in `reporting_framework` and name the actual approach in `synthesis_method`.

## 2. Main-body architecture

A mature decision-grade body should normally allocate:

- 500–650 words: importance, prior-review overlap, and exact question
- 450–700: reproducible methods
- 450–650: evidence map and study characteristics
- 1,200–1,500: direct evidence, separated by design and outcome
- 600–800: exposure/outcome measurement
- 400–600: mechanisms and evidence boundaries
- 900–1,100: risk of bias, heterogeneity, counterevidence, reporting bias, and certainty
- 550–750: ranked gaps and study-design consequences
- 150–250: conclusion

Embed populated Study Characteristics and Effect Evidence Matrix tables. The prose must interpret rather than repeat the tables.

## 3. Search and screening truth

An executed row requires a literal source query, date, limits, hit count, retained/downloaded count, and execution status. Preserve query syntax exactly enough to rerun. Reconcile all flow counts to the raw, deduplicated, screening, and included artifacts. Give every full-text exclusion a single primary reason code plus a specific explanation. Run a reading-triggered second round for measurement, confounding, mechanism, contradiction, or terminology.

Refresh the final search when older than six months. If refresh is impossible, set `older_search_cutoff_disclosed=true` and explain the resulting currency limitation in the body.

## 4. Appraisal and deep-reading standard

Mark deep reading only after the full text or an adequate authoritative report has been examined for population, design, measurement, analysis, estimates, and limitations. Record the date and source.

Appraise at least four study-specific domains for each included claim-bearing study. Select domains by design:

- cross-sectional: selection, exposure measurement, outcome measurement, confounding/overadjustment, reverse causation, estimand/reporting
- prospective: selection/attrition, baseline/time zero, changing exposure, outcome measurement, confounding, estimand/reporting
- evidence synthesis: search/screening, study-level bias assessment, synthesis method, heterogeneity, publication/reporting bias

Write a concrete `raw_signal` and `evidence_source` for each judgment. Repeated generic text is not appraisal.

Extract effects for at least 80% of direct/counterevidence studies. Use `NR` only after checking the full text; never turn missing estimates into null effects.

## 5. Mature-topic release gate

For `decision_grade` and `full_package`, require:

- at least 4,500 main-body words; target 5,500–6,500
- at least 30 identity-resolved references; target 45–70
- at least 12 documented deep-read studies; target 12–20
- nonempty study-specific appraisal
- exact search strings and reconciled screening counts
- populated main-body evidence tables
- counterevidence, heterogeneity, and outcome-specific certainty

The floors prevent a structured outline from being mislabeled as a complete review. They do not license repetition, citation dumping, or invented facts.

## 6. Sparse-evidence exception

Use only when the evidence base is genuinely sparse after reproducible saturation. Add:

```json
"sparse_evidence_exception": {
  "applies": true,
  "rationale": "Why fewer studies exist and why the smaller corpus is still informative",
  "search_saturation": "What sources, rounds, citation chains, and stopping evidence establish saturation",
  "scope_boundary": "The narrow population, exposure, outcome, design, language, or period boundary"
}
```

Release as a scoped evidence-gap review, not as a falsely comprehensive mature-topic review. The exception does not waive citation identity, appraisal, search truth, screening reconciliation, or anti-padding checks.
