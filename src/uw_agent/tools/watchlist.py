"""Watchlist screening.

Three ways a watchlist entry can attach to a profile:

- ``confirmed`` / ``client_id``: same ClientId as the profiled client.
- ``possible`` / ``homonym_candidate``: the entry belongs to another ClientId that the resolver
  could not rule out (inside its ambiguity window). Screening *all* plausible candidates means a
  flag is never lost just because the resolver picked the dominant homonym.
- ``possible`` / ``name``: the watchlist ClientId does not exist in the portfolio (some
  entries), so the only link is the name. Linked when the normalized name (core + legal-form
  family) equals one of the client's recorded spellings, or a curated alias points to the client.

There is deliberately no fuzzy matching against the watchlist: attaching a sanction to the
wrong company is worse than asking a human to review a "possible" link.
"""

from __future__ import annotations

import pandas as pd

from uw_agent.data.quality import watchlist_note_contradicts_status
from uw_agent.data.repository import DataRepository
from uw_agent.resolution import EntityResolver, NormalizedName, ResolutionResult, normalize_name
from uw_agent.schema.profile import LinkMethod, RiskFlag, WatchlistLink


def _date(value) -> pd.Timestamp | None:
    return None if pd.isna(value) else value.date()


def _same_name(a: NormalizedName, b: NormalizedName) -> bool:
    if a.core != b.core:
        return False
    # A missing legal form on either side is not a contradiction ("ACME" vs "ACME S.A.").
    return a.legal_family is None or b.legal_family is None or a.legal_family == b.legal_family


class WatchlistScreener:
    def __init__(self, repo: DataRepository, resolver: EntityResolver) -> None:
        self._repo = repo
        self._resolver = resolver
        w = repo.watchlist
        # Entries that can only be linked by name: their ClientId is not in the portfolio.
        orphan = w[~w["ClientId"].isin(repo.clients.index)]
        self._orphans = [(row, normalize_name(row.client_name)) for row in orphan.itertuples()]

    def screen(self, resolution: ResolutionResult) -> list[RiskFlag]:
        window = self._resolver.ambiguity_window(resolution)
        chosen = resolution.client_id
        flags: list[RiskFlag] = []
        seen: set[str] = set()

        def add(row, link, method, linked_client_id):
            if row.watchlist_id in seen:
                return
            seen.add(row.watchlist_id)
            flags.append(self._to_flag(row, link, method, linked_client_id))

        candidate_ids = [c.client_id for c in window]
        if chosen and chosen not in candidate_ids:
            candidate_ids.insert(0, chosen)
        for cid in candidate_ids:
            is_chosen = cid == chosen
            for row in self._repo.watchlist_for(cid).itertuples():
                add(
                    row,
                    WatchlistLink.CONFIRMED if is_chosen else WatchlistLink.POSSIBLE,
                    LinkMethod.CLIENT_ID if is_chosen else LinkMethod.HOMONYM_CANDIDATE,
                    cid,
                )
            for row in self._name_links(cid):
                add(row, WatchlistLink.POSSIBLE, LinkMethod.NAME, cid)
        return flags

    def _name_links(self, client_id: str):
        spellings = self._resolver.spellings_of(client_id)
        for row, wl_name in self._orphans:
            if any(_same_name(wl_name, s) for s in spellings) or (
                client_id in self._resolver.alias_client_ids(row.client_name)
            ):
                yield row

    def _to_flag(self, row, link, method, linked_client_id) -> RiskFlag:
        first_start = (
            self._repo.clients.at[linked_client_id, "first_policy_start"]
            if linked_client_id in self._repo.clients.index
            else pd.NaT
        )
        predates = (
            None
            if pd.isna(row.flag_date) or pd.isna(first_start)
            else bool(row.flag_date < first_start)
        )
        return RiskFlag(
            watchlist_id=row.watchlist_id,
            watchlist_client_id=row.ClientId,
            watchlist_client_name=row.client_name,
            flag_type=row.flag_type,
            severity=row.severity,
            status=row.status,
            flag_date=_date(row.flag_date),
            resolved_date=_date(row.resolved_date),
            notes=row.notes,
            link=link,
            link_method=method,
            linked_client_id=linked_client_id,
            note_contradicts_status=watchlist_note_contradicts_status(row.notes, row.status),
            predates_relationship=predates,
            evidence=[f"watchlist:{row.watchlist_id}"],
        )
