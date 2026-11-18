## ADDED Requirements

### Requirement: Active flag versus public resolution
The system SHALL report ACTIVE_FLAG_VS_NEWS (medium) when a confirmed watchlist flag is active and a
confirmed public finding of the same risk category has a positive or neutral stance (reporting a
resolution). The internal flag SHALL remain in force for the rules.

#### Scenario: Active litigation, public news of settlement
- **WHEN** a confirmed active litigation flag exists and a confirmed positive litigation finding is kept
- **THEN** an ACTIVE_FLAG_VS_NEWS conflict cites both, and the litigation rule still fires

### Requirement: Industry decisions need verified identity
The web industry SHALL fill a missing industry, and INDUSTRY_WEB_MISMATCH or
COVERAGE_VS_WEB_INDUSTRY SHALL be raised, only when the public identity is verified.

#### Scenario: Unverified industry
- **WHEN** research returns an industry but the identity is not verified
- **THEN** the industry is not filled and no industry conflict is raised
