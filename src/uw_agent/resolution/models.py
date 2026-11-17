"""Result types for entity resolution."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ResolutionOutcome(StrEnum):
    RESOLVED = "RESOLVED"
    """One ClientId, no close alternative."""
    RESOLVED_WITH_AMBIGUITY = "RESOLVED_WITH_AMBIGUITY"
    """A clear leader exists, but other ClientIds match closely (typically homonyms in
    other states). The profile is built for the leader; alternatives are listed."""
    AMBIGUOUS = "AMBIGUOUS"
    """Several ClientIds match and none dominates: the agent must not guess."""
    NOT_FOUND = "NOT_FOUND"
    INVALID_INPUT = "INVALID_INPUT"


class MatchType(StrEnum):
    EXACT = "exact"  # same normalized core
    COMPACT = "compact"  # same core ignoring spaces ("VivaAerobus")
    # every query word appears in the candidate name ("Bajío" -> "Tecnologías Bajío")
    PARTIAL = "partial"
    FUZZY = "fuzzy"  # typos / word order
    ALIAS = "alias"  # curated alias table


class Candidate(BaseModel):
    client_id: str
    display_name: str
    state: str
    municipality: str
    n_policies: int
    score: float = Field(description="Name similarity in [0, 1] after the legal-form adjustment")
    match_type: MatchType
    matched_variant: str = Field(description="The portfolio spelling that produced the score")
    legal_form_match: bool | None = Field(
        description="True or False when both query and candidate carry a legal form; None otherwise"
    )


class ResolutionResult(BaseModel):
    query: str
    state_hint: str | None = None
    normalized_core: str
    normalized_legal_family: str | None
    outcome: ResolutionOutcome
    client_id: str | None = None
    entity_confidence: float = Field(ge=0, le=1)
    dominance: float | None = Field(
        default=None,
        description="Share of policies held by the leader among the tied candidates",
    )
    margin_to_next: float | None = None
    candidates: list[Candidate] = Field(default_factory=list)
    n_candidates_total: int = Field(
        default=0, description="Candidates above the score threshold; only the top ones are listed"
    )
    notes: list[str] = Field(default_factory=list)
