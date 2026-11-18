# Evaluation report

All numbers below come from the scripts in `eval/` run on the provided data
(`as_of = 2025-09-28`, the approximate extraction date of the files, so "active policy" is
meaningful). Datasets are generated deterministically (fixed seeds) from the source CSVs and are
not committed; rerun them with the commands at the end.

## What can and cannot be measured

The data has no ground truth for *the right underwriting decision*, so accuracy of the
recommended action cannot be measured directly. The evaluation instead checks everything that
is verifiable:

| Question | How it is measured |
|---|---|
| Does the agent identify the right company? | Entity-resolution set (1,030 cases), ground truth from the ClientIds behind every recorded spelling. |
| Does it ever lose a risk flag? | Watchlist recall over every watchlist entry. |
| Are the numbers right? | Aggregates recomputed with an independent pandas implementation. |
| Is every fact traceable? | Every evidence id in every profile checked against the source rows. |
| Is it reliable and cheap at scale? | Error rate, latency, cost per lookup, 500-company batch. |
| Is the public information sound? | Hand-labelled web set, live, 2 models × 2 runs (section 5). |

## 1. Entity resolution (`run_resolution_eval.py`, 1,030 cases)

| Category | n | Accuracy | False resolution | Candidate recall |
|---|---:|---:|---:|---:|
| Exact spelling | 120 | 100% | 0% | 100% |
| Typographic (case, accents, punctuation) | 120 | 100% | 0% | 100% |
| Legal-form variants (`SACV`, `SAPI`…) | 120 | 100% | 0% | 100% |
| Truncated names (`Arcoíris S.A. de C.V.`) | 120 | 100% | 0% | 100% |
| Real companies (trade names, acronyms) | 120 | 98.3% | 0% | 98.3% |
| Typo in generic word | 120 | 100% | 0% | 100% |
| Typo in distinctive word | 120 | 100% | 0% | 100% |
| State hint on homonyms | 120 | 100% | 0% | 100% |
| Curated aliases | 6 | 100% | 0% | 100% |
| **Held-out aliases** (not curated) | 7 | **14.3%** | 0% | 14.3% |
| Non-clients (hard negatives) | 52 | 96.2% | 0% | – |
| Invalid input | 5 | 100% | 0% | – |
| **Overall** | **1,030** | **99.0%** | **0.0%** | **99.2%** |

- *False resolution* = the wrong company returned **without** an ambiguity flag: the costliest
  error (a confident profile of the wrong company). It is 0 in every category.
- An ambiguous name counts as correct only if the agent flags the ambiguity and the true client
  is among the candidates.
- Latency p50 0.9 ms, p95 1.5 ms; no LLM involved (cost 0).

Failures, all understood:
- Held-out aliases (6/7 missed: "Banco Nacional de México" → Banamex, "CPKC de México" → KCSM…):
  names that appear nowhere in the data or the alias table. This is the honest out-of-sample
  measure of the deterministic resolver; it is the gap an LLM/web alias layer would close.
- Two single generic words that are part of dozens of client names: genuinely ambiguous; the
  agent returns AMBIGUOUS but the intended real company is beyond the top-10 candidates shown.
- Two non-clients one letter away from existing clients (think "Servicios Lunar" vs an existing
  "Servicios Lunas"): indistinguishable from a typo by text alone. Flagged, never asserted.

Calibration (resolved cases): confidence [0.6, 0.8) → 100% precision, [0.8, 0.95) → 99.0%,
[0.95, 1.0] → 100%. The confidence is **conservative**; the set lacks enough hard cases to say it
is well calibrated rather than merely safe.

### Development notes (the evaluation changed the code and the test)

- Whole-string fuzzy matching resolved "Constructora **Modelo**" to "Constructora **Morelos**"
  (similarity 0.94). Fixed by requiring every word to match its counterpart.
- The first typo generator only corrupted the generic first word ("Sevicios"), never the
  distinctive one, inflating results. Split into two categories; the distinctive-word category
  exposed transposition misses in short words ("Nvoa"), fixed with a Damerau-Levenshtein rule.
- The ground truth originally called "X **SACV**" unique because only one ClientId used that
  exact spelling, although "X S.A. de C.V." is shared. Ambiguity is now judged on the company
  name, not on how the legal form was typed.

## 2. Homonyms: the dominant property of this data

74% of full company names belong to more than one ClientId (mostly the same name in different
states). The resolver profiles the leader only when it holds ≥ 70% of the tied candidates'
policies; otherwise it asks for clarification. Measured on 800 random clients:

| Dominance threshold | State given | Correct client | Asks to clarify | Other client (flagged as ambiguous) |
|---|---|---:|---:|---:|
| **0.7 (chosen)** | no | 14% | 73% | 13% |
| **0.7 (chosen)** | **yes** | **84%** | 11% | 5% |
| 0.6 | no | 19% | 56% | 25% |
| 0.5 | no | 25% | 35% | **40%** |
| 0.5 | yes | 89% | 1% | 10% |

Lowering the threshold does not make the agent more accurate: it turns "please clarify" into
"wrong company". The state is the real lever, which is why the batch CSV accepts a `state`
column. No configuration produced an unflagged wrong client.

## 3. Profile evaluation (`run_profile_eval.py`)

Sample: all 181 ClientIds with watchlist entries + 300 random clients + the 7 watchlist entries
whose ClientId is not in the portfolio (reachable by name only) = 488 lookups. Input = one of the
client's recorded spellings.

| Metric | Without state | With state |
|---|---:|---:|
| Errors | 0 / 488 | 0 / 488 |
| Resolved to the true client | 15.0% | 85.9% |
| **Watchlist recall, any link** (188 entries) | **100%** | **100%** |
| Watchlist recall as `confirmed` when resolved | 100% | 100% |
| Aggregates exact vs independent computation | 100% | 100% |
| Profiles citing a non-existent evidence id | 0 | 0 |
| Schema round-trip valid | 488 | 488 |
| Latency p50 / p95 | 3.6 / 11.0 ms | 7.5 / 10.1 ms |
| Cost per lookup (internal only) | $0 | $0 |

Watchlist recall is 100% even when the name is ambiguous, because screening covers every
plausible candidate (flags of non-chosen homonyms appear as `possible`). Missing a sanction is
the error the design treats as unacceptable.

Recommended actions with state (488 lookups): PROCEED_STANDARD 195, INSUFFICIENT_INFORMATION 138,
REFER_TO_COMPLIANCE 43, NEEDS_CLARIFICATION 42, REFER_TO_SENIOR_UNDERWRITER 31,
PROCEED_WITH_CONDITIONS 24, DECLINE 15. Confidence: HIGH 94, MEDIUM 189, LOW 205.
The share of INSUFFICIENT_INFORMATION (28%) is driven by thin clients (1–2 policies, no
industry, no active policy): the agent says so instead of producing a confident-looking profile
on thin evidence, as the brief asks.

## 4. Scale (`uw-agent batch`)

500 distinct clients (CSV with name + state), 4 workers, internal data only:
**6.7 s wall time** including data loading, 0 errors, 3 duplicates computed once,
latency p50 16 ms / p95 138 ms. Resume after interruption re-processes nothing already written.

## 5. Web research: live runs and model choice (`run_web_eval.py`)

Live runs against the OpenAI Responses API with the `web_search` tool, on the hand-labelled set
(`eval/web_cases.yaml`: 11 real public companies with their expected industry + 2 synthetic
controls), **2 runs per company**, cache bypassed, `as_of = 2025-09-28`.

| Metric | `gpt-4o-mini` | `gpt-5.4-mini` |
|---|---:|---:|
| Lookups (researched) | 26 (24) | 26 (24) |
| Provider failures | 0 | 0 |
| **Identity accuracy** (verified identity = label) | **45.8%** | **100%** |
| **Industry accuracy** (closed list) | **38.9%** | **100%** |
| Synthetic controls verified as real (false positives) | 0 | 0 |
| Avg. web searches per lookup (T2 only) | 1.0 (1.0) | 1.8 (1.95) |
| Avg. findings kept per lookup | 0.33 | 4.5 |
| Adverse findings kept (total) | 0 | 31 |
| Findings dropped: URL not among returned sources | 34 | 6 |
| Findings dropped: different company | 0 | 4 |
| Run-to-run agreement (identity, industry, action) | 92.3% | 76.9% |
| Avg. input / output tokens | 8,174 / 282 | 12,045 / 863 |
| Avg. latency | 3.5 s | 7.4 s |

**What the live runs changed (change `web-live-fixes`).** The first live run reported 100%
identity accuracy for `gpt-4o-mini`, but the model was asserting identities (and industries) with
no verified finding, including "finding" a fictitious control company. Identity now counts only
when a kept finding with a verified URL confirms the company; under that rule `gpt-4o-mini` drops
to 46%, because most of the URLs it cites are not among the sources its search returned (34
dropped). Its 1-search behaviour at T2 also left adverse media unexplored (0 adverse findings).

**Model choice: `gpt-5.4-mini`.** It verifies every real company and its industry, finds the
adverse media T2 exists for, and invents far fewer sources, at about 1.5× the input tokens, 3× the
output tokens and 2× the latency of `gpt-4o-mini`. Its weakness is consistency: in 3 of 13
companies the two runs led to different actions, because a borderline adverse finding appeared
in one run and not the other. Rules are deterministic given the findings; the variance comes from
search. Mitigations: the 7-day cache makes repeated lookups consistent, and web evidence can only
escalate to a human, never decline. The model is configuration (`UW_OPENAI_MODEL`).

**Watchlist review (human-review output).** For the 8 watchlist flags of real companies, public
sources corroborated 3 (an active litigation, an active regulatory sanction and an active fraud
investigation), contradicted none, and showed nothing for 5. One of those 5 is a critical
"international sanctions" flag on a real company, checked with a dedicated T2 lookup (its profile
short-circuits the web step by design): no public source supports it. Absence of evidence does
not refute a flag, but this is the kind of planted conflict a compliance officer must verify.

**Cost per lookup (USD).** Computed from the usage measured in the live runs above and OpenAI list
prices for `gpt-5.4-mini` **as of 2026-11-18**: input $0.75 / 1M tokens, output $4.50 / 1M tokens,
`web_search` tool $10.00 / 1k calls ($0.01 per call; search content tokens are billed at model
rates and are already included in the measured `input_tokens`). Prices are configuration, never
code: they live in `.env` and change over time or by contract.

```
cost = input_tokens/1e6 · UW_PRICE_INPUT_PER_MTOK + output_tokens/1e6 · UW_PRICE_OUTPUT_PER_MTOK
     + web_search_calls · UW_PRICE_PER_WEB_SEARCH
```

Measured per lookup (`gpt-5.4-mini`, 2 runs × 13 companies, 24 researched lookups):

| Lookup type | n | Input tokens | Output tokens | Web searches | Cost per lookup |
|---|---:|---:|---:|---:|---:|
| T1 (identity check) | 4 | 9,195 | 465 | 1.0 (max 2) | **$0.019** |
| T2 (adverse media) | 20 | 12,615 | 943 | 1.95 (max 5) | **$0.033** (max seen $0.049) |
| All researched | 24 | 12,045 | 863 | 1.79 | **$0.031** (range $0.018–$0.049) |
| Short-circuited (R1), ambiguous, invalid | – | 0 | 0 | 0 | $0 |
| Cache hit (same company within 7 days) | – | 0 | 0 | 0 | $0 |
| Internal-only (no key configured) | – | 0 | 0 | 0 | $0 |

Split of the average researched lookup: tokens $0.013 (42%), web searches $0.018 (58%), so the
search budget per depth is the main cost lever. The whole 26-lookup live evaluation cost ≈ $0.74.

**Batch projection.** With the depth mix measured on 400 random clients (§6: 9% T0, 79% T1,
12% T2) and the per-depth costs above, a batch costs about **$0.019 per company**, i.e.
**≈ $1.90 per 100 companies** and **≈ $9.50 per 500**, before cache hits. This is an upper
estimate: lookups that end in NEEDS_CLARIFICATION or a short-circuit make no web call.

With the prices set in `.env`, every profile (`trace.cost_usd`) and every batch summary
(`total_cost_usd`, `cost_per_lookup_usd`) report dollars directly.

## 6. Depth calibration (web research budget)

Depth chosen on 400 random clients (with state), with a stub researcher so only the policy is
measured:

| Policy | T0 | T1 | T2 | Max searches per lookup (avg) |
|---|---:|---:|---:|---:|
| Before audit (industry issues → T2) | 37 | 199 | 164 | 3.05 |
| **After audit** (industry issues → T1) | 37 | **314** | **49** | **2.18** |

Before the change, 79% of T2 lookups were triggered only by a missing or name-inconsistent
industry, a data-quality gap that the identity check (T1) already answers. T2 is now reserved
for risk signals (watchlist entries, top-decile sum insured, credible loss ratio > 80%, disputed
claims), cutting the search budget by 29%.

## Reproduce

```bash
uv run python eval/generate_resolution_cases.py
uv run python eval/run_resolution_eval.py
uv run python eval/run_profile_eval.py
uv run python eval/run_profile_eval.py --with-state
uv run python eval/run_web_eval.py --model gpt-5.4-mini --runs 2   # needs OPENAI_API_KEY
```
