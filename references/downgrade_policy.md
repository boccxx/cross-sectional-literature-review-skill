# Downgrade Policy

Use downgrade states when the evidence or design fit is insufficient for a stronger downstream mode.

Downgrade decisions operate on two axes:

- **research ambition**
  - what kind of downstream claim or study is allowed
- **delivery form**
  - whether the package can honestly support `brief`, `decision_grade`, or `full_package`

## Allowed States

- `preliminary_review`
  Search and screening exist, but synthesis is too early for protocol generation.
- `narrow_evidence_review`
  The topic is coherent, but the evidence base is too narrow for a broad review claim.
- `protocol_draft_only`
  There is enough support for a draft protocol, but not enough to justify a final protocol or manuscript.
- `sap_not_ready`
  Protocol logic is usable, but the estimand or analytic support is still under-specified.
- `analysis_core_only`
  Core analysis may proceed, but extended methods should remain off.
- `applied_methods_manuscript_only`
  The workflow can support an applied-methods manuscript, but not a real empirical manuscript.
- `workflow_methods_manuscript_only`
  Outputs may support a workflow/methods paper only.
- `research_manuscript_blocked`
  A research-grade manuscript is not allowed because the evidence or design does not support it.

## Default Triggers

- Use `preliminary_review` when the review package lacks a stable study registry or sufficiency assessment.
- Use `narrow_evidence_review` when the corpus is coherent but highly sparse or restricted to a narrow slice of the topic.
- Use `protocol_draft_only` when measurement support or confounder support is limited.
- Use `sap_not_ready` when the main estimand or interpretation boundary is unclear.
- Use `analysis_core_only` when the evidence or design supports the main analysis but not exploratory extensions.
- Use `applied_methods_manuscript_only` when the research question is real but the data are synthetic, pilot, or internal-validation only.
- Use `workflow_methods_manuscript_only` when the topic serves pipeline validation rather than a substantive study.
- Use `research_manuscript_blocked` when evidence is weak, design fit is low, or temporality/interpretation risks make a research-grade paper inappropriate.

## Delivery-Form Downgrade Rule

Even when the project mode stays the same, the package may need to downgrade its delivery form.

- If search and screening are incomplete:
  - downgrade to `brief`
- If registries are complete but direct evidence is sparse or poorly aligned:
  - keep `decision_grade` package outputs
  - but set `deliverable_style = evidence_map`
- If claim discipline, anchor support, and narrative readiness are satisfied:
  - allow `deliverable_style = narrative_review`
- If exports or citation verification are missing:
  - do not pretend the package is `full_package`
