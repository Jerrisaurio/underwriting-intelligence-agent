"""Read-only, indexed access to the internal databases.

``ClientId`` is the entity key. In the data, state, municipality and industry are
constant within a ClientId, while the *name* is not: one ClientId carries up to 7
spellings, and one spelling can belong to up to 11 ClientIds. Everything
downstream therefore aggregates by ClientId, never by name.
"""

from __future__ import annotations

from functools import cached_property
from pathlib import Path

import pandas as pd

from uw_agent.data.loader import Datasets, load_datasets


class DataRepository:
    def __init__(self, datasets: Datasets) -> None:
        self._ds = datasets
        # groupby(...).indices gives positional row arrays: O(1) lookups per client
        # instead of a full-table scan per query, which matters in batch runs.
        self._policy_rows = datasets.portfolio.groupby("ClientId").indices
        self._claim_rows = datasets.claims.groupby("ClientId").indices
        self._watch_rows = datasets.watchlist.groupby("ClientId").indices

    @classmethod
    def load(cls, data_dir: Path | str) -> DataRepository:
        return cls(load_datasets(data_dir))

    @property
    def portfolio(self) -> pd.DataFrame:
        return self._ds.portfolio

    @property
    def claims(self) -> pd.DataFrame:
        return self._ds.claims

    @property
    def watchlist(self) -> pd.DataFrame:
        return self._ds.watchlist

    def policies_for(self, client_id: str) -> pd.DataFrame:
        return self._take(self.portfolio, self._policy_rows, client_id)

    def claims_for(self, client_id: str) -> pd.DataFrame:
        return self._take(self.claims, self._claim_rows, client_id)

    def watchlist_for(self, client_id: str) -> pd.DataFrame:
        """Watchlist rows linked by ClientId only. Name-based matching belongs to the
        watchlist tool, because 7 watchlist ClientIds (``FAMS…``) do not exist in the
        portfolio and can only be linked by name."""
        return self._take(self.watchlist, self._watch_rows, client_id)

    @cached_property
    def clients(self) -> pd.DataFrame:
        """One row per ClientId with the attributes used to describe candidates."""
        p = self.portfolio
        industry = (
            p[p["industry"] != ""].groupby("ClientId")["industry"].first()
        )  # constant within a ClientId when present
        g = p.groupby("ClientId")
        out = pd.DataFrame(
            {
                "display_name": g["client_name"].agg(lambda s: s.value_counts().index[0]),
                "state": g["state"].first(),
                "municipality": g["municipality"].first(),
                "n_policies": g.size(),
                "first_policy_start": g["policy_start_date"].min(),
                "last_policy_end": g["policy_end_date"].max(),
            }
        )
        out["industry"] = industry.reindex(out.index).fillna("")
        return out

    @staticmethod
    def _take(df: pd.DataFrame, index: dict, key: str) -> pd.DataFrame:
        rows = index.get(key)
        if rows is None:
            return df.iloc[0:0]
        return df.iloc[rows]
