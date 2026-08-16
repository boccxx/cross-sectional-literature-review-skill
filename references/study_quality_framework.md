# Study Quality Framework

## Purpose

This file defines how to assign evidential weight after topical relevance is established.

The goal is not to force a formal bias tool on every paper. The goal is to stop weak
but on-topic studies from carrying the same weight as stronger or more transferable evidence.

Assign credibility using `scoring_rubric.md` Dimension 2.  Use the bias checklists
in this file to inform that assignment and to populate `bias_registry.csv`.

---

## Design-Aware Weighting

### Evidence syntheses and prior reviews

- Prefer recent systematic reviews or umbrella reviews over unsystematic narrative reviews
- Check whether the review reports databases, search dates, inclusion criteria, and appraisal logic
- If a review is methodologically thin, treat it as background rather than decisive evidence

### Cross-sectional primary studies

Evaluate:

- target population fit
- exposure and outcome measurement validity
- confounder handling quality
- whether the estimand and interpretation are appropriate for a common outcome
- whether claims overreach the design

Well-measured cross-sectional studies are often highly useful for measurement,
prevalence framing, and confounder planning, but they remain weak for temporality.

### Cohort or case-control studies

- Use them to strengthen temporality logic or triangulate associations
- Check follow-up adequacy, exposure timing, outcome ascertainment, and loss-to-follow-up risk
- When these studies disagree with cross-sectional findings, surface the disagreement
  rather than averaging it away

### Measurement-validation studies

- Prioritize papers that report reliability, validity, threshold choice, or population-specific adaptation
- These papers may be more useful for protocol inputs than a loosely related association paper

### Trials or interventions

- Use mainly for mechanism plausibility, behavioral modification logic, or outcome responsiveness
- Do not over-import intervention logic into a purely observational estimand without explanation

### Preprints

- Use preprints as frontier signals, early methods signals, or niche-population evidence
- Flag them clearly as preprints or not-yet-peer-reviewed sources
- Verify metadata carefully because preprint records drift more often
- Do not let a single preprint anchor the main conclusion unless corroborating evidence exists
- If a preprint fills a key gap, say that the gap is provisionally addressed rather than
  definitively closed

---

## Bias Checklists by Study Type

Use these checklists to screen each included study and to populate `bias_registry.csv`.

The required columns in `bias_registry.csv` are:
`paper_id, bias_domain, severity, bias_direction, evidence_of_bias, reviewer_note`

`severity` values: `high / moderate / low / none_detected / unclear`
`bias_direction`: `towards_null / away_from_null / uncertain / not_applicable`

### Pharmacoepidemiology and Treatment Strategy Studies

Required when `question_type = treatment_strategy_comparison`.
Recommended for `exposure_outcome_association` with a drug or healthcare exposure.

| Bias domain | What to check |
|---|---|
| confounding_by_indication | Was the indication for starting/stopping treatment controlled for? Do sicker patients preferentially receive (or discontinue) the drug? |
| prevalent_user_bias | Were incident (new) users identified, or were prevalent users included? Prevalent users have survived an early adverse period, which biases results. |
| immortal_time_bias | Is time zero clearly defined? Is there a period between cohort entry and exposure definition when outcomes could not occur? |
| protopathic_bias | Was the exposure started in response to early symptoms of the outcome? |
| depletion_of_susceptibles | Does long follow-up compare survivors of early adverse effects in one arm against a mixed population in the other? |
| reverse_causation | Could the outcome precede the exposure in time? Is temporality assured by design? |
| measurement_timing_mismatch | Was the exposure window aligned with the outcome risk window? |
| selection_bias | Was the cohort entry rule or follow-up rule applied symmetrically across exposure arms? |
| overadjustment | Were mediators or colliders included in the adjustment set without explicit justification? |
| competing_risk | For non-mortality outcomes, was death or treatment switch addressed as a competing event? |

### Prognosis Studies (Cohort, Time-to-Event)

Recommended when `question_type = prognosis`.

| Bias domain | What to check |
|---|---|
| baseline_imbalance | Were prognostic factors distributed similarly at baseline? Was adjustment adequate? |
| follow_up_completeness | Was loss to follow-up differential by exposure or outcome status? |
| competing_risk | Was competing risk (e.g., death from other causes) handled appropriately? |
| measurement_timing_mismatch | Were predictors measured before the outcome risk period? |
| reverse_causation | Could early-stage disease have influenced the predictor measurement? |

### Diagnostic and Measurement Studies

Recommended when `question_type = diagnostic_measurement`.

| Bias domain | What to check |
|---|---|
| reference_standard | Was the reference standard adequate and independently applied? |
| verification_bias | Did all participants receive the reference standard regardless of index test result? |
| measurement_timing | Was the index test applied close in time to the reference standard? |
| spectrum_effect | Was the study population representative of the target clinical population? |

### Cross-Sectional Association Studies

Minimum expected when `question_type = exposure_outcome_association` and design is cross-sectional.

| Bias domain | What to check |
|---|---|
| reverse_causation | Can the temporal direction of the exposure-outcome relationship be established from the design? |
| overadjustment | Were intermediary variables (on the causal pathway) included in the adjustment set? |
| common_cause_confounding | Were major shared causes of both exposure and outcome controlled for? |
| OR_as_RR | For common outcomes (> 10%), is the OR being interpreted as a prevalence ratio or risk ratio? |

---

## When `bias_registry.csv` Is Required vs Recommended

| question_type + review_goal | bias_registry.csv requirement |
|---|---|
| treatment_strategy_comparison (any goal) | **Required.** Populate the pharmacoepi checklist for every included study. |
| treatment_strategy_comparison + decision_support or protocol_support | **Required and must be complete.** Severity must be assigned for all domains. |
| prognosis + decision_support or protocol_support | **Required.** Populate the prognosis checklist. |
| prognosis + other goals | Recommended. |
| exposure_outcome_association (cross-sectional) | At minimum: reverse_causation, overadjustment, OR_as_RR. |
| background_landscape (any question_type) | Optional. |
| mechanism_mediation | Optional, focus on overadjustment and reverse_causation. |

---

## Practical Appraisal Labels

Use the four-level credibility label from `scoring_rubric.md` Dimension 2:

- `strong`
- `adequate`
- `limited`
- `weak`

Assign based on the paper's actual contribution to the downstream decision,
not only its prestige or journal name.

---

## High-Value Signals

- validated exposure or outcome tool
- explicit confounder rationale using causal reasoning (not automatic stepwise adjustment)
- transparent sample and setting description
- effect measure compatible with study design
- limits stated honestly
- findings triangulated by other studies
- new user / active comparator design for drug studies

## Downgrade Signals

- exposure or outcome poorly defined
- convenience sample with unclear generalizability
- automatic covariate adjustment without causal reasoning
- odds ratios interpreted as if they were risk or prevalence ratios when the outcome is common
- strong causal language from cross-sectional evidence
- missing time zero in longitudinal studies
- no mention of competing risk in time-to-event analyses

---

## How To Use This Framework

1. Score record relevance and advancement with `scoring_rubric.md` Dimension 1.
2. Read the full paper.
3. Assign credibility label using `scoring_rubric.md` Dimension 2.
4. Run the appropriate bias checklist from this file.
5. Assign `effect_trustworthiness` per estimate using `scoring_rubric.md` Dimension 3.
6. Populate `bias_registry.csv` when required or recommended.
7. Let the credibility label and bias findings constrain the `claim_strength`
   (Dimension 4) used in `claim_registry.csv`.
