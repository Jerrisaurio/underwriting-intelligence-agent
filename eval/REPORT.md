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
| Is the public information sound? | Hand-labelled web set; **not run** in this submission (no API key available, see below). |

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

## 5. Web research and cost (`run_web_eval.py`)

**Not run in this submission:** no OpenAI API key was available in the development environment.
The runner reports `not_run` and exits 0. The web layer is covered by unit tests with a fake
OpenAI client (source verification, other-company filtering, failures, cache, conflicts, rules,
cost accounting).

The labelled set (`eval/web_cases.yaml`) has 11 real public companies with their expected
industry, plus 2 synthetic controls that must produce no confirmed finding. For every watchlist
flag linked to those profiles (read from the data at run time, not stored in the file), the
runner lists the public findings of the same risk category for human review: several
real-company flags read as planted conflicts, and this check is what would confirm or refute them.

Cost per lookup is bounded by design and reported per profile once prices are configured:

```
cost = input_tokens/1e6 · UW_PRICE_INPUT_PER_MTOK + output_tokens/1e6 · UW_PRICE_OUTPUT_PER_MTOK
     + web_search_calls · UW_PRICE_PER_WEB_SEARCH
```

with at most 1 model call and 2 (T1) or 5 (T2) searches per company, 0 for short-circuited or
ambiguous lookups, and 0 for cache hits. Prices are configuration, never guessed: unpriced runs
report token counts and `cost_usd: null`.

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
uv run python eval/run_web_eval.py            # needs OPENAI_API_KEY + UW_OPENAI_MODEL
```
