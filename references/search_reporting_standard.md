# Search Reporting Standard

## Purpose

This file adapts PRISMA 2020 and PRISMA-S into a compact operating standard for this skill.

The objective is reproducibility, not cosmetic formality. A reader should be able to tell what was searched, when it was searched, why papers were kept, and what limitations remain.

## Minimum Search Log Fields

Each row in `search_log.csv` should capture at least:

- `search_id`
- `search_round`
- `parent_search_id`
- `concept_focus`
- `query_family`
- `query`
- `source`
- `source_query`
- `date_searched`
- `date_limit`
- `language_limit`
- `recommended_retrieval_target`
- `n_retrieved`
- `n_after_dedup`
- `status`
- `rationale_trigger`
- `note`

If some fields are unavailable, keep the column and state why the value is missing.

## Minimum Screening Decision Fields

Each row in `screening_decisions.csv` should capture at least:

- `paper_id`
- `title`
- `decision`
- `screening_stage`
- `reason`
- `role`
- `include_in_synthesis`
- `include_in_protocol`

Reasons should be specific enough to audit later, for example:

- wrong population
- no validated outcome measure
- exposure too broad or poorly matched
- review article used only for citation chaining
- retained for measurement justification only

## Required Search Behaviors

1. Search both direct-topic and support-topic evidence.
   A defensible review usually needs association papers, measurement papers, and at least some mechanism or confounder logic papers.

2. Query the core sources directly unless a source is truly unavailable.
   The default core set is:
   - `OpenAlex`
   - `PubMed/MEDLINE`
   - `Embase`
   - `Web of Science`
   - `medRxiv`
   - `bioRxiv`

3. Record the actual search date.
   Do not leave it implicit.

4. Capture both recent and seminal work.
   Recent work is important for currency; seminal work is important when it anchors measurement tools, classification schemes, or field-defining associations.

5. Use iterative search rounds.
   Round 1 maps the field broadly. Then read the strongest anchors. Round 2 is driven by what the papers reveal about theory, mechanisms, measurements, confounding structure, effect modification, contradictory results, and design boundaries. Round 3 performs citation chaining, cited-by expansion, and focused retrieval for unresolved tensions.

6. Explain source limitations.
   If you only had access to abstracts, could not run one of the core databases, or had to rely on web search for part of the retrieval, state that plainly.

7. Preserve screening traceability.
   A retained paper should have a clear reason for staying in the synthesis.

8. Verify citation identity before final writing.
   Use DOI resolution, Crossref metadata, or equivalent authority checks so the citation registry does not drift away from the papers actually screened.

9. Log why later queries were created.
   A reading-driven expansion query should not appear magically. The trigger should be recoverable from anchor-paper reading, for example:
   - newly discovered measurement tool
   - named mechanism or theory
   - contradictory subgroup finding
   - null-finding thread
   - landmark review reference chasing

## Preferred Retrieval Stack

For a serious but still reproducible default stack:

- use OpenAlex as the baseline scholarly graph source
- use PubMed/MEDLINE for biomedical indexing and MeSH-linked retrieval
- use Embase to improve biomedical and pharmacological coverage
- use Web of Science for citation coverage and interdisciplinary recall
- use medRxiv and bioRxiv for preprint and frontier capture
- use Crossref or DOI resolution to clean metadata and resolve duplicates

This keeps the search process inspectable and easier to rerun.

## Practical Default Volumes

There is no universally correct fixed number of papers, but the default planning targets should be explicit:

- Round 1 broad mapping: inspect roughly `30-50` ranked records per core source; `40` is a good default target
- Anchor reading before expansion: read at least `12-20` high-value papers after deduplication
- Round 2 reading-driven expansion: inspect roughly `15-30` records per triggered query family and source
- Round 3 citation chaining and contradiction chasing: continue until an additional cycle yields no new decision-relevant evidence

These are planning defaults, not hard caps. If the topic is sparse, read fewer because fewer exist. If the topic is saturated, tighten by relevance and downstream decision value rather than pretending more volume is always better.

## Query Construction Logic

The query should evolve rather than remain a single frozen keyword string.

Use a layered query family:

1. Direct association query.
   Exposure + outcome + population/setting.

2. Population or setting query.
   Population/setting + exposure or outcome variants that may be indexed differently.

3. Measurement query.
   Exposure or outcome + named scales, instruments, thresholds, biomarkers, classification systems, or validation terms.

4. Design and estimand query.
   Exposure + outcome + design terms such as cohort, trial, case-control, prevalence, incidence, odds ratio, risk ratio, hazard ratio, marginal structural model, or mediation.

5. Mechanism or theory query.
   Triggered after reading when papers reveal pathway language, named theories, or biological or behavioral mediators.

6. Contradiction or boundary query.
   Triggered when the first round reveals null findings, subgroup differences, geography-specific patterns, or conflicting operationalizations.

Source syntax should be adapted rather than copied blindly:

- OpenAlex: broad text query and cited-by chaining
- PubMed/MEDLINE: MeSH plus title/abstract fields
- Embase: Emtree-aware and free-text Boolean logic
- Web of Science: topic field queries and citation chasing
- medRxiv and bioRxiv: plain Boolean/free-text frontier sweeps

## Large-Corpus Option

When the candidate set is large enough that manual title/abstract screening becomes the bottleneck, an ASReview-style active-learning workflow is acceptable, provided that:

- all human labels remain exportable
- the stop rule is documented
- the final retained set is still logged in `screening_decisions.csv`
- the review does not present the prioritization model as if it replaced human judgment

## PRISMA-Style Narrative Requirements

The narrative review must state inline counts for:

- records retrieved
- records after deduplication
- records screened
- records retained

These numbers must come from source files such as `search_log.csv` and `screening_decisions.csv`. If the counts cannot be recovered, write `not available`; do not estimate.

## Search Refresh Rule

If the review is meant for a current manuscript submission and the search is old enough that currency is doubtful, rerun or update the search and log the refresh. As a practical default, treat a search older than 6 months as stale unless the user explicitly accepts the older cutoff.

## Common Failure Modes

- Search log records queries but not dates or sources
- Search log records only one keyword pass and never shows reading-driven expansion
- A local paper set is imported and treated as if it were the original search
- Screening decisions only say "include" or "exclude" without reasons
- The narrative delegates all search detail to sidecar files
- Only exposure-outcome papers are retained, while measurement validity and confounder structure are ignored
- Search numbers in the narrative do not match the logs
