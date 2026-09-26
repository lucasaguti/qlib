import json

import numpy as np
import pandas as pd
import pytest

from research.abnb.pipeline.daily_features import FEATURE_COLUMNS, STATUS_COLUMNS
from research.abnb.pipeline.feature_diagnostics import (
    assign_subperiods,
    correlation_diagnostics,
    corporate_action_diagnostics,
    effective_sample_diagnostics,
    load_development_inputs,
    status_diagnostics,
)
from research.abnb.pipeline.targets import TARGET_COLUMN, TARGET_STATUS_COLUMN


def _feature_rows(sessions):
    rows = pd.DataFrame({"reference_session": pd.to_datetime(sessions)})
    for number, feature in enumerate(FEATURE_COLUMNS, 1):
        rows[feature] = np.arange(len(rows), dtype=float) + number
        rows[f"{feature}_STATUS"] = "VALID"
    return rows


def _target_rows(sessions):
    rows = pd.DataFrame({"reference_session": pd.to_datetime(sessions)})
    rows["maturity_session"] = rows["reference_session"] + pd.offsets.MonthEnd(3)
    rows[TARGET_COLUMN] = np.linspace(-0.1, 0.2, len(rows))
    rows[TARGET_STATUS_COLUMN] = "VALID"
    rows["evaluation_partition"] = [
        "DEVELOPMENT" if session <= pd.Timestamp("2021-03-31") else "FINAL_TEST"
        for session in rows["reference_session"]
    ]
    return rows


def test_filtered_load_never_materializes_rows_after_development_cutoff(tmp_path):
    sessions = pd.date_range("2020-12-31", periods=5, freq="ME")
    feature_path = tmp_path / "features.parquet"
    target_path = tmp_path / "targets.parquet"
    protocol_path = tmp_path / "protocol.json"
    _feature_rows(sessions).to_parquet(feature_path, index=False)
    _target_rows(sessions).to_parquet(target_path, index=False)
    protocol_path.write_text(
        json.dumps(
            {
                "periods": {
                    "development_origin_start": "2020-12-31",
                    "development_origin_end": "2021-03-31",
                }
            }
        ),
        encoding="utf-8",
    )

    features, targets, _, cutoff = load_development_inputs(
        feature_path, target_path, protocol_path
    )

    assert cutoff == pd.Timestamp("2021-03-31")
    assert features["reference_session"].max() == cutoff
    assert targets["reference_session"].max() == cutoff
    assert len(features) == len(targets) == 4
    assert targets["evaluation_partition"].eq("DEVELOPMENT").all()


def test_subperiods_are_contiguous_and_fixed_by_row_position():
    sessions = pd.Series(pd.date_range("2021-01-31", periods=9, freq="ME"))
    labels = assign_subperiods(sessions)

    assert labels.value_counts(sort=False).tolist() == [3, 3, 3]
    assert labels.iloc[0].startswith("P1:")
    assert labels.iloc[3].startswith("P2:")
    assert labels.iloc[6].startswith("P3:")


def test_status_counts_preserve_warmup_reason_by_period():
    features = _feature_rows(pd.date_range("2021-01-31", periods=6, freq="ME"))
    features["subperiod"] = assign_subperiods(features["reference_session"])
    features.loc[0, "ABNB_MOM_12_2"] = np.nan
    features.loc[0, "ABNB_MOM_12_2_STATUS"] = "INSUFFICIENT_HISTORY"

    result = status_diagnostics(features)["ABNB_MOM_12_2"]

    assert result["ALL"]["value_missing"] == 1
    assert result["ALL"]["status_counts"] == {
        "VALID": 5,
        "INSUFFICIENT_HISTORY": 1,
    }
    assert result[next(key for key in result if key.startswith("P1:"))][
        "status_counts"
    ]["INSUFFICIENT_HISTORY"] == 1


def test_corporate_action_exposure_uses_exact_feature_session_window():
    sessions = pd.date_range("2021-01-04", periods=30, freq="B")
    prices = {}
    for security in ("ABNB", "BKNG", "EXPE", "SPY"):
        close = np.linspace(100, 130, len(sessions))
        prices[security] = pd.DataFrame(
            {"close": close, "adjusted_close": close}, index=sessions
        )
    features = _feature_rows([sessions[-1]])
    # Match the proxies exactly except where adjustment is deliberately changed.
    features.loc[0, "SPY_RET_5D"] = prices["SPY"].close.iloc[-1] / prices["SPY"].close.iloc[-6] - 1
    peer_return = np.mean(
        [
            prices[name].close.iloc[-1] / prices[name].close.iloc[-6] - 1
            for name in ("EXPE", "BKNG")
        ]
    )
    features.loc[0, "PEER_RET_5D"] = peer_return
    raw_returns = np.diff(np.log(prices["SPY"].close.iloc[-21:].to_numpy()))
    features.loc[0, "SPY_RVOL_20D"] = np.std(raw_returns, ddof=1) * np.sqrt(252)
    actions = {security: [] for security in prices}
    actions["SPY"] = [
        {"session_date": sessions[-6], "dividend": 1.0, "split_ratio": 0.0}
    ]
    actions["BKNG"] = [
        {"session_date": sessions[-7], "dividend": 1.0, "split_ratio": 0.0}
    ]

    result = corporate_action_diagnostics(features, prices, actions)

    assert result["features"]["SPY_RET_5D"]["action_exposed_origins"] == 1
    assert result["features"]["SPY_RVOL_20D"]["action_exposed_origins"] == 1
    assert result["features"]["PEER_RET_5D"]["action_exposed_origins"] == 0


def test_effective_sample_reports_design_based_three_month_overlap():
    sessions = pd.date_range("2021-01-31", periods=9, freq="ME")
    features = _feature_rows(sessions)
    targets = _target_rows(sessions)
    targets["evaluation_partition"] = "DEVELOPMENT"

    result = effective_sample_diagnostics(features, targets)
    summary = result["all_valid_development_targets"]

    assert summary["nominal_observations"] == 9
    assert summary["mechanical_nonoverlap_equivalent_n_over_3"] == 3
    assert summary["nonoverlapping_phase_counts"] == [3, 3, 3]


def test_multicollinearity_accepts_pandas_nullable_float_columns():
    features = _feature_rows(pd.date_range("2021-01-31", periods=12, freq="ME"))
    for feature in FEATURE_COLUMNS:
        features[feature] = pd.array(features[feature], dtype="Float64")

    result = correlation_diagnostics(features)

    assert result["multicollinearity"]["complete_case_rows"] == 12
    assert "condition_number" in result["multicollinearity"]


def test_feature_and_status_schema_remain_locked():
    assert len(FEATURE_COLUMNS) == 8
    assert STATUS_COLUMNS == tuple(f"{feature}_STATUS" for feature in FEATURE_COLUMNS)
