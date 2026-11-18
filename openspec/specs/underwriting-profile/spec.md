# underwriting-profile Specification

## Purpose
Structured, traceable underwriting profile: fixed source order, explicit conflicts, rule-based
recommended action and confidence, CLI contract. Implemented in `src/uw_agent/agent/`,
`src/uw_agent/schema/` and `src/uw_agent/cli.py`; documented in `docs/SCHEMA.md`.
## Requirements
### Requirement: Structured, traceable profile
The system SHALL emit a profile that validates against a documented schema, and every reported
fact SHALL reference the evidence ids it was derived from.

#### Scenario: Traceable premium
- **WHEN** the profile reports total premium
- **THEN** the evidence list contains the `portfolio:<policy_id>` ids that were summed

### Requirement: Fixed source order
The system SHALL run, in order: entity resolution, watchlist screening, portfolio summary, claims
summary, related entities, conflict detection, recommended action and confidence. Watchlist
screening SHALL NOT be skippable.

#### Scenario: Critical sanction short-circuit
- **WHEN** the confirmed client has an active critical `sancion_regulatoria`
- **THEN** the action is DECLINE, internal summaries are still present, and the trace records the short-circuit

### Requirement: Recommended action by precedence
The system SHALL choose exactly one action from DECLINE, REFER_TO_COMPLIANCE, NEEDS_CLARIFICATION,
INSUFFICIENT_INFORMATION, REFER_TO_SENIOR_UNDERWRITER, PROCEED_WITH_CONDITIONS, PROCEED_STANDARD,
using the precedence and matrix in the approved draft, and SHALL list every triggered rule with an
id and a Spanish explanation. `possible` flags SHALL never produce DECLINE.

#### Scenario: Possible critical sanction
- **WHEN** only a homonym candidate has an active critical sanction
- **THEN** the action is at most REFER_TO_COMPLIANCE

#### Scenario: Resolved flag with contradicting note
- **WHEN** a confirmed flag is `resuelto` but its note says the case is ongoing
- **THEN** a high-severity WATCHLIST_NOTE_VS_STATUS conflict is reported and the action is at least REFER_TO_SENIOR_UNDERWRITER

### Requirement: Explicit conflicts
The system SHALL report conflicts ENTITY_AMBIGUITY, WATCHLIST_NOTE_VS_STATUS,
FLAG_PREDATES_RELATIONSHIP, WATCHLIST_LINKED_BY_NAME_ONLY, INDUSTRY_MISSING,
INDUSTRY_NAME_MISMATCH and DATA_ANOMALY with severity, sources and a Spanish description, and
SHALL NOT resolve them silently. Every conflict SHALL also carry a `reasoning` text in Spanish that
states which source is more authoritative and why, what the conflict implies for underwriting,
and what to verify.

#### Scenario: Business word contradicts industry
- **WHEN** the client is "Agroindustrias X" and its industry is "Hotelería y Turismo"
- **THEN** an INDUSTRY_NAME_MISMATCH conflict of severity medium is reported

#### Scenario: Conflict is reasoned, not only described
- **WHEN** any conflict is reported
- **THEN** its `reasoning` is non-empty and names the authoritative source, the implication and a verification step

### Requirement: Rule-based confidence
The system SHALL compute confidence as C_entity × (0.7·C_internal + 0.3·C_external) minus conflict
penalties, capped at 0.4 when C_entity < 0.6, and SHALL report the components and the level
(HIGH ≥ 0.75, MEDIUM ≥ 0.5, LOW otherwise).

#### Scenario: Weak entity match caps confidence
- **WHEN** entity confidence is 0.5
- **THEN** overall confidence is at most 0.4 and the level is LOW

### Requirement: Related entities
The system SHALL list related entities from a curated table (corporate groups, historical names)
without using them in action rules.

#### Scenario: Historical name
- **WHEN** the curated table records "Empresa Nueva" with former name "Empresa Antigua" and the profile is for Empresa Nueva
- **THEN** Empresa Antigua appears as a related entity with relation `former_name`

### Requirement: Non-resolved outcomes
The system SHALL return status AMBIGUOUS with candidates, their mini-summaries and action
NEEDS_CLARIFICATION; status NOT_FOUND with action INSUFFICIENT_INFORMATION; and status
INVALID_INPUT for invalid names.

#### Scenario: Ambiguous name
- **WHEN** the name matches several clients without a dominant one
- **THEN** each candidate shows state, number of policies and active flags

### Requirement: CLI exit codes
`uw-agent profile` SHALL exit 0 when a profile is produced (any status), 2 on invalid input or an
invalid `--as-of`, and 1 on system failure such as missing data.

#### Scenario: Invalid name
- **WHEN** `uw-agent profile ""` runs
- **THEN** the JSON has status INVALID_INPUT and the exit code is 2

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

### Requirement: Coverage versus web industry
The system SHALL report COVERAGE_VS_WEB_INDUSTRY (medium) when an unambiguous coverage holds more
than half of the client's written premium and the industry found on the web is not consistent
with it. Unambiguous coverages are Agrícola (Agricultura, Alimentos y Bebidas) and Ingeniería
(Construcción, Inmobiliaria, Minería, Manufactura). Coverages any business buys (fleet, liability,
fire, miscellaneous, cargo) SHALL NOT imply an industry.

#### Scenario: Agricultural coverage, technology company on the web
- **WHEN** 80% of the client's premium is Agrícola and the web industry is "Tecnología"
- **THEN** a COVERAGE_VS_WEB_INDUSTRY conflict cites the client and the web findings

#### Scenario: Generic coverage implies nothing
- **WHEN** 100% of the premium is Flotilla Vehicular and the web industry is "Tecnología"
- **THEN** no COVERAGE_VS_WEB_INDUSTRY conflict is reported

#### Scenario: No web industry
- **WHEN** web research did not run or returned no industry
- **THEN** no COVERAGE_VS_WEB_INDUSTRY conflict is reported

### Requirement: Industry source
The profile SHALL state the source of `company_identity.industry` in `industry_source`: `portfolio`
when recorded internally (kept even if the web disagrees, with a conflict), `web` when the
portfolio has none and research found one, null otherwise. The web SHALL NOT override a recorded
industry.

#### Scenario: Web fills a gap
- **WHEN** the portfolio has no industry and the web identity industry is "Minería"
- **THEN** industry is "Minería" with `industry_source = "web"` and no INDUSTRY_MISSING conflict

#### Scenario: Web disagrees with the portfolio
- **WHEN** the portfolio says "Construcción" and the web says "Minería"
- **THEN** industry stays "Construcción" with `industry_source = "portfolio"` and INDUSTRY_WEB_MISMATCH is reported

