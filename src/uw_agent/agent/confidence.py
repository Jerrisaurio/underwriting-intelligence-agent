"""Rule-based confidence (never self-reported by an LLM).

overall = C_entity × (W_INTERNAL·C_internal + W_EXTERNAL·C_external) − Σ conflict penalties

- C_entity: the resolver's entity confidence.
- C_internal: depth of internal evidence (history length, credible loss ratio, industry known,
  active relationship).
- C_external: 0.5 = neutral until web research exists; absence of web evidence must not be
  read as negative evidence.
- ENTITY_AMBIGUITY conflicts carry no penalty: C_entity already reflects them.
- If C_entity < ENTITY_CAP_THRESHOLD, overall is capped: a rich profile of possibly the wrong
  company must not look trustworthy.

The weights are a reasoned starting point, not fitted: the data has no ground truth for
underwriting outcomes to calibrate against (stated in the README).
"""

from __future__ import annotations

from uw_agent.schema.profile import (
    ClaimsPerformance,
    ConfidenceBreakdown,
    ConfidenceLevel,
    Conflict,
    ConflictType,
    Credibility,
    Relationship,
    ResearchStatus,
    Severity,
    WebResearch,
)

W_INTERNAL = 0.7
W_EXTERNAL = 0.3
NEUTRAL_EXTERNAL = 0.5
PENALTY = {Severity.HIGH: 0.15, Severity.MEDIUM: 0.07, Severity.LOW: 0.0}
ENTITY_CAP_THRESHOLD = 0.6
ENTITY_CAP = 0.4
HIGH_THRESHOLD = 0.75
MEDIUM_THRESHOLD = 0.5
FULL_HISTORY_YEARS = 4  # the portfolio spans 4 years of policy starts


def level_for(score: float) -> ConfidenceLevel:
    if score >= HIGH_THRESHOLD:
        return ConfidenceLevel.HIGH
    if score >= MEDIUM_THRESHOLD:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.LOW


def internal_evidence(
    relationship: Relationship | None,
    claims: ClaimsPerformance | None,
    industry_known: bool,
    history_years: float,
) -> float:
    if relationship is None or claims is None:
        return 0.0
    return round(
        0.4 * min(history_years / FULL_HISTORY_YEARS, 1.0)
        + 0.3 * (claims.credibility is Credibility.CREDIBLE)
        + 0.15 * industry_known
        + 0.15 * (relationship.n_active_policies > 0),
        4,
    )


def external_evidence(web: WebResearch | None) -> float:
    """0.8 identity confirmed on the web; 0.3 only a different company found; else neutral."""
    if web is None or web.status is not ResearchStatus.DONE:
        return NEUTRAL_EXTERNAL
    if any(f.entity_match == "confirmed" for f in web.findings):
        return 0.8
    found = web.identity is not None and web.identity.found_publicly
    if not found and not web.findings and web.dropped_other_entity > 0:
        return 0.3
    return NEUTRAL_EXTERNAL


def compute_confidence(
    entity: float,
    internal: float,
    conflicts: list[Conflict],
    external: float = NEUTRAL_EXTERNAL,
) -> ConfidenceBreakdown:
    # ENTITY_AMBIGUITY is already priced into C_entity (dominance factor); penalising it again
    # would count the same uncertainty twice.
    penalty = round(
        sum(PENALTY[c.severity] for c in conflicts if c.type is not ConflictType.ENTITY_AMBIGUITY),
        4,
    )
    raw = entity * (W_INTERNAL * internal + W_EXTERNAL * external) - penalty
    overall = min(max(raw, 0.0), 1.0)
    capped = entity < ENTITY_CAP_THRESHOLD and overall > ENTITY_CAP
    if capped:
        overall = ENTITY_CAP
    overall = round(overall, 4)
    return ConfidenceBreakdown(
        overall=overall,
        level=level_for(overall),
        entity=round(entity, 4),
        internal=internal,
        external=external,
        conflict_penalty=penalty,
        capped=capped,
    )
