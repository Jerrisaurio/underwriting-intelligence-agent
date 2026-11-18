# data-layer Specification

## Purpose

Typed, read-only access to the three internal databases (portfolio, claims, watchlist),
indexed by ClientId, plus reproducible dataset-level data-quality checks.
Implemented in `src/uw_agent/data/`.

## Requirements

### Requirement: Typed loading of the source files
The system SHALL load `portfolio_mexico.csv`, `claims.csv` and `watchlist.csv` from the directory
given by `UW_DATA_DIR` (default `data/`), decoding UTF-8 with BOM, parsing dates strictly as
`DD/MM/YYYY` and numeric columns as floats.

#### Scenario: Day-first dates
- **WHEN** a policy has `policy_start_date` "04/01/2022"
- **THEN** it is loaded as 4 January 2022, not 1 April 2022

#### Scenario: BOM in the header
- **WHEN** the first header cell starts with a UTF-8 BOM
- **THEN** the column is still recognised by its plain name

### Requirement: Fail fast on schema errors, tolerate value errors
The system SHALL raise `DataSchemaError` when a file or a required column is missing, and SHALL
convert unparseable individual values to missing values instead of failing.

#### Scenario: Missing column
- **WHEN** `watchlist.csv` lacks the `status` column
- **THEN** loading raises `DataSchemaError` naming the missing column

#### Scenario: Unparseable value
- **WHEN** a claim has `claim_date` "not-a-date"
- **THEN** loading succeeds and that value is missing (NaT)

### Requirement: ClientId-indexed access
The repository SHALL return policies, claims and watchlist rows for a ClientId without scanning
the full tables, and SHALL expose one row per ClientId with display name, state, municipality,
number of policies, industry and policy date range.

#### Scenario: Unknown ClientId
- **WHEN** policies are requested for a ClientId that does not exist
- **THEN** an empty table with the same columns is returned

### Requirement: Reproducible data-quality report
The system SHALL report dataset-level issues through `uw-agent data-quality`, including missing
industry, homonymous names, claims after the reference date, reserves kept on closed claims,
stale open claims, watchlist ClientIds absent from the portfolio, watchlist notes that contradict
a resolved status, and flags that predate the client relationship.

#### Scenario: Note contradicts resolved status
- **WHEN** a watchlist entry has status `resuelto` and the note says "Demanda civil/mercantil en curso"
- **THEN** it is counted under `WATCHLIST_NOTE_VS_STATUS`

#### Scenario: Phrase that only looks ongoing
- **WHEN** a resolved entry's note says "Sin impacto activo"
- **THEN** it is not counted as a contradiction
