"""Web-research interface and factory.

The pipeline depends only on ``WebResearcher``; providers are interchangeable. OpenAI is the
implementation shipped (the stack used by the hiring team); adding another provider means one
new class and one branch in ``build_researcher``.
"""

from __future__ import annotations

import logging
from typing import Protocol

from uw_agent.config import Settings
from uw_agent.schema.profile import ResearchStatus
from uw_agent.web.models import ResearchOutcome, ResearchRequest

log = logging.getLogger(__name__)


class WebResearcher(Protocol):
    provider: str
    model: str | None
    available: bool

    def research(self, request: ResearchRequest) -> ResearchOutcome: ...


class UnavailableResearcher:
    """Used when no credentials/model are configured: the agent runs on internal data only."""

    provider = "none"
    model = None
    available = False

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def research(self, request: ResearchRequest) -> ResearchOutcome:
        return ResearchOutcome(status=ResearchStatus.UNAVAILABLE, reason=self.reason)


def build_researcher(settings: Settings, use_cache: bool = True) -> WebResearcher:
    if not settings.openai_api_key or not settings.openai_model:
        missing = [
            n
            for n, v in [
                ("OPENAI_API_KEY", settings.openai_api_key),
                ("UW_OPENAI_MODEL", settings.openai_model),
            ]
            if not v
        ]
        return UnavailableResearcher(f"Investigación web desactivada: falta {', '.join(missing)}")

    from uw_agent.web.openai_researcher import OpenAIWebResearcher  # imports the SDK lazily

    researcher: WebResearcher = OpenAIWebResearcher(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        timeout=settings.request_timeout_s,
    )
    if use_cache:
        from uw_agent.infra.cache import CachedResearcher

        researcher = CachedResearcher(
            researcher, settings.cache_dir / "web_research.sqlite", settings.cache_ttl_days
        )
    return researcher
