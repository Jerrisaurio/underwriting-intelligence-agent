"""Dataset-level data-quality checks.

These checks make the findings from the exploratory analysis reproducible
(``uw-agent data-quality``) instead of leaving them as claims in the README. Some of
them also drive per-client conflicts later (e.g. watchlist note vs status).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from uw_agent.data.repository import DataRepository

# Wording in watchlist notes that describes an *ongoing* situation. If the entry is
# marked "resuelto", the note and the status disagree (28 such cases in the data).
ONGOING_NOTE_PATTERN = re.compile(
    # Explicit phrases rather than a bare "activo": "Sin impacto activo" means the opposite.
    r"en curso|sin liquidar|sin pago|pendiente|diligencia activ|deteriorad|degradad|monitorear",
    re.IGNORECASE,
)
STALE_OPEN_CLAIM_YEARS = 3


@dataclass
class DataIssue:
    code: str
    severity: str  # info | warning | error
    count: int
    description: str
    examples: list[str] = field(default_factory=list)


def watchlist_note_contradicts_status(notes: str, status: str) -> bool:
    return status == "resuelto" and bool(ONGOING_NOTE_PATTERN.search(notes))


def run_quality_checks(repo: DataRepository, as_of: date) -> list[DataIssue]:
    p, c, w = repo.portfolio, repo.claims, repo.watchlist
    as_of_ts = pd.Timestamp(as_of)
    issues: list[DataIssue] = []

    def add(code, severity, mask_or_count, description, examples=None):
        count = int(mask_or_count.sum()) if hasattr(mask_or_count, "sum") else mask_or_count
        if count:
            issues.append(DataIssue(code, severity, count, description, examples or []))

    # Parse failures (loader coerces instead of raising).
    for name, df, cols in [
        ("portfolio", p, ["premium", "sum_insured", "policy_start_date", "policy_end_date"]),
        ("claims", c, ["incurred_loss_mxn", "reserved_mxn", "loss_ratio", "claim_date"]),
        ("watchlist", w, ["flag_date"]),
    ]:
        for col in cols:
            add("PARSE_FAILURE", "error", df[col].isna(), f"{name}.{col} could not be parsed")

    # Portfolio
    add("MISSING_INDUSTRY", "warning", p["industry"] == "", "Policies with empty industry")
    add("STATE_OTROS", "info", p["state"] == "Otros", "Policies with non-specific state 'Otros'")
    ids_per_name = p.groupby("client_name")["ClientId"].nunique()
    add(
        "NAME_SHARED_BY_CLIENTIDS",
        "warning",
        ids_per_name > 1,
        "Exact client names that belong to more than one ClientId (homonyms)",
        ids_per_name[ids_per_name > 1].sort_values(ascending=False).head(3).index.tolist(),
    )

    # Claims
    add(
        "CLAIM_AFTER_AS_OF",
        "warning",
        c["claim_date"] > as_of_ts,
        f"Claims dated after as_of_date {as_of}",
    )
    closed = c["status"] == "cerrado"
    add(
        "RESERVE_ON_CLOSED_CLAIM",
        "info",
        closed & (c["reserved_mxn"] > 0),
        "Closed claims that keep a reserve; reserved_mxn is treated as the registered "
        "reserve, not the outstanding one",
    )
    stale_cut = as_of_ts - pd.DateOffset(years=STALE_OPEN_CLAIM_YEARS)
    add(
        "STALE_OPEN_CLAIM",
        "warning",
        (~closed) & (c["claim_date"] < stale_cut),
        f"Open or disputed claims older than {STALE_OPEN_CLAIM_YEARS} years",
    )

    # Watchlist
    add(
        "WATCHLIST_ID_NOT_IN_PORTFOLIO",
        "warning",
        ~w["ClientId"].isin(p["ClientId"]),
        "Watchlist ClientIds absent from the portfolio (linkable by name only)",
        w.loc[~w["ClientId"].isin(p["ClientId"]), "client_name"].tolist(),
    )
    contradict = [
        watchlist_note_contradicts_status(n, s)
        for n, s in zip(w["notes"], w["status"], strict=True)
    ]
    add(
        "WATCHLIST_NOTE_VS_STATUS",
        "warning",
        pd.Series(contradict),
        "Entries marked 'resuelto' whose note describes an ongoing situation",
        w.loc[contradict, "watchlist_id"].head(5).tolist(),
    )
    first_policy = repo.clients["first_policy_start"]
    flagged = w.join(first_policy, on="ClientId")
    add(
        "FLAG_PREDATES_RELATIONSHIP",
        "info",
        flagged["flag_date"] < flagged["first_policy_start"],
        "Watchlist flags older than the client's first policy",
    )
    return issues
