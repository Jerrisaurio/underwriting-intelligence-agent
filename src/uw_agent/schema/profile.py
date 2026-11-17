"""Underwriting profile schema (documented field by field in docs/SCHEMA.md).

Conventions:
- Field names in English; values copied from the source data stay verbatim (Spanish).
- Text written by the agent (descriptions, explanations, summary) is in Spanish.
- ``evidence`` lists hold ids of the source rows a fact was derived from:
  ``portfolio:<policy_id>``, ``claims:<claim_id>``, ``watchlist:<watchlist_id>``.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from uw_agent.resolution.models import ResolutionResult

SCHEMA_VERSION = "1.0"


class ProfileStatus(StrEnum):
    COMPLETE = "COMPLETE"  # a single client was profiled (possibly with ambiguity flagged)
    AMBIGUOUS = "AMBIGUOUS"  # several clients match; candidates listed, no profile
    NOT_FOUND = "NOT_FOUND"  # no internal match
    INVALID_INPUT = "INVALID_INPUT"
    ERROR = "ERROR"  # unexpected failure while building this profile (batch mode)


class RecommendedAction(StrEnum):
    DECLINE = "DECLINE"
    REFER_TO_COMPLIANCE = "REFER_TO_COMPLIANCE"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"
    REFER_TO_SENIOR_UNDERWRITER = "REFER_TO_SENIOR_UNDERWRITER"
    PROCEED_WITH_CONDITIONS = "PROCEED_WITH_CONDITIONS"
    PROCEED_STANDARD = "PROCEED_STANDARD"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ConflictType(StrEnum):
    ENTITY_AMBIGUITY = "ENTITY_AMBIGUITY"
    WATCHLIST_NOTE_VS_STATUS = "WATCHLIST_NOTE_VS_STATUS"
    FLAG_PREDATES_RELATIONSHIP = "FLAG_PREDATES_RELATIONSHIP"
    WATCHLIST_LINKED_BY_NAME_ONLY = "WATCHLIST_LINKED_BY_NAME_ONLY"
    INDUSTRY_MISSING = "INDUSTRY_MISSING"
    INDUSTRY_NAME_MISMATCH = "INDUSTRY_NAME_MISMATCH"
    DATA_ANOMALY = "DATA_ANOMALY"


class ConfidenceLevel(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class WatchlistLink(StrEnum):
    CONFIRMED = "confirmed"  # same ClientId as the profiled client
    POSSIBLE = "possible"  # homonym candidate or name-only link: needs human review


class LinkMethod(StrEnum):
    CLIENT_ID = "client_id"
    HOMONYM_CANDIDATE = "homonym_candidate"
    NAME = "name"


class Credibility(StrEnum):
    CREDIBLE = "credible"
    LOW = "low"


# --------------------------------------------------------------------------- sections


class QueryInfo(BaseModel):
    input_name: str
    state_hint: str | None = None
    as_of_date: date
    generated_at: datetime


class CompanyIdentity(BaseModel):
    client_id: str
    legal_name: str = Field(description="Most frequent spelling of the client in the portfolio")
    name_variants: list[str]
    state: str
    municipality: str
    industry: str | None = Field(description="Portfolio industry; null when never recorded")
    evidence: list[str]


class CoverageLine(BaseModel):
    coverage_type: str
    n_policies: int
    n_active: int
    premium_mxn: float
    sum_insured_mxn: float


class Relationship(BaseModel):
    n_policies: int = Field(description="Policies started on or before as_of_date")
    n_active_policies: int = Field(description="Policies with start <= as_of_date < end")
    total_premium_mxn: float
    total_sum_insured_mxn: float
    active_premium_mxn: float
    active_sum_insured_mxn: float
    first_policy_start: date | None
    last_policy_end: date | None
    coverage_mix: list[CoverageLine]
    evidence: list[str]


class YearLine(BaseModel):
    policy_start_year: int
    n_policies: int
    premium_mxn: float
    n_claims: int
    incurred_mxn: float
    loss_ratio: float


class ClaimsPerformance(BaseModel):
    n_claims: int
    n_excluded_after_as_of: int
    incurred_mxn: float
    reserved_registered_mxn: float = Field(
        description="Sum of reserved_mxn as recorded. Closed claims keep their reserve in the "
        "source data, so this is NOT outstanding exposure."
    )
    by_status: dict[str, int]
    oldest_open_claim_date: date | None
    oldest_open_claim_age_days: int | None
    client_loss_ratio: float = Field(description="Σ incurred / Σ written premium")
    credibility: Credibility
    by_year: list[YearLine]
    top_claim_types: dict[str, int]
    evidence: list[str]


class RiskFlag(BaseModel):
    watchlist_id: str
    watchlist_client_id: str
    watchlist_client_name: str
    flag_type: str
    severity: str
    status: str
    flag_date: date | None
    resolved_date: date | None
    notes: str
    link: WatchlistLink
    link_method: LinkMethod
    linked_client_id: str = Field(description="Portfolio ClientId this flag was linked to")
    note_contradicts_status: bool
    predates_relationship: bool | None
    evidence: list[str]

    @property
    def is_active(self) -> bool:
        return self.status == "activo"


class RelatedEntity(BaseModel):
    name: str
    relation: str  # same_group | former_name | subsidiary
    group: str
    client_ids: list[str] = Field(description="Portfolio ClientIds of this entity, if any")
    note: str | None = None


class PublicFinding(BaseModel):
    """Reserved for the web-research change."""

    id: str
    claim: str
    url: str
    published_date: date | None = None
    category: str
    stance: str


class WebResearch(BaseModel):
    status: str = "not_run"
    reason: str | None = None
    depth: str = "T0"
    findings: list[PublicFinding] = Field(default_factory=list)


class Conflict(BaseModel):
    id: str
    type: ConflictType
    severity: Severity
    description: str
    sources: list[str]
    resolution: str = "unresolved"


class TriggeredRule(BaseModel):
    rule_id: str
    action: RecommendedAction
    explanation: str


class ConfidenceBreakdown(BaseModel):
    overall: float = Field(ge=0, le=1)
    level: ConfidenceLevel
    entity: float
    internal: float
    external: float
    conflict_penalty: float
    capped: bool = Field(description="True when the weak-entity cap (0.4) was applied")


class Assessment(BaseModel):
    recommended_action: RecommendedAction
    triggered_rules: list[TriggeredRule]
    confidence: ConfidenceBreakdown
    summary: str


class CandidateSummary(BaseModel):
    client_id: str
    display_name: str
    state: str
    n_policies: int
    score: float
    active_flags: list[str] = Field(description="'flag_type/severity' of active watchlist entries")


class TraceStep(BaseModel):
    step: str
    duration_ms: float
    detail: str


class Trace(BaseModel):
    steps: list[TraceStep] = Field(default_factory=list)
    short_circuit: str | None = None
    llm_calls: int = 0
    cost_usd: float = 0.0


class UnderwritingProfile(BaseModel):
    schema_version: str = SCHEMA_VERSION
    status: ProfileStatus
    query: QueryInfo
    entity_resolution: ResolutionResult | None = None
    candidates_summary: list[CandidateSummary] = Field(default_factory=list)
    company_identity: CompanyIdentity | None = None
    relationship: Relationship | None = None
    claims_performance: ClaimsPerformance | None = None
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    related_entities: list[RelatedEntity] = Field(default_factory=list)
    public_information: WebResearch = Field(default_factory=WebResearch)
    conflicts: list[Conflict] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    assessment: Assessment
    trace: Trace = Field(default_factory=Trace)
