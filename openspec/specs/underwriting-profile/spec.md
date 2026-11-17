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
SHALL NOT resolve them silently.

#### Scenario: Business word contradicts industry
- **WHEN** the client is "Agroindustrias X" and its industry is "Hotelería y Turismo"
- **THEN** an INDUSTRY_NAME_MISMATCH conflict of severity medium is reported

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
- **WHEN** the profile is for HSBC México
- **THEN** BITAL appears as a related entity with relation `former_name`

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

