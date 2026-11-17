## Why

Entity resolution tells us *which* client a name refers to, but an underwriter needs the full
picture: relationship, performance, risk flags and how much to trust it. Everything that can be
answered from internal data should be answered deterministically, at zero cost, before any web or
LLM step is added. Requirements were reviewed and closed in
`docs/specs/add-internal-tools-and-schema-draft.md`.

## What Changes

- Watchlist screening tool: confirmed (ClientId) and possible (homonym candidates, name-only links)
  matches; contradiction between note and resolved status detected.
- Client history tools: portfolio summary at a reference date and claims summary with a
  credibility-aware client loss ratio.
- Related-entities lookup from a curated YAML of corporate groups and historical names.
- Underwriting profile: Pydantic schema with evidence ids on every fact, rule-based conflicts,
  recommended action (precedence matrix) and confidence formula.
- `uw-agent profile "<name>" [--state] [--as-of]` command with defined exit codes.

## Capabilities

### New Capabilities
- `watchlist-screening`: link watchlist entries to a resolved client and its homonyms.
- `client-history`: portfolio and claims summaries for one ClientId at a reference date.
- `underwriting-profile`: profile schema, conflicts, recommended action, confidence and CLI.

### Modified Capabilities
<!-- none: entity-resolution and data-layer are used as-is -->

## Impact

- New packages: `src/uw_agent/tools/`, `src/uw_agent/agent/`, `src/uw_agent/schema/`.
- New CLI command `profile`; `docs/SCHEMA.md` documents the output.
- No new dependencies. No external calls.
