"""Small hand-built databases that reproduce the hard cases of the real data, so tests are fast
and independent from the 50k-row CSV."""

import pandas as pd
import pytest

from uw_agent.data.loader import Datasets
from uw_agent.data.repository import DataRepository

T = pd.Timestamp
AS_OF = T("2025-06-30").date()


def _policies(
    client_id,
    names,
    state,
    n,
    start="2021-03-01",
    years=1,
    premium=1000.0,
    industry="",
    coverage="Ingeniería",
):
    return [
        {
            "policy_id": f"{client_id}-{i}",
            "client_name": names[i % len(names)],
            "ClientId": client_id,
            "state": state,
            "municipality": "M",
            "coverage_type": coverage,
            "industry": industry,
            "premium": premium,
            "sum_insured": premium * 50,
            "policy_start_date": T(start) + pd.DateOffset(months=6 * i),
            "policy_end_date": T(start) + pd.DateOffset(months=6 * i, years=years),
        }
        for i in range(n)
    ]


def _claim(cid, client_id, policy_id, date, incurred, status="cerrado", ctype="falla_equipo"):
    return {
        "claim_id": cid,
        "policy_id": policy_id,
        "ClientId": client_id,
        "client_name": "x",
        "state": "x",
        "coverage_type": "Ingeniería",
        "claim_type": ctype,
        "claim_date": T(date),
        "incurred_loss_mxn": incurred,
        "reserved_mxn": incurred * 1.2,
        "loss_ratio": 0.0,
        "status": status,
    }


def _flag(wid, client_id, name, ftype, severity, status, flag_date, notes="Nota.", resolved=None):
    return {
        "watchlist_id": wid,
        "client_name": name,
        "ClientId": client_id,
        "flag_type": ftype,
        "severity": severity,
        "flag_date": T(flag_date),
        "resolved_date": T(resolved) if resolved else pd.NaT,
        "status": status,
        "notes": notes,
    }


@pytest.fixture(scope="session")
def repo() -> DataRepository:
    rows = []
    # Dominant client + small homonym; the dominant one also carries a truncated spelling
    # shared with a different company.
    rows += _policies(
        "BIG",
        ["Tecnologías Arcoíris S.A. de C.V.", "TECNOLOGIAS ARCOIRIS SACV", "Arcoíris S.A. de C.V."],
        "Tamaulipas",
        50,
        industry="Construcción",
    )
    rows += _policies("SMALL", ["Tecnologías Arcoíris S.A. de C.V."], "Veracruz", 2)
    rows += _policies("SC", ["Tecnologías Arcoíris S.C."], "Querétaro", 5)
    rows += _policies(
        "SOL", ["Soluciones Arcoíris S.A. de C.V.", "Arcoíris S.A. de C.V."], "Michoacán", 6
    )
    # Two homonyms without a dominant one; N2 has an active critical sanction.
    rows += _policies("N1", ["Grupo Quimera S.A."], "Jalisco", 3)
    rows += _policies("N2", ["Grupo Quimera S.A."], "Sonora", 3)
    rows += _policies(
        "MOR", ["Constructora Morelos S.A. de C.V."], "Puebla", 4, industry="Construcción"
    )
    # Real company with trade names; the watchlist also lists it under an unknown ClientId.
    rows += _policies(
        "PDG", ["Petrolera del Golfo S.A.", "PDG", "Pdg"], "Ciudad de México", 3, industry="Minería"
    )
    # Client with long history and a high loss ratio.
    rows += _policies(
        "LOSS",
        ["Transportes Delta S.A. de C.V."],
        "Puebla",
        6,
        industry="Transporte y Logística",
        start="2021-01-15",
    )
    # Thin client: one policy.
    rows += _policies(
        "THIN", ["Industrias Omega S.C."], "Sonora", 1, start="2024-01-10", industry="Manufactura"
    )
    # Historical-name pair for related entities.
    rows += _policies(
        "HSBC", ["HSBC México S.A."], "Ciudad de México", 3, industry="Servicios Financieros"
    )
    rows += _policies(
        "BITAL", ["BITAL SA"], "Ciudad de México", 2, industry="Servicios Financieros"
    )

    claims = [
        # LOSS: 6 policies x 1000 premium; 7000 incurred -> LR 1.17, credible.
        _claim("C1", "LOSS", "LOSS-0", "2021-05-01", 3000),
        _claim("C2", "LOSS", "LOSS-1", "2021-10-01", 4000, status="en_disputa"),
        _claim("C3", "LOSS", "LOSS-2", "2022-05-01", 0.0, status="en_disputa"),
        # Claim after AS_OF: must be excluded.
        _claim("C4", "LOSS", "LOSS-5", "2026-01-01", 9999),
        # THIN: 1 policy, LR 1.6 but not credible.
        _claim("C5", "THIN", "THIN-0", "2024-03-01", 1600),
    ]
    watchlist = [
        _flag(
            "W1",
            "PDG",
            "Petrolera del Golfo S.A.",
            "sancion_regulatoria",
            "crítico",
            "activo",
            "2020-03-30",
        ),
        _flag("W2", "WL-ONLY-01", "PDG", "riesgo_crediticio", "alto", "activo", "2019-05-19"),
        _flag(
            "W3",
            "N2",
            "Grupo Quimera S.A.",
            "sancion_regulatoria",
            "crítico",
            "activo",
            "2022-01-01",
        ),
        _flag(
            "W4",
            "SMALL",
            "Tecnologías Arcoíris S.A. de C.V.",
            "pago_incumplido",
            "medio",
            "activo",
            "2022-01-01",
        ),
        _flag(
            "W5",
            "MOR",
            "Constructora Morelos S.A. de C.V.",
            "litigio_activo",
            "medio",
            "resuelto",
            "2022-01-01",
            notes="Demanda civil/mercantil en curso.",
            resolved="2023-01-01",
        ),
    ]
    return DataRepository(
        Datasets(
            portfolio=pd.DataFrame(rows),
            claims=pd.DataFrame(claims),
            watchlist=pd.DataFrame(watchlist),
        )
    )
