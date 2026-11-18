## MODIFIED Requirements

### Requirement: Depth policy and budget
The system SHALL choose depth T0 (no research) when the profile was short-circuited, is invalid or
ambiguous, or research is unavailable; T2 (at most 5 searches) when risk signals exist (any
watchlist flag, credible loss ratio above 0.8, total sum insured above the portfolio p90 of client totals,
two or more disputed claims that are also at least 25% of the client's claims, or no internal match); T1 (at most 2 searches) otherwise, including
when the industry is missing or inconsistent with the name (an identity check answers that);
and SHALL record the reasons.

#### Scenario: Short-circuit skips research
- **WHEN** rule R1 fired
- **THEN** depth is T0 and no provider call is made

#### Scenario: Risk signal deepens research
- **WHEN** the client has a resolved watchlist flag
- **THEN** depth is T2

#### Scenario: Industry question stays at identity depth
- **WHEN** the only signal is a missing or name-inconsistent industry
- **THEN** depth is T1 and the reason mentions the industry check

## ADDED Requirements

### Requirement: Provider data retention
Requests to the web-research provider SHALL ask it not to store the request or response
(`store=false`), in addition to sending only the company name, state and depth.

#### Scenario: Request payload
- **WHEN** a web-research request is sent
- **THEN** it carries `store = false`
