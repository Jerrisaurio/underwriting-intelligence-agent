## Context

The audit mapped every sentence of the challenge to the implementation. Gaps closed here are
listed in `proposal.md`. Constraints that stay in force: internal data is authoritative, the action
and confidence are rule-based, no dataset content in the repository, no new runtime dependency.

## Goals / Non-Goals

**Goals:**
- Detect the challenge's literal coverage-vs-web industry conflict without flooding profiles.
- Make every conflict reasoned (authority, implication, verification), deterministically.
- Spend T2 searches only on risk signals.
- Trace where the industry value comes from.
- A reviewer can run the README examples' workflow and see CI pass.

**Non-Goals:**
- An LLM writing the reasoning (it must stay reproducible and testable).
- Inferring industry from coverage for internal-only profiles (the data shows no relation; it
  would be noise).

## Decisions

- **Coverage → industry only for unambiguous coverages with majority premium.** Agrícola and
  Ingeniería are bought by specific businesses; fleet, liability, fire, cargo and miscellaneous
  by any. Majority premium (> 50%) avoids judging a client by a side policy. Alternative
  considered: any coverage share or all coverage types → rejected as noise (the internal data has
  no coverage/industry relation).
- **Reasoning from a per-type template table** in `agent/conflicts.py`, filled with the
  conflict's facts. Alternative: free-form LLM text → rejected (non-deterministic, untestable,
  and the web layer may be unavailable).
- **The web fills, never corrects.** `industry_source = "web"` only when the portfolio has no
  industry; when both exist the internal value stays and INDUSTRY_WEB_MISMATCH records the
  disagreement. INDUSTRY_MISSING is not raised when the web filled the gap (the data gap is then
  answered, with its source).
- **Industry issues → T1.** T1 already returns the identity and the industry from a closed list;
  T2 adds adverse-media searches that an industry question does not need. Measured before the
  change: 79% of T2 lookups were triggered only by industry.
- **CI with the locked environment** (`uv sync --locked`), Python from `.python-version`; no
  secrets and no data needed because tests use fictitious fixtures.

## Risks / Trade-offs

- [Coverage rule misses mixed clients] → intentional: only clear cases are flagged; documented.
- [Template reasoning reads repetitive] → accepted: consistency and auditability over prose.
- [Fewer T2 lookups could miss adverse media for clients whose only signal is industry] → T1
  still searches the company; any confirmed adverse finding still raises
  ADVERSE_MEDIA_NOT_IN_WATCHLIST.
- [CI action versions drift] → pinned major versions; failures are visible on the next push.

## Migration Plan

Schema gains `Conflict.reasoning`, `CompanyIdentity.industry_source` and a new conflict type;
additive, `schema_version` moves to 1.1. No data migration.

## Open Questions

None: decisions confirmed by the user in the requirements review.
