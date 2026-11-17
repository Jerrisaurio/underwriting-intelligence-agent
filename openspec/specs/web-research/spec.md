# web-research Specification

## Purpose
Provider-agnostic public web research with verified citations, depth calibration, budgets,
failure isolation and caching. Implemented in `src/uw_agent/web/` and `src/uw_agent/infra/`.

## Requirements
### Requirement: Provider-agnostic research
The system SHALL perform public research through a `WebResearcher` interface, with OpenAI as the
implementation, and SHALL send only the company name, state and depth to the provider.

#### Scenario: No credentials
- **WHEN** `OPENAI_API_KEY` or `UW_OPENAI_MODEL` is not set
- **THEN** the profile is produced from internal data with `public_information.status = "unavailable"` and exit code 0

### Requirement: Depth policy and budget
The system SHALL choose depth T0 (no research) when the profile was short-circuited, is invalid or
ambiguous, or research is unavailable; T2 (at most 5 searches) when risk signals exist (any
watchlist flag, credible loss ratio above 0.8, total sum insured above the portfolio p90 of client totals,
industry missing or mismatched, two or more disputed claims, or no internal match); T1 (at most 2
searches) otherwise; and SHALL record the reasons.

#### Scenario: Short-circuit skips research
- **WHEN** rule R1 fired
- **THEN** depth is T0 and no provider call is made

#### Scenario: Risk signal deepens research
- **WHEN** the client has a resolved watchlist flag
- **THEN** depth is T2

### Requirement: Verified, attributable findings
Every kept finding SHALL cite a URL that appears among the sources returned by the search tool;
findings classified as about a different company SHALL be dropped; both kinds of drops SHALL be
counted in the profile.

#### Scenario: Hallucinated URL
- **WHEN** the model returns a finding whose URL is not among the returned sources
- **THEN** the finding is dropped and `dropped_unverified` is incremented

#### Scenario: Homonymous company on the web
- **WHEN** a finding is classified `different_company`
- **THEN** it is dropped and `dropped_other_entity` is incremented

### Requirement: Failure isolation
Provider errors (timeout, rate limit, server error, refusal, unparsable output) SHALL NOT fail the
profile: research status becomes `failed` with a reason and the internal profile is kept.

#### Scenario: Timeout
- **WHEN** the provider times out after retries
- **THEN** `public_information.status = "failed"` and the recommended action is computed from internal data

### Requirement: Cache
Research results SHALL be cached by provider, model, prompt version, name, state and depth with a
configurable TTL; a corrupt cache SHALL be bypassed with a warning.

#### Scenario: Repeated lookup
- **WHEN** the same company is profiled twice within the TTL
- **THEN** the second profile reuses the cached research and reports a cache hit and zero cost

