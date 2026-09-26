import hashlib
from pathlib import Path

import pandas as pd
import pytest

from research.abnb.pipeline.daily_features import FEATURE_COLUMNS, STATUS_COLUMNS
from research.abnb.pipeline.monthly_features import (
    SAMPLING_RULE,
    TEMPORAL_CONTRACT,
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


def test_weekend_holiday_and_year_boundary_issuance(monthly_features):
    by_month = monthly_features.set_index("calendar_month")

    new_year = by_month.loc["2021-12"]
    assert new_year["reference_session"] == pd.Timestamp("2021-12-31")
    assert new_year["reference_close_utc"] == pd.Timestamp(
        "2021-12-31 21:00:00+00:00"
    )
    assert new_year["information_cutoff_utc"] == new_year["reference_close_utc"]
    assert new_year["issued_at_utc"] == pd.Timestamp("2022-01-03 14:30:00+00:00")

    holiday_weekend = by_month.loc["2021-05"]
    assert holiday_weekend["reference_session"] == pd.Timestamp("2021-05-28")
    assert holiday_weekend["issued_at_utc"] == pd.Timestamp(
        "2021-06-01 13:30:00+00:00"
    )


def test_early_close_uses_actual_close_and_next_regular_open(monthly_features):
    row = monthly_features.set_index("calendar_month").loc["2024-11"]

    assert row["reference_session"] == pd.Timestamp("2024-11-29")
    assert row["reference_close_utc"] == pd.Timestamp(
        "2024-11-29 18:00:00+00:00"
    )
    assert row["information_cutoff_utc"] == row["reference_close_utc"]
    assert row["issued_at_utc"] == pd.Timestamp("2024-12-02 14:30:00+00:00")


def test_maturity_is_final_session_exactly_three_calendar_months_later(
    monthly_features,
):
    by_month = monthly_features.set_index("calendar_month")

    november = by_month.loc["2024-11"]
    assert november["maturity_session"] == pd.Timestamp("2025-02-28")
    assert november["label_available_at"] == pd.Timestamp(
        "2025-02-28 21:00:00+00:00"
    )

    year_boundary = by_month.loc["2021-11"]
    assert year_boundary["maturity_session"] == pd.Timestamp("2022-02-28")
    assert year_boundary["label_available_at"] == pd.Timestamp(
        "2022-02-28 21:00:00+00:00"
    )


def test_incomplete_maturity_month_uses_calendar_month_end_not_data_end(
    monthly_features,
):
    latest = monthly_features.iloc[-1]

    assert latest["reference_session"] == pd.Timestamp("2026-08-31")
    assert latest["maturity_session"] == pd.Timestamp("2026-11-30")
    assert latest["maturity_session"] > pd.Timestamp("2026-09-23")
    assert latest["label_available_at"] == pd.Timestamp(
        "2026-11-30 21:00:00+00:00"
    )


def test_three_calendar_months_is_not_approximated_as_63_sessions(monthly_features):
    by_month = monthly_features.set_index("calendar_month")
    row = by_month.loc["2021-05"]

    assert row["maturity_session"] == pd.Timestamp("2021-08-31")
    # The 63rd following XNYS session is 2021-08-27, proving the contract is
    # calendar-month based rather than a fixed session offset.
    assert row["maturity_session"] != pd.Timestamp("2021-08-27")


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
    assert restored["monthly_temporal_contract"].unique().tolist() == [
        TEMPORAL_CONTRACT
    ]
    assert restored.attrs["sampling_rule"] == SAMPLING_RULE
    assert restored.attrs["temporal_contract"] == TEMPORAL_CONTRACT
    assert restored.attrs["schema_version"] == 2
