"""Runtime settings, read from environment variables (never hardcoded).

A ``.env`` file in the working directory is loaded if present (values already set in the
environment win). Model and prices are configuration on purpose: model availability and
pricing depend on the account and change over time.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _float(name: str) -> float | None:
    raw = os.getenv(name, "").strip()
    return float(raw) if raw else None


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    as_of_date: date
    openai_api_key: str | None = None
    openai_model: str | None = None
    # USD per 1M tokens and per web-search call; None = unpriced (cost reported as null).
    price_input_per_mtok: float | None = None
    price_output_per_mtok: float | None = None
    price_per_web_search: float | None = None
    request_timeout_s: float = 60.0
    cache_dir: Path = Path(".cache")
    cache_ttl_days: int = 7

    @classmethod
    def from_env(cls) -> Settings:
        _load_dotenv()
        raw_date = os.getenv("UW_AS_OF_DATE", "").strip()
        return cls(
            data_dir=Path(os.getenv("UW_DATA_DIR", "data")),
            as_of_date=date.fromisoformat(raw_date) if raw_date else date.today(),
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            openai_model=os.getenv("UW_OPENAI_MODEL") or None,
            price_input_per_mtok=_float("UW_PRICE_INPUT_PER_MTOK"),
            price_output_per_mtok=_float("UW_PRICE_OUTPUT_PER_MTOK"),
            price_per_web_search=_float("UW_PRICE_PER_WEB_SEARCH"),
            request_timeout_s=float(os.getenv("UW_REQUEST_TIMEOUT_S", "60")),
            cache_dir=Path(os.getenv("UW_CACHE_DIR", ".cache")),
            cache_ttl_days=int(os.getenv("UW_CACHE_TTL_DAYS", "7")),
        )
