import hashlib
from pathlib import Path

import pandas as pd
import pytest

from research.abnb.pipeline.daily_features import FEATURE_COLUMNS, STATUS_COLUMNS
from research.abnb.pipeline.monthly_features import (
    SAMPLING_RULE,
    build_monthly_feature_table,
    sample_monthly_features,
    write_monthly_feature_table,
)

DAILY_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "interim"
    / "daily_features.parquet"
)


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def daily_features():
    return pd.read_parquet(DAILY_PATH, engine="pyarrow")


@pytest.fixture(scope="module")
def monthly_features(daily_features):
    return sample_monthly_features(daily_features)


def test_selects_actual_month_end_only_after_month_is_complete(monthly_features):
    assert len(monthly_features) == 69
    assert monthly_features.iloc[0]["session_date"] == pd.Timestamp("2020-12-31")
    assert monthly_features.iloc[-1]["session_date"] == pd.Timestamp("2026-08-31")
    assert "2026-09" not in set(monthly_features["calendar_month"])
    assert monthly_features["calendar_month"].is_unique

    by_month = monthly_features.set_index("calendar_month")
    assert by_month.loc["2021-12", "session_date"] == pd.Timestamp("2021-12-31")
    assert by_month.loc["2024-11", "session_date"] == pd.Timestamp("2024-11-29")


def test_monthly_feature_and_status_cells_are_exact_daily_rows(
    daily_features, monthly_features
):
    daily_selected = daily_features.set_index("session_date").loc[
        monthly_features["session_date"]
    ]
    monthly_selected = monthly_features.set_index("session_date")

    pd.testing.assert_frame_equal(
        monthly_selected[list(FEATURE_COLUMNS) + list(STATUS_COLUMNS)],
        daily_selected[list(FEATURE_COLUMNS) + list(STATUS_COLUMNS)],
    )


def test_sampling_does_not_recalculate_recursive_or_volatility_values(
    daily_features,
):
    daily = daily_features.copy()
    month_end = daily["session_date"].eq(pd.Timestamp("2025-01-31"))
    sentinels = {
        "ABNB_RSI_14": 12345.0,
        "ABNB_EMA_GAP_20": 23456.0,
        "ABNB_MACD_HIST_NORM": 34567.0,
        "SPY_RVOL_20D": 45678.0,
    }
    for column, value in sentinels.items():
        daily.loc[month_end, column] = value

    sampled = sample_monthly_features(daily).set_index("calendar_month")
    for column, value in sentinels.items():
        assert sampled.loc["2025-01", column] == value


def test_rejects_daily_artifact_with_a_missing_calendar_session(daily_features):
    incomplete = daily_features.loc[
        ~daily_features["session_date"].eq(pd.Timestamp("2025-06-16"))
    ]

    with pytest.raises(ValueError, match="every calendar session"):
        sample_monthly_features(incomplete)


def test_monthly_parquet_round_trip_and_parent_lineage(tmp_path):
    table = build_monthly_feature_table(DAILY_PATH)
    output = write_monthly_feature_table(
        table, tmp_path / "interim" / "monthly_features.parquet"
    )
    restored = pd.read_parquet(output, engine="pyarrow")

    pd.testing.assert_frame_equal(restored, table)
    assert restored["parent_daily_features_sha256"].unique().tolist() == [
        _sha256(DAILY_PATH)
    ]
    assert restored["monthly_sampling_rule"].unique().tolist() == [SAMPLING_RULE]
    assert restored.attrs["sampling_rule"] == SAMPLING_RULE
    assert restored.attrs["schema_version"] == 1
