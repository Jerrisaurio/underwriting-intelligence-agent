## Why

The profile is complete for internal data, but the challenge asks for public information too,
for batch runs of hundreds of companies with cost, caching and failure handling as first-class
concerns, and for an evaluation of the agent. Requirements were closed in
`docs/specs/add-web-batch-and-eval-draft.md`.

## What Changes

- Web research behind a `WebResearcher` interface; OpenAI Responses API (`web_search` tool,
  structured output) as the implementation; degrades to `unavailable` without key or model.
- Depth policy T0/T1/T2, budgets, source-verified findings, identity verification.
- Web-vs-internal conflicts and two web rules (never DECLINE); C_external from research outcome.
- `uw-agent batch` with concurrency, SQLite cache, resume, per-company error isolation, summary.
- Trace with tokens, web-search calls and cost.
- `eval/run_profile_eval.py` against verifiable facts; hand-labelled web set.

## Capabilities

### New Capabilities
- `web-research`: provider-agnostic public research with citations, depth policy and budgets.
- `batch-processing`: batch command, cache, resume, failure isolation, run summary.
- `profile-evaluation`: profile-level evaluation (watchlist recall, aggregates, schema, cost).

### Modified Capabilities
- `underwriting-profile`: adds web conflicts, web rules and the external-evidence factor.

## Impact

- New dependency: `openai`. New packages `src/uw_agent/web/`, `src/uw_agent/infra/`.
- New env vars: `OPENAI_API_KEY`, `UW_OPENAI_MODEL`, `UW_PRICE_*`, `UW_CACHE_DIR`, `UW_CACHE_TTL_DAYS`.
- Only company name and state are sent to the provider.
