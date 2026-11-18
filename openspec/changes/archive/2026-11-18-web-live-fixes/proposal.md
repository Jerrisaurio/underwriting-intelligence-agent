## Why

The first runs against the real OpenAI API (13 companies, `gpt-4o-mini`) validated the web layer
(0 failures, identity and industry 100%, 12 invented URLs filtered out) but exposed behaviour the
fake client could not: the model asserts that a company exists, and names its industry, without any
verified finding (a fictitious control company came back as "found"; a conflict was raised with zero
findings); it uses 1 of the 5 searches allowed at T2, so adverse-media coverage is shallow and varies
between runs; and an *active* watchlist flag contradicted by public news of its resolution goes
unnoticed. The evaluation also does not record searches, tokens or variability, so cost and depth
cannot be reported.

## What Changes

- Web identity is **verified** only when at least one kept finding is `confirmed` with a verified
  URL. Unverified identity never fills the industry and never raises INDUSTRY_WEB_MISMATCH or
  COVERAGE_VS_WEB_INDUSTRY.
- New conflict `ACTIVE_FLAG_VS_NEWS` (medium): active confirmed flag vs. a confirmed public finding
  of the same risk category that reports a resolution. Internal data stays authoritative.
- T2 instructions ask for one search per risk category (sanctions, fraud, litigation, credit,
  payments) so the budget is used.
- `eval/run_web_eval.py`: `--model`, `--runs N`, per-case searches, tokens, rules and run-to-run
  consistency; aggregate averages.
- Model comparison `gpt-4o-mini` vs `gpt-5.4-mini`; results and the closed watchlist review in
  `eval/REPORT.md` and `docs/OPEN_ITEMS.md`.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `web-research`: verified identity rule; per-category search instructions at T2.
- `underwriting-profile`: ACTIVE_FLAG_VS_NEWS conflict; industry fill and industry conflicts only on verified identity.
- `profile-evaluation`: web evaluation records searches, tokens, rules and consistency, per model.

## Impact

- Code: `web/openai_researcher.py`, `web/models.py` (prompt version bump → cache invalidation),
  `agent/conflicts.py`, `agent/pipeline.py`, `agent/confidence.py`, `schema/profile.py`,
  `eval/run_web_eval.py`, tests.
- Docs: `docs/SCHEMA.md`, `eval/REPORT.md`, `docs/OPEN_ITEMS.md`.
- Real API spend for the comparison (~52 lookups); no new dependencies.
