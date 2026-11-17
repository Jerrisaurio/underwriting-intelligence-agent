"""Small hand-built portfolio that reproduces the hard cases of the real data,
so resolver tests are fast and independent from the 50k-row CSV."""

import pandas as pd
import pytest

from uw_agent.data.loader import Datasets
from uw_agent.data.repository import DataRepository


def _policies(client_id, names, state, n):
    return [
        {
            "policy_id": f"{client_id}-{i}",
            "client_name": names[i % len(names)],
            "ClientId": client_id,
            "state": state,
            "municipality": "M",
            "coverage_type": "Ingeniería",
            "industry": "",
            "premium": 1000.0,
            "sum_insured": 50000.0,
            "policy_start_date": pd.Timestamp("2023-01-01"),
            "policy_end_date": pd.Timestamp("2024-01-01"),
        }
        for i in range(n)
    ]


@pytest.fixture(scope="session")
def repo() -> DataRepository:
    rows = []
    # A dominant client plus a small homonym in another state; the dominant one also
    # carries a truncated spelling shared with a different company.
    rows += _policies(
        "BIG",
        ["Tecnologías Bajío S.A. de C.V.", "TECNOLOGIAS BAJIO SACV", "Bajío S.A. de C.V."],
        "Tamaulipas",
        50,
    )
    rows += _policies("SMALL", ["Tecnologías Bajío S.A. de C.V."], "Veracruz", 2)
    rows += _policies("SC", ["Tecnologías Bajío S.C."], "Querétaro", 5)
    rows += _policies(
        "SOL", ["Soluciones Bajío S.A. de C.V.", "Bajío S.A. de C.V."], "Michoacán", 6
    )
    # Two homonyms without a dominant one.
    rows += _policies("N1", ["Grupo Nova S.A."], "Jalisco", 3)
    rows += _policies("N2", ["Grupo Nova S.A."], "Sonora", 3)
    # Look-alike synthetic names that must stay apart.
    rows += _policies("MOR", ["Constructora Morelos S.A. de C.V."], "Puebla", 4)
    # Real company with trade names.
    rows += _policies("PMX", ["Petróleos Mexicanos", "PEMEX", "Pemex"], "Ciudad de México", 3)
    portfolio = pd.DataFrame(rows)
    empty = pd.DataFrame()
    return DataRepository(
        Datasets(
            portfolio=portfolio,
            claims=empty.assign(ClientId=[]),
            watchlist=empty.assign(ClientId=[]),
        )
    )
