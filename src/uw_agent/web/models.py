"""Data types of the web-research step.

``LLM*`` models are the structured output requested from the provider. Every field is
required (nullable where optional) because strict JSON-schema output does not allow defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

from uw_agent.schema.profile import PublicFinding, PublicIdentity, ResearchStatus

Depth = Literal["T0", "T1", "T2"]
SEARCH_BUDGET: dict[str, int] = {"T1": 2, "T2": 5}

RiskCategory = Literal[
    "identity", "sanction", "fraud", "litigation", "credit", "payment", "operations", "other"
]


class LLMFinding(BaseModel):
    claim: str
    url: str
    source_title: str | None
    published_date: str | None  # YYYY-MM-DD; validated by us, not trusted
    risk_category: RiskCategory
    stance: Literal["negative", "neutral", "positive"]
    entity_match: Literal["confirmed", "uncertain", "different_company"]


class LLMIdentity(BaseModel):
    found_publicly: bool
    description: str | None
    industry: str | None
    state: str | None


class LLMResearch(BaseModel):
    identity: LLMIdentity
    findings: list[LLMFinding]


@dataclass(frozen=True)
class ResearchRequest:
    name: str
    state: str | None
    depth: Depth
    industries: tuple[str, ...]  # closed list the model must choose the industry from


@dataclass
class Usage:
    llm_calls: int = 0
    web_search_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class ResearchOutcome:
    status: ResearchStatus
    reason: str | None = None
    identity: PublicIdentity | None = None
    findings: list[PublicFinding] = field(default_factory=list)
    dropped_unverified: int = 0
    dropped_other_entity: int = 0
    usage: Usage = field(default_factory=Usage)
    provider: str | None = None
    model: str | None = None
    cache_hit: bool = False
