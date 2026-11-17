"""Tools: deterministic, side-effect-free lookups over the internal databases.

Each tool takes plain inputs and returns schema models, so it can be called by the fixed
pipeline today and exposed to an LLM tool-calling layer later without changes.
"""

from uw_agent.tools.history import HistoryResult, summarize_history
from uw_agent.tools.related import RelatedEntities
from uw_agent.tools.watchlist import WatchlistScreener

__all__ = ["HistoryResult", "RelatedEntities", "WatchlistScreener", "summarize_history"]
