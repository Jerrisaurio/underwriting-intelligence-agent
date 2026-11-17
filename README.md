# Underwriting Intelligence Agent

Builds a structured underwriting profile for a company from three internal databases
(portfolio, claims, watchlist) and public web sources.

> **Status:** work in progress. Implemented: data layer, entity resolution (+ evaluation),
> internal tools (watchlist, portfolio, claims, related entities), profile schema, rule-based
> conflicts / action / confidence and the `profile` command. Next: web research, batch mode,
> profile-level evaluation. Specs live in [`openspec/`](openspec/); deferred items in
> [`docs/OPEN_ITEMS.md`](docs/OPEN_ITEMS.md).

## Setup

Requires [uv](https://docs.astral.sh/uv/) (the Python version is pinned in `.python-version`).

```bash
uv sync                  # creates .venv from uv.lock
cp .env.example .env     # optional: UW_DATA_DIR, UW_AS_OF_DATE
```

The CSVs are expected in `data/` (`portfolio_mexico.csv`, `claims.csv`, `watchlist.csv`).

## Usage

```bash
uv run uw-agent profile "Pemex"                              # full profile as JSON
uv run uw-agent profile "Grupo Nova S.A." --state Jalisco    # disambiguate homonyms
uv run uw-agent profile "Coppel" --as-of 2025-09-28          # reference date
uv run uw-agent resolve "Tecnologías Bajío S.A. de C.V."     # entity resolution only
uv run uw-agent data-quality                                 # dataset-level checks
uv run uw-agent schema                                       # JSON Schema of the profile
```

Exit codes of `profile`: `0` a profile was produced (any status, including NOT_FOUND and
AMBIGUOUS), `1` system failure (missing or malformed data), `2` invalid input.
The output schema, the confidence formula and every possible action are documented in
[`docs/SCHEMA.md`](docs/SCHEMA.md).

## Tests and evaluation

```bash
uv run pytest
uv run python eval/generate_resolution_cases.py   # rebuilds eval/datasets/resolution_cases.jsonl
uv run python eval/run_resolution_eval.py         # metrics per category + calibration
```

## Repository layout

```
src/uw_agent/
  data/          database layer: typed CSV loading, indexed repository, data-quality checks
  resolution/    entity resolution: normalization, alias table, resolver
  tools/         tool definitions: watchlist screening, client history, related entities
  agent/         agent logic: fixed pipeline, conflicts, rules, confidence
  schema/        output schema (Pydantic)
  cli.py
openspec/        specifications (current specs + proposed changes)
eval/            evaluation datasets and runners
tests/           unit tests (fast, use a small hand-built portfolio)
docs/            challenge statement, open items
```
