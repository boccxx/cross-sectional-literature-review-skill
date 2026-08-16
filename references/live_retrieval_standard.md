# Live Retrieval Standard

## Purpose

This file defines what counts as a real search execution for this skill.

The key distinction is simple:

- a `search plan` is not yet a search
- a `search_log.csv` with planned rows is not yet a completed retrieval
- a completed search must produce raw source payloads, candidate records, and updated retrieval counts

## Default Execution Stack

The default execution script is:

- `scripts/build_search_plan.py`
- `scripts/run_live_search.py`

The intended order is:

1. build the multi-round plan
2. execute the live search
3. inspect anchor papers
4. revise or refresh later-round query families if the reading reveals new terminology or theories
5. rerun targeted rows as needed

## Source Handling Rules

### Direct API Retrieval

These sources should be queried directly when possible:

- `OpenAlex`
- `PubMed/MEDLINE`
- `medRxiv`
- `bioRxiv`

For `OpenAlex`, `PubMed/MEDLINE`, `medRxiv`, and `bioRxiv`, the retrieval should generate:

- raw JSON or XML-derived payload captures under `raw_results/`
- `candidate_records_raw.csv`
- `candidate_records_dedup.csv`
- updated `search_log.csv` with real `date_searched`, `n_retrieved`, and execution status

If the local environment lacks a usable certificate chain, `run_live_search.py` may be run with `--insecure-skip-verify`, but this should be treated as an environment workaround rather than the normal default.

### Access-Controlled Sources

These are still mandatory review sources, but they may require subscription, institutional access, or provider credentials:

- `Embase`
- `Web of Science`

If they cannot be queried programmatically in the current environment:

- keep them in `search_log.csv`
- mark the row honestly, for example `blocked_auth_required`
- state the reason in `note`
- do not delete the source to make the review appear complete

## Preprint Retrieval Rule

The official bioRxiv / medRxiv API exposes interval-style endpoints rather than a fully general keyword-search API.

Therefore, the acceptable default behavior is:

1. retrieve by date window from the official API
2. rank locally by overlap with the planned query
3. keep the scan cap explicit in the search note

This is acceptable only if the search log states that local ranking was applied after official source retrieval.

## Minimum Execution Artifacts

After a real retrieval run, the review directory should usually contain:

- `search_log.csv`
- `search_strategy.md`
- `candidate_records_raw.csv`
- `candidate_records_dedup.csv`
- `raw_results/`

These are upstream retrieval artifacts. They precede screening and synthesis.

## Honesty Rule

Do not claim:

- that all six core sources were successfully queried if some were blocked
- that preprint retrieval was free-text searched if it was actually interval retrieval plus local ranking
- that imported local papers are equivalent to a current multi-source search

The search layer should be inspectable enough that another researcher could understand what actually happened.
