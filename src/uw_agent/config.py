"""Runtime settings, read from environment variables (never hardcoded)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    as_of_date: date

    @classmethod
    def from_env(cls) -> Settings:
        raw_date = os.getenv("UW_AS_OF_DATE", "").strip()
        return cls(
            data_dir=Path(os.getenv("UW_DATA_DIR", "data")),
            as_of_date=date.fromisoformat(raw_date) if raw_date else date.today(),
        )
