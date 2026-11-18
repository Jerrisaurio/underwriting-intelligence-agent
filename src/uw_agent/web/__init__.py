"""Public web research behind a provider-agnostic interface."""

from uw_agent.web.base import UnavailableResearcher, WebResearcher, build_researcher
from uw_agent.web.depth import choose_depth
from uw_agent.web.models import ResearchOutcome, ResearchRequest, Usage

__all__ = [
    "ResearchOutcome",
    "ResearchRequest",
    "UnavailableResearcher",
    "Usage",
    "WebResearcher",
    "build_researcher",
    "choose_depth",
]
