# Eligibility Criteria

## Purpose

This file defines what it means for a study to genuinely answer the research question,
as opposed to merely being topically adjacent.  Use it at the screening stage to
populate the eligibility boolean columns in `study_registry.csv`.

A paper can score high on `record_relevance` (from `scoring_rubric.md`) while still
failing one or more eligibility criteria.  Those two judgements serve different purposes:
relevance decides whether to read the paper; eligibility decides whether its estimates
can be used to anchor claims about the specific question.

---

## Eligibility Boolean Columns for `study_registry.csv`

Add these five columns to every `study_registry.csv` row.
Use `yes`, `no`, or `unclear` at screening / abstract stage.
If a criterion is genuinely not applicable to the question type, record `NA`
only after structured extraction confirms that it does not apply.

| Column | Question answered |
|---|---|
| `direct_question_match` | Does this study directly answer the stated PECO/PICO question? |
| `design_integrity_ok` | Is the study design appropriate for the estimand and does it have a clear time zero? |
| `comparator_integrity_ok` | Is the comparator interpretable as the intended alternative strategy or treatment arm? |
| `time_zero_clear` | Is the start of follow-up clearly and symmetrically defined for all arms? |
| `prior_user_design` | For drug/treatment studies: were prevalent users excluded (new/incident user design)? |

Interpretation:

- `yes`: the criterion is clearly satisfied from the available evidence.
- `no`: the criterion clearly fails.
- `unclear`: title/abstract or incomplete extraction does not justify either `yes` or `no`.

If all five are `yes` for a given study, it is eligible to anchor main-synthesis claims.
Studies with one or more `unclear` values may still enter the narrative as direct-but-limited
or indirect support, depending on the synthesis tier.
Studies where one or more are `no` may still contribute context, measurement, or confounder
logic, but should not anchor the primary direction of evidence.

---

## Recommended Synthesis Tiers

Use the five eligibility columns together with `synthesis_tier` and `anchor_eligible`.

| Tier | Typical pattern | Narrative use |
|---|---|---|
| `core_direct_strict` | direct question match and comparator integrity are `yes`; design is robust; no major eligibility failure | Can anchor primary direction-of-effect claims |
| `core_direct_broad` | directly relevant strategy comparison, but one or more design fields remain `unclear` | Can appear in direct-evidence section but should not anchor strong claims alone |
| `indirect_support` | useful for measurement, patient perspective, context, confounding, or implementation | Can support interpretation or gap statements |
| `background_policy` | guideline, policy, narrative review, or broad deprescribing context | Background only |
| `appendix_only` | topically adjacent or too indirect to inform the stated question | Keep out of main evidence sections |

---

## Criterion 1: Direct Question Match

**Ask:** Does this study measure the exposure *and* the outcome *in the population* defined by the research question, using a comparator that is interpretable as the intended alternative?

**Pass:** The study population overlaps substantially with the target population; the exposure construct and outcome construct are operationalised in a compatible way; the comparison is not a proxy or a lookalike.

**Fail examples:**
- The study compares drug users vs never-users when the question is about continuing vs stopping among existing users.
- The outcome is a surrogate without established validity for the target outcome.
- The population is paediatric when the target population is adult.

---

## Criterion 2: Design Integrity

**Ask:** Is the study design capable of answering the question, and does the analytic approach match the estimand?

**Pass:** The design is cohort, RCT, case-control, or target trial emulation as appropriate; the time zero is clearly defined; follow-up is post-exposure.

**Fail examples:**
- Cross-sectional study used to answer a temporality-dependent prognosis question.
- No defined cohort entry date; outcomes measured before exposure assignment is complete.
- Prevalent users are analysed as a single group without distinguishing by treatment duration.

---

## Criterion 3: Comparator Integrity

**Primarily applies to `question_type = treatment_strategy_comparison`.**

**Ask:** Is the comparator the right alternative strategy, not just an absence of treatment or a different drug class?

**Pass criteria:**
- Both arms had prior use of the relevant drug class (active comparator / prior user design).
- The comparator is an active treatment decision, not "no exposure."
- The comparison is interpretable as a real-world strategy choice (continue vs discontinue; escalate vs maintain).

**Fail examples:**
- Metformin users vs metformin non-users (initiation study, not a continuation vs discontinuation study).
- Comparing drug A vs drug B when the question is about continuing vs stopping drug A.
- Patients who ran out of supply (unintentional discontinuation) treated as "discontinuers."

Set `comparator_integrity_ok = NA` for studies that are not strategy comparison studies.

---

## Criterion 4: Time Zero Is Clear

**Ask:** Is the start of follow-up defined consistently and symmetrically across all comparison arms?

**Pass:** Each arm has a clear, clinically meaningful index date; the risk period begins at the same relative point for all participants.

**Fail examples (immortal time risk):**
- Exposure is defined over a look-back window but the outcome clock starts at cohort entry.
- Users who initiated treatment *after* the index date are included in the "treated" arm from the index date onward.
- The grace period is not accounted for, leaving an interval where the exposure is undefined but outcomes are counted.

---

## Criterion 5: Prior User Design (Drug / Treatment Studies Only)

**Ask:** Were prevalent users excluded, or at least analysed separately, to avoid depletion-of-susceptibles bias?

**Pass:** The study uses an incident (new) user design in which follow-up begins at treatment initiation; or a prior user / active comparator design in which all arms have comparable prior treatment history.

**Fail:** Patients who have been on treatment for varying durations are pooled at a cross-sectional snapshot; early discontinuers due to adverse effects have already left the cohort, biasing the remaining "continuers" toward healthier survivors.

Set `prior_user_design = NA` for non-drug studies.

---

## Using These Criteria in Practice

1. For each paper that passes the relevance threshold (`record_relevance ≥ 3`), complete the five columns as part of the screening decision.

2. Record the reasoning briefly in `screening_decisions.csv` `reason` field when any criterion is `FALSE`.

3. In the narrative, distinguish clearly between:
   - **Eligible studies** (all five criteria met): can support direction-of-effect claims.
   - **Ineligible but useful studies** (one or more criteria failed): can support context, measurement, confounder, or mechanism claims only.

4. In `claim_registry.csv`, set `allowed_strength` to at most `suggestive` when no eligible study supports the claim, even if multiple ineligible-but-relevant studies point in the same direction.
