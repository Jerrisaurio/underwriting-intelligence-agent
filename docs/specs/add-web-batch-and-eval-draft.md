# Draft: add-web-batch-and-eval

Status: approved by the user on 2026-11-17. Source of truth for the OpenSpec change
`add-web-batch-and-eval`.

## Goal

1. Public web research with source citations, calibrated in depth, behind a provider interface
   (OpenAI as the implementation: the stack the hiring team uses).
2. Web-vs-internal conflicts surfaced explicitly; web never overrides internal data.
3. Batch mode with concurrency, caching, per-company failure isolation, resume and a run summary.
4. Observability: per-profile trace with tokens, web-search calls and cost.
5. Profile-level evaluation against verifiable facts.

## Decisions

| # | Topic | Decision |
|---|---|---|
| 1 | Provider | OpenAI Responses API with the `web_search` tool and structured output (`responses.parse`). Behind a `WebResearcher` interface; no other module imports the SDK. Model set by `UW_OPENAI_MODEL` (no hardcoded model: availability depends on the account). |
| 2 | No key / no model | Research is `unavailable`: profile built from internal data, `public_information.status = "unavailable"`, C_external stays neutral (0.5). Not an error. |
| 3 | Budget | T1 ≤ 2 web-search calls, T2 ≤ 5 (`max_tool_calls`); `max_output_tokens` capped. Tokens, search calls and cost (from `UW_PRICE_*` env prices) in `trace`. Cost is `null` when prices are not configured, never guessed. |
| 4 | Depth policy | T0 when short-circuited (R1), status INVALID/AMBIGUOUS, or research unavailable. T2 when any watchlist flag (active or resolved), credible LR > 0.8, total sum insured above the portfolio p90 of client totals, industry missing or name-mismatched, ≥ 2 disputed claims, or NOT_FOUND. Otherwise T1. |
| 5 | Data governance | Only the company name, state and depth leave the system. No premiums, claims or watchlist content are sent. |
| 6 | Untrusted web content | Instructions forbid following instructions found on pages; output is schema-constrained; every finding URL must appear in the sources the tool actually returned (otherwise dropped and counted). Actions remain rule-based, so web text cannot change a decision by itself. |
| 7 | Identity verification | The model must classify each finding's entity match (`confirmed` / `uncertain` / `different_company`). `different_company` findings are dropped (counted); `uncertain` are kept but excluded from rules. |
| 8 | Web conflicts | `WATCHLIST_STATUS_VS_NEWS` (resolved flag + confirmed negative finding of the same risk category published after the resolution) → high. `INDUSTRY_WEB_MISMATCH` (web industry, chosen from the portfolio's industry list, differs from the recorded one) → medium. `ADVERSE_MEDIA_NOT_IN_WATCHLIST` (confirmed negative sanction/fraud/litigation/payment finding with no matching flag) → medium. |
| 9 | Web rules | Web findings never produce DECLINE. `ADVERSE_MEDIA_NOT_IN_WATCHLIST` for sanction/fraud → REFER_TO_COMPLIANCE (R2c); other categories → REFER_TO_SENIOR_UNDERWRITER (R5f). High conflicts already map to R5e. |
| 10 | C_external | research done & identity confirmed → 0.8; done but company not found publicly → 0.5 (neutral: SMEs often have no footprint); identity contradicted (only `different_company` results) → 0.3; unavailable/failed/skipped → 0.5. |
| 11 | Batch input | `.txt` (one name per line, `#` comments) or `.csv` with `name` and optional `state`. |
| 12 | Batch output | `.jsonl` (one profile per line, input order) + `<out>.summary.json` (counts by status/action, errors, tokens, cost, latency p50/p95). Resume: names already in the output file are skipped. |
| 13 | Failures | One company failing → `status: ERROR` profile with the error message; the batch continues. Web call: SDK retries (2) + timeout; on failure the profile keeps internal data and `public_information.status = "failed"`. |
| 14 | Cache | SQLite in `UW_CACHE_DIR` (default `.cache/`), key = provider + model + prompt version + name + state + depth, TTL `UW_CACHE_TTL_DAYS` (default 7). Duplicates inside a batch are computed once. |
| 15 | Concurrency | Thread pool (`--workers`, default 4): web calls are I/O bound; internal steps are ms. |
| 16 | Profile evaluation | On a sample of clients (input = one of their spellings): watchlist recall (every entry of the true ClientId confirmed; target 100%), aggregate exactness vs an independent pandas computation, schema validity, evidence-id validity, error rate, latency, cost per lookup. Web part: hand-labelled real-company set (expected identity / known facts), run only when a key is configured; otherwise reported as not run. |

## Unhappy paths

| Case | Behaviour |
|---|---|
| No API key / model | research `unavailable`, profile still complete, exit 0 |
| Rate limit / timeout / 5xx | SDK retries; then `failed`, internal profile kept |
| Refusal / unparsable output | `failed` with reason; no partial findings |
| Finding URL not among returned sources | dropped, counted in `public_information.dropped_unverified` |
| Batch input missing / empty / bad CSV header | exit 2 with message |
| Exception while profiling one company | `status: ERROR` line, batch continues, counted in summary |
| Output file exists | resume (skip done names) unless `--overwrite` |
| Cache file corrupt | cache disabled with a warning, run continues |
