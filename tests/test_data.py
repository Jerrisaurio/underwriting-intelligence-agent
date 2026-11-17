import pandas as pd
import pytest

from uw_agent.data.loader import (
    CLAIMS_FILE,
    PORTFOLIO_FILE,
    WATCHLIST_FILE,
    DataSchemaError,
    load_datasets,
)
from uw_agent.data.quality import watchlist_note_contradicts_status


def _write(path, header, row):
    # BOM on purpose: the real files carry one.
    path.write_text("\ufeff" + header + "\n" + row + "\n", encoding="utf-8")


@pytest.fixture
def data_dir(tmp_path):
    _write(
        tmp_path / PORTFOLIO_FILE,
        "policy_id,client_name,ClientId,state,municipality,coverage_type,industry,premium,"
        "sum_insured,policy_start_date,policy_end_date",
        "POL-1,ACME S.A.,ID1,Jalisco,Zapopan,Agrícola,,100.5,1000,04/01/2022,04/01/2023",
    )
    _write(
        tmp_path / CLAIMS_FILE,
        "claim_id,policy_id,ClientId,client_name,state,coverage_type,claim_type,claim_date,"
        "incurred_loss_mxn,reserved_mxn,loss_ratio,status",
        "CLM-1,POL-1,ID1,ACME S.A.,Jalisco,Agrícola,plaga,not-a-date,10,12,0.1,abierto",
    )
    _write(
        tmp_path / WATCHLIST_FILE,
        "watchlist_id,client_name,ClientId,flag_type,severity,flag_date,resolved_date,status,notes",
        "WL-1,ACME S.A.,ID1,litigio_activo,medio,01/02/2021,,activo,x",
    )
    return tmp_path


def test_loader_handles_bom_and_day_first_dates(data_dir):
    ds = load_datasets(data_dir)
    row = ds.portfolio.iloc[0]
    assert row["policy_start_date"] == pd.Timestamp("2022-01-04")  # 4 Jan, not 1 Apr
    assert row["premium"] == 100.5
    assert row["industry"] == ""


def test_unparseable_value_becomes_missing_instead_of_raising(data_dir):
    assert pd.isna(load_datasets(data_dir).claims.iloc[0]["claim_date"])


def test_missing_column_raises(data_dir):
    _write(data_dir / WATCHLIST_FILE, "watchlist_id,client_name", "WL-1,ACME")
    with pytest.raises(DataSchemaError, match="missing columns"):
        load_datasets(data_dir)


def test_missing_file_raises(tmp_path):
    with pytest.raises(DataSchemaError, match="Missing data file"):
        load_datasets(tmp_path)


@pytest.mark.parametrize(
    ("note", "status", "expected"),
    [
        ("Demanda civil/mercantil en curso.", "resuelto", True),
        ("Prima vencida sin liquidar.", "resuelto", True),
        ("Proceso de debida diligencia activo.", "resuelto", True),
        ("Demanda colectiva resuelta en 2023. Sin impacto activo.", "resuelto", False),
        ("Demanda civil/mercantil en curso.", "activo", False),
    ],
)
def test_watchlist_note_vs_status(note, status, expected):
    assert watchlist_note_contradicts_status(note, status) is expected
