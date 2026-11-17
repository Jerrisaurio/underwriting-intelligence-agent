## ADDED Requirements

### Requirement: Batch command
`uw-agent batch <input> -o <out.jsonl>` SHALL accept a `.txt` file (one name per line, `#`
comments ignored) or a `.csv` with a `name` column and an optional `state` column, and SHALL write
one profile per line in input order plus `<out>.summary.json`.

#### Scenario: CSV without name column
- **WHEN** the CSV header lacks `name`
- **THEN** the command exits with code 2 and a clear message

### Requirement: Failure isolation and resume
A failure while profiling one company SHALL produce a `status: ERROR` line and SHALL NOT stop the
batch; re-running with an existing output file SHALL skip names already present unless
`--overwrite` is given.

#### Scenario: One company raises
- **WHEN** one of three companies raises an exception
- **THEN** the output has three lines, one with status ERROR, and the summary counts one error

#### Scenario: Resume
- **WHEN** the batch is re-run after an interruption
- **THEN** only the missing names are processed

### Requirement: Run summary
The summary SHALL report counts by status and by recommended action, errors, web-search calls,
tokens, total and per-lookup cost (null when prices are not configured), and latency p50/p95.

#### Scenario: Unpriced run
- **WHEN** no `UW_PRICE_*` variables are set
- **THEN** costs are null and token counts are still reported

### Requirement: Deduplication and concurrency
Identical inputs (same normalized name and state) SHALL be profiled once per run, and companies
SHALL be processed concurrently with a configurable number of workers.

#### Scenario: Duplicate names
- **WHEN** the input lists "ACME" and "Acme" (same normalized name)
- **THEN** the pipeline runs once and both output lines carry the same profile
