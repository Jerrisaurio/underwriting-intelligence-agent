## 1. Schema

- [x] 1.1 Pydantic models for the profile (`schema/profile.py`): query, resolution, identity, relationship, claims performance, risk flags, related entities, conflicts, data gaps, assessment, evidence, trace; reserved `public_information` section
- [x] 1.2 Enums for recommended actions, conflict types, confidence levels, profile status

## 2. Tools

- [x] 2.1 `tools/watchlist.py`: confirmed / possible matches, name-only links for ClientIds absent from the portfolio, note-vs-status detection
- [x] 2.2 `tools/history.py` (portfolio part): summary at `as_of_date` (active policies, premium, sum insured, coverage mix, date range)
- [x] 2.3 `tools/history.py` (claims part): frequency, incurred, status counts, open-claim age, client loss ratio with credibility, by-year breakdown, claims after `as_of` excluded
- [x] 2.4 `tools/related.py` + `related_entities.yaml`
- [x] 2.5 Unit tests for each tool

## 3. Agent logic

- [x] 3.1 `agent/conflicts.py`: conflict rules from the draft
- [x] 3.2 `agent/rules.py`: recommended action with precedence and rule ids
- [x] 3.3 `agent/confidence.py`: confidence formula and levels
- [x] 3.4 `agent/pipeline.py`: fixed orchestration, AMBIGUOUS / NOT_FOUND / INVALID paths
- [x] 3.5 Unit tests for rules, confidence and pipeline paths

## 4. CLI and docs

- [x] 4.1 `uw-agent profile` with `--state`, `--as-of`, exit codes 0/1/2
- [x] 4.2 `docs/SCHEMA.md`: every field, confidence calculation, possible actions
- [x] 4.3 README usage update
