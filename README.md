# Underwriting Intelligence Agent

Given a company name, builds a structured, auditable **underwriting profile** for a Mexican
P&C portfolio: who the company is, the relationship with it, how it has performed as a client,
its risk flags, what is publicly known, where the sources disagree, how confident the agent is,
and a recommended action.

It reads three internal databases first (portfolio, claims, watchlist), then the public web
(OpenAI Responses API with web search, optional), and never hides ambiguity or conflicts.

```bash
uv run uw-agent profile "Petrolera del Golfo" --as-of 2025-09-28
```
```text
# Illustrative output for a fictitious company (abridged)
status: COMPLETE · action: DECLINE (R1: active critical sanction, confirmed by ClientId)
risk_flags: sancion_regulatoria/crítico (confirmed) · riesgo_crediticio/alto
            (possible: watchlist ClientId not in portfolio, linked by name)
conflicts:  WATCHLIST_LINKED_BY_NAME_ONLY · FLAG_PREDATES_RELATIONSHIP · INDUSTRY_MISSING
web:        skipped (short-circuit: no public information would change a DECLINE)
```

## Setup

Python 3.12 (pinned in `.python-version`). Dependencies are declared in `pyproject.toml` and
locked to exact versions in `uv.lock`; `requirements.txt` / `requirements-dev.txt` are generated
from that lock, so both options install the same versions.

**Option A, [uv](https://docs.astral.sh/uv/) (recommended):**

```bash
uv sync                       # creates .venv with runtime + dev dependencies
uv run uw-agent --help        # prefix commands with `uv run`
```

**Option B, pip:**

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt   # dev file only needed for tests/lint
pip install -e . --no-deps                                 # installs the `uw-agent` command
uw-agent --help               # in this README, drop the `uv run` prefix
```

Then, optionally: `cp .env.example .env` (see below).

| Dependency | Why |
|---|---|
| `pandas` | Loading and aggregating the three CSV databases |
| `rapidfuzz` | Fuzzy name matching (string similarity, Damerau-Levenshtein) |
| `pydantic` | Output schema, validation and JSON Schema export |
| `pyyaml` | Curated alias and related-entities tables |
| `typer` | Command-line interface |
| `openai` | Web research (Responses API + web search); only used when configured |
| `pytest`, `ruff` | Tests and lint (development only) |

After changing dependencies, regenerate the requirements files with
`uv export --no-dev --no-hashes --no-emit-project -o requirements.txt` (and `--only-dev` for
`requirements-dev.txt`).

Place the source files in `data/` (they are not versioned, see `data/README.md`):
`portfolio_mexico.csv`, `claims.csv`, `watchlist.csv`.

Optional configuration (`.env`, nothing is hardcoded):

| Variable | Purpose |
|---|---|
| `UW_DATA_DIR` | Data directory (default `data`). |
| `UW_AS_OF_DATE` | Reference date for "active policy" and for excluding later data (default today). |
| `OPENAI_API_KEY`, `UW_OPENAI_MODEL` | Enable web research (recommended model: `gpt-5.4-mini`, chosen with measured data in `eval/REPORT.md` §5). Without both, the agent runs on internal data only and says so in each profile. |
| `UW_PRICE_INPUT_PER_MTOK`, `UW_PRICE_OUTPUT_PER_MTOK`, `UW_PRICE_PER_WEB_SEARCH` | Prices for cost reporting. Unset → token counts reported, cost `null` (never guessed). |
| `UW_CACHE_DIR`, `UW_CACHE_TTL_DAYS` | Web-research cache (default `.cache`, 7 days). |

## Usage

> Company names in this README are **fictitious** (the repository never includes data from the
> source files). To try real lookups, pick names from your copy of the data, e.g.
> `uv run python -c "import pandas as pd; print(pd.read_csv('data/portfolio_mexico.csv', encoding='utf-8-sig').client_name.drop_duplicates().sample(10, random_state=1).to_string(index=False))"`.
> Many names are shared by several clients: add `--state` to disambiguate.

```bash
uv run uw-agent profile "Petrolera del Golfo"                 # one company, JSON to stdout
uv run uw-agent profile "Grupo Quimera S.A." --state Jalisco     # disambiguate homonyms
uv run uw-agent batch companies.csv -o out/profiles.jsonl     # batch (CSV name[,state] or .txt)
uv run uw-agent resolve "Tecnologías Arcoíris SACV"              # entity resolution only
uv run uw-agent data-quality                                  # dataset-level data checks
uv run uw-agent schema                                        # JSON Schema of the profile
```

- `batch` writes one profile per line plus `out/profiles.summary.json` (counts by status and
  action, errors, tokens, cost, latency). Re-running resumes; `--workers`, `--overwrite`,
  `--no-cache`, `--as-of` are available.
- Exit codes: `0` profile(s) produced (NOT_FOUND / AMBIGUOUS are valid answers), `1` system
  failure (missing or malformed data), `2` invalid input.
- The output schema, the confidence formula and every recommended action are documented in
  **[`docs/SCHEMA.md`](docs/SCHEMA.md)**.

## Tests and evaluation

```bash
uv run pytest                                   # 115 unit tests, < 2 s, no network
uv run python eval/generate_resolution_cases.py
uv run python eval/run_resolution_eval.py       # entity resolution, 1,030 cases
uv run python eval/run_profile_eval.py [--with-state]   # full profiles vs verifiable facts
uv run python eval/run_web_eval.py              # web set (needs OpenAI credentials)
```

Results and their interpretation: **[`eval/REPORT.md`](eval/REPORT.md)**. Headlines:
entity resolution 99.0% accurate with **0% confident wrong answers**; **100% watchlist recall**
(188/188 entries) and 100% exact aggregates on 488 profiles; 500-company batch in 6.7 s;
live web research with `gpt-5.4-mini`: 100% verified identity and industry on 11 real companies,
0 fictitious companies "found", model chosen over `gpt-4o-mini` with measured data;
**$0.031 per researched lookup** (≈ $1.90 per 100 companies in batch, $0 for internal-only).

## Architecture

A **modular monolith**: one package, clear layers, no network between them. The orchestration
is a **fixed, code-driven pipeline**, not a free-form LLM loop:

```
name ─► [1] entity resolution ──► AMBIGUOUS ──► candidates + NEEDS_CLARIFICATION
          (deterministic)    └──► NOT_FOUND / INVALID ──► honest empty profile
            │ ClientId (+ homonym candidates)
            ▼
        [2] watchlist screening   MANDATORY, over every plausible candidate
        [3] portfolio + claims    at as_of_date, evidence ids on every number
        [4] related entities      curated corporate groups / former names
            │
            ├── R1 confirmed critical sanction/fraud ──► short-circuit (skip web)
            ▼
        [5] web research          depth T0/T1/T2 by risk signals, ≤ 2/5 searches,
            (OpenAI, optional)    only name+state sent, URLs verified against tool sources
            ▼
        [6] conflicts ─► [7] confidence (formula) ─► [8] action (rule precedence)
            ▼
        UnderwritingProfile JSON + trace (steps, tokens, cost)
```

```
src/uw_agent/
  data/         database layer: typed CSV loading, ClientId-indexed repository, quality checks
  resolution/   entity resolution: normalization, alias table, resolver
  tools/        tool definitions: watchlist screening, client history, related entities
  web/          web research: interface, OpenAI implementation, depth policy
  agent/        agent logic: pipeline, conflicts, rules, confidence
  schema/       output schema (Pydantic → JSON Schema)
  infra/        cache
  batch.py      batch runner;  cli.py  command line
eval/           evaluation datasets (generated), runners, REPORT.md
openspec/       specifications: current specs + archived changes
tests/          unit tests on a small hand-built dataset that reproduces the hard cases
```

## Key decisions and why

1. **Code decides, the LLM classifies.** Source order, mandatory checks, short-circuits,
   conflicts, confidence and the action are deterministic rules. The model only searches and
   classifies findings (category, stance, entity match). This makes the agent testable with exact
   oracles, auditable rule by rule (`triggered_rules`), immune to a model "deciding" to skip the
   watchlist, and robust to prompt injection from web pages: page text cannot change a decision.
2. **ClientId is the entity, not the name.** In this data one ClientId has up to 7 spellings and
   one spelling up to 11 ClientIds (74% of names are shared). Aggregation is always per ClientId;
   homonyms are never merged.
3. **Never guess silently.** A tie is resolved to the leader only when it holds ≥ 70% of the
   policies; otherwise the agent asks. The evaluation shows that lowering the threshold trades
   "please clarify" for "wrong company" (40% wrong at 0.5), not for accuracy.
4. **Screen the watchlist for every plausible candidate.** Flags of non-chosen homonyms appear as
   `possible`, never as `confirmed`, and never cause a DECLINE. Result: 100% watchlist recall
   even when the name is ambiguous. No fuzzy matching against the watchlist.
5. **Internal data is authoritative.** Web evidence can raise conflicts and escalate to a human
   (R2c, R5f) but never declines and never overwrites an internal fact. Absence of web evidence
   is neutral (most private SMEs have no footprint).
6. **Depth calibration and cost.** No web call for short-circuits, ambiguous or invalid input;
   identity check (T1) by default; adverse-media search (T2) only with risk signals. One model
   call per company, bounded searches, SQLite cache keyed by model and prompt version.
7. **Provider behind an interface.** `WebResearcher` with an OpenAI implementation (the hiring
   team's stack); switching provider is one class.
8. **Spec-driven continuity.** Requirements live in `openspec/` (5 capability specs, each
   scenario mapped to a test or eval case; changes proposed, implemented and archived).
   `docs/OPEN_ITEMS.md` tracks what is deliberately deferred.

## Write-up

### Tradeoffs

- **Deterministic pipeline vs. agentic loop.** Less flexible than letting a model plan its own
  queries, but every behaviour the brief calls mandatory is guaranteed, and the internal profile
  costs $0 and takes milliseconds. The LLM is used where it adds unique value (open-web search
  and reading).
- **Asking vs. guessing.** Without a state, 73% of synthetic names end in NEEDS_CLARIFICATION.
  That is the price of 0% confident wrong answers; with the state, 84–86% resolve correctly.
- **Conservative confidence.** Weights are reasoned, not fitted (there is no outcome data to fit
  them). Thin clients land in INSUFFICIENT_INFORMATION (28% of lookups with state) by design.
- **Written premium.** The loss ratio uses written premium (no earned premium in the source), so
  2-year policies are not pro-rated.

### Known limitations

- **Cost figures depend on list prices.** A researched lookup costs ≈ $0.031 with `gpt-5.4-mini`
  (≈ $1.90 per 100 companies in batch; $0 for short-circuited, ambiguous, cached or internal-only
  lookups), computed from measured usage and OpenAI list prices of 2026-11-18. Prices are never
  hard-coded: they come from the `UW_PRICE_*` variables and must be updated when they change
  (`eval/REPORT.md` §5).
- **Web research varies between runs** (search results differ): with `gpt-5.4-mini`, 3 of 13
  companies got a different action in two runs. The cache keeps repeated lookups consistent and web
  evidence can only escalate to a human.
- **Aliases outside the data** ("Banco Nacional de México" for Banamex) are missed by the
  deterministic resolver (1/7 held-out aliases found).
- **Text-only identity.** Names one letter apart (e.g. a fictitious "Servicios Lunar" vs "Servicios Lunas") cannot be told from typos;
  they are flagged, not resolved.
- **Data quirks taken at face value, but surfaced:** `reserved_mxn` on closed claims is reported
  as "registered reserve", not exposure; 46 resolved watchlist entries whose notes describe ongoing
  situations raise a high conflict; industry is missing for 35% of policies.
- **Evaluation ground truth comes from the same dataset** (except held-out aliases and the web
  set); there is no ground truth for the recommended action itself.

### With more time

1. Record live responses as fixtures for reproducible web evals; require two independent sources
   before an adverse web finding escalates, to reduce run-to-run variance.
2. LLM/web fallback for out-of-data aliases (only on NOT_FOUND, cached), measured on the
   held-out alias set.
3. Calibrate confidence against underwriter decisions (or a labelled sample) and report
   reliability curves; tune rule thresholds with the business.
4. Earned-premium loss ratio, claim-severity trends and portfolio benchmarks by coverage.
5. Expose the pipeline as an API (the modular monolith keeps that one module away) and add
   structured logging/metrics export for production monitoring.

## Security

- **Secrets:** only from the environment / a local `.env` (git-ignored); none in code, history or CI.
- **Data minimisation:** the web provider receives only company name, state and depth, with
  `store=false`; no premiums, claims or watchlist content leave the system.
- **Untrusted web content:** the model only classifies findings (strict JSON schema); every URL must
  be one the search tool returned; conflicts, confidence and actions are computed by code, and web
  evidence can never produce DECLINE. Consumers rendering `claim` / `description` in HTML must escape
  them (they are third-party text).
- **Bounded cost / availability:** per-lookup search budget, output-token cap, request timeout and
  SDK retries; batch failures are isolated per company.
- **Local storage:** the cache holds public web findings only (`.cache/`, git-ignored); SQLite access
  is parameterised. Batch outputs contain internal data and are written only where the user asks.
- **Supply chain:** dependencies locked (`uv.lock`), `pip-audit` reports no known vulnerabilities;
  CI runs with read-only repository permissions and no secrets.

## Data handling

Source CSVs, the challenge PDF and every dataset derived from the data (eval cases, results) are
excluded from version control. Only the company name and state are sent to the web provider.
