# Underwriting Intelligence Agent

Builds a structured underwriting profile for a company from three internal databases
(portfolio, claims, watchlist) and public web sources.

> **Status:** work in progress. Implemented so far: the data layer, entity resolution and
> its evaluation. Next: tools (watchlist, portfolio, claims), web research, the profile
> schema, `profile`/`batch` commands. Deferred items are tracked in
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
uv run uw-agent resolve "Tecnologías Bajío S.A. de C.V."
uv run uw-agent resolve "Grupo Nova S.A." --state Jalisco
uv run uw-agent data-quality
```

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
  cli.py
eval/            evaluation datasets and runners
tests/           unit tests (fast, use a small hand-built portfolio)
docs/            challenge statement, open items
```
