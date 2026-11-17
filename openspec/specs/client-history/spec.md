# client-history Specification

## Purpose
Portfolio and claims summaries for one ClientId at a reference date, including a
credibility-aware client loss ratio. Implemented in `src/uw_agent/tools/history.py`.

## Requirements
### Requirement: Portfolio summary at a reference date
The system SHALL summarise a ClientId's policies at `as_of_date`: total and active policies
(start ≤ as_of < end), total and active premium and sum insured, coverage mix, first policy start
and last policy end, each with evidence ids.

#### Scenario: Expired relationship
- **WHEN** all of a client's policies ended before `as_of_date`
- **THEN** active policies is 0 and the profile lists a data gap "sin pólizas vigentes"

### Requirement: Claims summary and client loss ratio
The system SHALL compute the client loss ratio as Σ incurred / Σ written premium over the client's
policies, a breakdown by policy start year, counts by status, and the age of the oldest open or
disputed claim. Claims dated after `as_of_date` SHALL be excluded and reported.

#### Scenario: Client without claims
- **WHEN** a client has policies and no claims
- **THEN** the loss ratio is 0.0 with its credibility, never missing

#### Scenario: Claim after the reference date
- **WHEN** a claim is dated after `as_of_date`
- **THEN** it is excluded from all metrics and reported as a data anomaly

### Requirement: Loss-ratio credibility
The system SHALL mark the loss ratio `credible` only with at least 3 policies and at least 2 years
between the first policy start and `as_of_date`; otherwise `low`. A `low` loss ratio SHALL NOT
trigger action rules.

#### Scenario: Thin history
- **WHEN** a client has 1 policy with a loss ratio of 1.6
- **THEN** credibility is `low` and no loss-ratio rule is triggered

