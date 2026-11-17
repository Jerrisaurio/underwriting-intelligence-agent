## ADDED Requirements

### Requirement: Web conflicts
The system SHALL report WATCHLIST_STATUS_VS_NEWS (high) when a resolved flag is contradicted by a
confirmed negative finding of the same risk category published after the resolution date,
INDUSTRY_WEB_MISMATCH (medium) when the web industry differs from the recorded one, and
ADVERSE_MEDIA_NOT_IN_WATCHLIST (medium) for confirmed negative sanction, fraud, litigation or
payment findings without a matching watchlist flag.

#### Scenario: Resolved flag, recent bad news
- **WHEN** a credit-risk flag was resolved in 2022 and a confirmed negative credit finding is dated 2024
- **THEN** a high WATCHLIST_STATUS_VS_NEWS conflict cites both the watchlist entry and the finding

### Requirement: Web evidence never declines
Web findings SHALL NOT produce DECLINE. Adverse media not in the watchlist SHALL produce
REFER_TO_COMPLIANCE (R2c) for sanction or fraud, and REFER_TO_SENIOR_UNDERWRITER (R5f) otherwise.

#### Scenario: Unflagged sanction news
- **WHEN** a confirmed finding reports a sanction and the watchlist has no sanction flag
- **THEN** the action is at least REFER_TO_COMPLIANCE and never DECLINE because of it

### Requirement: External evidence factor
C_external SHALL be 0.8 when research confirmed the identity, 0.5 when research ran but found no
public footprint or did not run, and 0.3 when results only described a different company.

#### Scenario: No public footprint
- **WHEN** research ran and found nothing about the company
- **THEN** C_external is 0.5 (absence is not negative evidence)
