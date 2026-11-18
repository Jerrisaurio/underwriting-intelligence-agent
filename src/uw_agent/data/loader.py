"""Load the three internal CSVs into typed DataFrames.

File conventions observed in the source data:
- UTF-8 with a BOM, so we read with ``utf-8-sig`` (otherwise the first column is
  named ``\\ufeffpolicy_id``).
- Dates are ``DD/MM/YYYY``. We parse with an explicit format: inferring the format
  would silently swap day and month for dates like 04/01/2022.
- Empty strings mean "missing" (e.g. ``industry``, ``resolved_date``).

Values that fail to parse do not raise: they become NaT/NaN and are counted by
:mod:`uw_agent.data.quality`, so one bad row never takes down a batch run.
Missing *columns*, however, raise :class:`DataSchemaError`, because then nothing
downstream can be trusted.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

DATE_FORMAT = "%d/%m/%Y"

PORTFOLIO_FILE = "portfolio_mexico.csv"
CLAIMS_FILE = "claims.csv"
WATCHLIST_FILE = "watchlist.csv"

PORTFOLIO_COLUMNS = {
    "policy_id": "str",
    "client_name": "str",
    "ClientId": "str",
    "state": "str",
    "municipality": "str",
    "coverage_type": "str",
    "industry": "str",
    "premium": "float",
    "sum_insured": "float",
    "policy_start_date": "date",
    "policy_end_date": "date",
}

CLAIMS_COLUMNS = {
    "claim_id": "str",
    "policy_id": "str",
    "ClientId": "str",
    "client_name": "str",
    "state": "str",
    "coverage_type": "str",
    "claim_type": "str",
    "claim_date": "date",
    "incurred_loss_mxn": "float",
    "reserved_mxn": "float",
    "loss_ratio": "float",
    "status": "str",
}

WATCHLIST_COLUMNS = {
    "watchlist_id": "str",
    "client_name": "str",
    "ClientId": "str",
    "flag_type": "str",
    "severity": "str",
    "flag_date": "date",
    "resolved_date": "date",
    "status": "str",
    "notes": "str",
}


class DataSchemaError(ValueError):
    """A source file is missing or lacks required columns."""


@dataclass(frozen=True)
class Datasets:
    portfolio: pd.DataFrame
    claims: pd.DataFrame
    watchlist: pd.DataFrame


def _read_typed(path: Path, columns: dict[str, str]) -> pd.DataFrame:
    if not path.exists():
        raise DataSchemaError(f"Missing data file: {path}")
    df = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    missing = set(columns) - set(df.columns)
    if missing:
        raise DataSchemaError(f"{path.name} is missing columns: {sorted(missing)}")

    for col, kind in columns.items():
        stripped = df[col].str.strip()
        if kind == "str":
            df[col] = stripped
        elif kind == "float":
            df[col] = pd.to_numeric(stripped, errors="coerce")
        elif kind == "date":
            df[col] = pd.to_datetime(stripped, format=DATE_FORMAT, errors="coerce")
    return df[list(columns)]


def load_datasets(data_dir: Path | str) -> Datasets:
    data_dir = Path(data_dir)
    return Datasets(
        portfolio=_read_typed(data_dir / PORTFOLIO_FILE, PORTFOLIO_COLUMNS),
        claims=_read_typed(data_dir / CLAIMS_FILE, CLAIMS_COLUMNS),
        watchlist=_read_typed(data_dir / WATCHLIST_FILE, WATCHLIST_COLUMNS),
    )
