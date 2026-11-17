"""Client history: portfolio and claims summaries for one ClientId at a reference date.

Rules that are easy to get wrong, made explicit here:
- Only policies started on or before ``as_of`` count (the profile describes what was known then).
- A policy is active when ``start <= as_of < end``.
- Claims after ``as_of`` are excluded and reported (the data contains claims dated in the future
  relative to its own snapshot).
- The client loss ratio is Σ incurred / Σ *written* premium. The source has no earned premium,
  so 2-year policies are not pro-rated; this is a documented limitation.
- ``reserved_mxn`` is reported as recorded: closed claims keep a reserve of 1.0-1.4x incurred in
  the source, so the sum is not outstanding exposure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from uw_agent.data.repository import DataRepository
from uw_agent.schema.profile import (
    ClaimsPerformance,
    CoverageLine,
    Credibility,
    Relationship,
    YearLine,
)

MIN_CREDIBLE_POLICIES = 3
MIN_CREDIBLE_YEARS = 2


@dataclass
class HistoryResult:
    relationship: Relationship
    claims: ClaimsPerformance
    data_gaps: list[str] = field(default_factory=list)
    anomalies: list[tuple[str, list[str]]] = field(default_factory=list)  # (description, sources)


def _d(ts) -> date | None:
    return None if pd.isna(ts) else ts.date()


def summarize_history(repo: DataRepository, client_id: str, as_of: date) -> HistoryResult:
    as_of_ts = pd.Timestamp(as_of)
    gaps: list[str] = []
    anomalies: list[tuple[str, list[str]]] = []

    pol = repo.policies_for(client_id)
    bad = pol[
        pol[["premium", "sum_insured", "policy_start_date", "policy_end_date"]].isna().any(axis=1)
    ]
    if len(bad):
        anomalies.append(
            (
                f"{len(bad)} póliza(s) con valores ilegibles excluidas de las métricas",
                [f"portfolio:{p}" for p in bad["policy_id"]],
            )
        )
    pol = pol.drop(bad.index)
    future = pol[pol["policy_start_date"] > as_of_ts]
    if len(future):
        gaps.append(
            f"{len(future)} póliza(s) inician después de la fecha de referencia y no se consideran"
        )
    pol = pol[pol["policy_start_date"] <= as_of_ts]
    active = (pol["policy_start_date"] <= as_of_ts) & (as_of_ts < pol["policy_end_date"])
    if not active.any():
        gaps.append(f"Sin pólizas vigentes al {as_of.isoformat()}")

    mix = [
        CoverageLine(
            coverage_type=cov,
            n_policies=len(g),
            n_active=int(active[g.index].sum()),
            premium_mxn=round(g["premium"].sum(), 2),
            sum_insured_mxn=round(g["sum_insured"].sum(), 2),
        )
        for cov, g in pol.groupby("coverage_type")
    ]
    relationship = Relationship(
        n_policies=len(pol),
        n_active_policies=int(active.sum()),
        total_premium_mxn=round(pol["premium"].sum(), 2),
        total_sum_insured_mxn=round(pol["sum_insured"].sum(), 2),
        active_premium_mxn=round(pol.loc[active, "premium"].sum(), 2),
        active_sum_insured_mxn=round(pol.loc[active, "sum_insured"].sum(), 2),
        first_policy_start=_d(pol["policy_start_date"].min()),
        last_policy_end=_d(pol["policy_end_date"].max()),
        coverage_mix=sorted(mix, key=lambda c: -c.premium_mxn),
        evidence=[f"portfolio:{p}" for p in pol["policy_id"]],
    )

    clm = repo.claims_for(client_id)
    unreadable = clm[clm[["claim_date", "incurred_loss_mxn"]].isna().any(axis=1)]
    if len(unreadable):
        anomalies.append(
            (
                f"{len(unreadable)} siniestro(s) con valores ilegibles excluidos",
                [f"claims:{c}" for c in unreadable["claim_id"]],
            )
        )
    clm = clm.drop(unreadable.index)
    after = clm[clm["claim_date"] > as_of_ts]
    if len(after):
        anomalies.append(
            (
                f"{len(after)} siniestro(s) con fecha posterior a la fecha de referencia excluidos",
                [f"claims:{c}" for c in after["claim_id"]],
            )
        )
    # Claims must also belong to a policy that is in scope.
    clm = clm[(clm["claim_date"] <= as_of_ts) & clm["policy_id"].isin(pol["policy_id"])]

    premium = pol["premium"].sum()
    incurred = clm["incurred_loss_mxn"].sum()
    open_mask = clm["status"] != "cerrado"
    oldest_open = clm.loc[open_mask, "claim_date"].min()
    years = (as_of_ts - pol["policy_start_date"].min()).days / 365.25 if len(pol) else 0
    credible = len(pol) >= MIN_CREDIBLE_POLICIES and years >= MIN_CREDIBLE_YEARS

    by_year = []
    start_year = pol["policy_start_date"].dt.year
    for year, g in pol.groupby(start_year):
        c = clm[clm["policy_id"].isin(g["policy_id"])]
        p = g["premium"].sum()
        by_year.append(
            YearLine(
                policy_start_year=int(year),
                n_policies=len(g),
                premium_mxn=round(p, 2),
                n_claims=len(c),
                incurred_mxn=round(c["incurred_loss_mxn"].sum(), 2),
                loss_ratio=round(c["incurred_loss_mxn"].sum() / p, 4) if p else 0.0,
            )
        )

    claims = ClaimsPerformance(
        n_claims=len(clm),
        n_excluded_after_as_of=len(after),
        incurred_mxn=round(incurred, 2),
        reserved_registered_mxn=round(clm["reserved_mxn"].sum(), 2),
        by_status={k: int(v) for k, v in clm["status"].value_counts().items()},
        oldest_open_claim_date=_d(oldest_open),
        oldest_open_claim_age_days=None if pd.isna(oldest_open) else (as_of_ts - oldest_open).days,
        client_loss_ratio=round(incurred / premium, 4) if premium else 0.0,
        credibility=Credibility.CREDIBLE if credible else Credibility.LOW,
        by_year=by_year,
        top_claim_types={k: int(v) for k, v in clm["claim_type"].value_counts().head(5).items()},
        evidence=[f"claims:{c}" for c in clm["claim_id"]],
    )
    return HistoryResult(relationship, claims, gaps, anomalies)
