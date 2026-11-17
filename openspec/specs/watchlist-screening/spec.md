# watchlist-screening Specification

## Purpose
Link watchlist entries to the profiled client (confirmed) and to plausible homonyms or
name-only matches (possible), never by fuzzy matching. Implemented in
`src/uw_agent/tools/watchlist.py`.

## Requirements
### Requirement: Mandatory watchlist screening
The system SHALL screen the watchlist for every profile request that reaches a resolution with
candidates, regardless of any other finding.

#### Scenario: Flag on the chosen client
- **WHEN** the resolved ClientId has a watchlist entry
- **THEN** the entry is reported with `link: confirmed`

### Requirement: Possible matches on homonyms
The system SHALL report, as `link: possible`, watchlist entries whose ClientId is another
candidate inside the resolver's ambiguity window, and SHALL NOT use fuzzy name matching against
the watchlist.

#### Scenario: Flag on a non-dominant homonym
- **WHEN** a name resolves with ambiguity to client A and homonym B has an active flag
- **THEN** B's flag appears with `link: possible` and the candidate ClientId B

### Requirement: Name-only links
The system SHALL link watchlist entries whose ClientId does not exist in the portfolio when their
normalized name (core and legal-form family) or a curated alias equals one of the client's
recorded spellings, and SHALL mark them `link: possible` with link method `name`.

#### Scenario: Watchlist ClientId absent from the portfolio
- **WHEN** watchlist entry "PEMEX" has ClientId FAMS000002A1 and the resolved client has spelling "PEMEX"
- **THEN** the entry is reported with `link: possible` and `link_method: name`

### Requirement: Note versus status
The system SHALL flag resolved entries whose note describes an ongoing situation.

#### Scenario: Resolved entry still described as ongoing
- **WHEN** an entry has status `resuelto` and note "Prima vencida sin liquidar"
- **THEN** the entry carries `note_contradicts_status = true`

