## ADDED Requirements

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
