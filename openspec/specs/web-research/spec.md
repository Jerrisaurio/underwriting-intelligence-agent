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

### Requirement: Provider data retention
Requests to the web-research provider SHALL ask it not to store the request or response
(`store=false`), in addition to sending only the company name, state and depth.

#### Scenario: Request payload
- **WHEN** a web-research request is sent
- **THEN** it carries `store = false`

### Requirement: Verified public identity
The public identity returned by research SHALL be treated as verified only when at least one kept
finding has `entity_match = confirmed` and a URL among the sources returned by the search tool.
Otherwise `found_publicly` SHALL be reported as false with `identity_verified = false`, and the web
industry SHALL be discarded.

#### Scenario: Claimed but unsupported identity
- **WHEN** the model returns `found_publicly = true` and an industry but no confirmed verified finding
- **THEN** the profile reports `found_publicly = false`, `identity_verified = false` and no web industry

#### Scenario: Supported identity
- **WHEN** at least one confirmed finding with a verified URL is kept
- **THEN** `identity_verified = true` and the web industry is kept

### Requirement: Category coverage at T2
At depth T2 the research instructions SHALL ask for one search per risk category (sanctions, fraud,
litigation, credit, payments) within the T2 budget.

#### Scenario: Deep research request
- **WHEN** a T2 request is built
- **THEN** its input names the five risk categories to search and `max_tool_calls` is 5

