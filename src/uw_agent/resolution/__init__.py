"""Entity resolution: free-text company name -> portfolio ClientId."""

from uw_agent.resolution.models import Candidate, MatchType, ResolutionOutcome, ResolutionResult
from uw_agent.resolution.normalize import NormalizedName, normalize_name
from uw_agent.resolution.resolver import EntityResolver, ResolverConfig

__all__ = [
    "Candidate",
    "EntityResolver",
    "MatchType",
    "NormalizedName",
    "ResolutionOutcome",
    "ResolutionResult",
    "ResolverConfig",
    "normalize_name",
]
