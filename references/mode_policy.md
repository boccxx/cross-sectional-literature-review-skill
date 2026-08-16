# Mode Policy

Project mode answers:

- how real the downstream study is
- how strong the downstream manuscript claim may be

Delivery preset answers a different question:

- how complete the review package needs to be

Do not confuse `project_mode` with delivery scope.

## `research`

Use when the review is supporting a real study and real manuscript.

## `applied_methods`

Use when the evidence base is real, but the downstream project is synthetic, pilot, or validation-oriented.

## `workflow_methods`

Use when the task is only a skill demonstration or pipeline validation.

## Delivery Presets

### `brief`

Use when:

- the user needs a fast but structured evidence map
- the corpus is still unstable
- the review should not yet pretend to be a mature narrative review

Typical outputs:

- search tables
- screening tables
- core registries
- `review_briefing.md`

### `decision_grade`

Use when:

- the review is intended to shape a real study, protocol, SAP, or manuscript framing
- claim discipline and registry completeness matter
- a true narrative review is expected if the evidence qualifies

Typical outputs:

- full registries
- `claim_registry.csv`
- `effect_registry.csv` where required
- `bias_registry.csv` where required
- `proposal_bridge.md`
- `protocol_inputs.json`
- `literature_review_synthesis.md`

### `full_package`

Use when:

- the review is near delivery, circulation, or submission
- formatted exports and citation verification are needed

Adds:

- DOCX/PDF export
- citation verification outputs
- stricter handoff expectations

## Sufficiency Gates

- `strong` or `adequate`: protocol-ready
- `limited`: draft-only
- `weak`: do not force a research manuscript

## Downgrade Triggers

- sparse evidence density
- poor design fit for the intended claim
- high causal-temporality risk
- weak estimand feasibility
- high interpretation risk
- mismatch between requested delivery preset and actual narrative readiness
