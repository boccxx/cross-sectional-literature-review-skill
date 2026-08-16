# Scoring Rubric

Use four independent evaluation dimensions rather than a single paper-level total.
A single score cannot distinguish a paper whose primary finding is trustworthy from
one whose main contribution is only background framing.

---

## Dimension 1: Record Relevance (0–5)

Used at the candidate screening stage to decide whether a record advances to full reading.

| Score | Meaning |
|---|---|
| 5 | Directly answers the question (population, exposure, comparator, outcome all match) |
| 4 | Strong match on 3 of 4 elements; minor population or outcome drift |
| 3 | Answers a closely related question; useful for measurement, mechanism, or confounder logic |
| 2 | Loosely related; may provide background context or methods signal only |
| 1 | Peripheral; keep only if it fills a specific documented gap |
| 0 | Not relevant; exclude |

**Threshold:** records scoring ≥ 3 advance to full reading. Records scoring ≥ 4 are
candidates for the main synthesis. Records scoring 1–2 may be retained as context or
measurement support but must be labelled as such.

---

## Dimension 2: Study Credibility (strong / adequate / limited / weak)

Applied after full reading. Reflects how much evidential weight the study can carry
for downstream design, analytic, or interpretive decisions.

| Label | Criteria |
|---|---|
| strong | Well-executed study design; explicit confounder rationale; transparent sample; outcome ascertainment validated; findings triangulated |
| adequate | Sound design; adequate confounder handling; some limitations acknowledged; interpretations appropriate for design |
| limited | Relevant findings but notable design weakness, convenience sample, or missing confounder detail; useful for context, not for anchoring decisions |
| weak | Severe design flaws, unexplained adjustment choices, or findings that overreach the design; use for background only or exclude |

---

## Dimension 3: Effect Trustworthiness (high / moderate / low / not_applicable)

Applied to each specific effect estimate cited from the paper.  A study can be
`adequate` overall while producing one trustworthy main-analysis estimate and one
low-trustworthiness subgroup estimate.

| Label | Criteria |
|---|---|
| high | Primary pre-specified analysis; adequate adjustment set; time zero clear; comparator interpretable; confidence interval reported; no major bias detected |
| moderate | Estimate is informative but one concern is present (e.g., residual confounding likely, or this is a secondary analysis, or preprint status) |
| low | Notable bias threat (immortal time, prevalent user bias, confounding by indication, etc.); or estimate is from a subgroup not pre-specified; or adjustment set is inadequate |
| not_applicable | The paper does not report a quantitative effect estimate (e.g., methods paper, narrative review, prevalence-only study) |

When `effect_registry.csv` is populated, assign `trust_level` using this dimension,
not the overall study credibility label.

---

## Dimension 4: Claim Strength (definitive / suggestive / preliminary / background_only)

Controls the language strength allowed in the narrative for any given assertion.
Assign this dimension when populating `claim_registry.csv`.

| Label | Allowed narrative language | Required evidence base |
|---|---|---|
| definitive | "evidence demonstrates", "studies show" | ≥ 2 studies with high effect trustworthiness AND strong/adequate credibility; findings triangulated |
| suggestive | "evidence suggests", "findings indicate" | ≥ 1 study with high/moderate trustworthiness; direction consistent across available studies |
| preliminary | "preliminary evidence suggests", "limited data indicate" | Only one study, or findings from low-trustworthiness estimates, or preprints only |
| background_only | "has been described", "context indicates" | Background or context papers; not direct evidence for the claim |

**Enforcement rule:** the narrative builder must not use language stronger than the
`allowed_strength` recorded in `claim_registry.csv` for each claim.

---

## Mandatory Red Flags (apply across all dimensions)

Do not allow a high relevance score to override these:

- No clear exposure or outcome definition → cap `record_relevance` at 2
- Severe overclaiming beyond what the design supports → cap `study_credibility` at `limited`
- OR interpreted as RR/PR when outcome is common (> 10%) → cap `effect_trustworthiness` at `low`
- Adjustment for likely mediator or collider without justification → cap `effect_trustworthiness` at `low`
- No interpretable sample or setting → cap `study_credibility` at `weak`

---

## Publication-Status Adjustment

- Peer-reviewed primary studies and systematic reviews may reach any label if quality warrants.
- Preprints may reach `record_relevance` 5 and `study_credibility` adequate, but
  `effect_trustworthiness` is capped at `moderate` unless the peer-reviewed version is confirmed.
- When a preprint is used, record `publication_status = preprint` in the study registry
  and do not let it anchor a `definitive` claim alone.

---

## Migration Note

The former 0–100 total score (anchor 85+, core 70–84, etc.) is retired.
Reviewers who have existing registries using the old scale can map:

| Old band | New equivalent |
|---|---|
| 85–100 (anchor) | record_relevance 5, credibility strong, effect high |
| 70–84 (core) | record_relevance 4–5, credibility adequate, effect moderate–high |
| 55–69 (targeted support) | record_relevance 3–4, credibility adequate–limited |
| 40–54 (peripheral) | record_relevance 1–2 |
| < 40 | exclude |
